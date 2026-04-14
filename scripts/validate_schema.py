#!/usr/bin/env python3
"""
数据 schema 强校验 + 质量诊断
- 校验 type 枚举、字段完整性、覆盖率
- 检测虚词空泛、多音字不一致、词组拆分异常
- 输出机器可读报告 + 可被脚本调用的 validate(data) 函数

使用：
  python3 scripts/validate_schema.py                    # 校验所有 data/books/
  python3 scripts/validate_schema.py --book shiji       # 仅某本书
  python3 scripts/validate_schema.py --fix              # 生成需重跑清单
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

BASE_DIR = Path(__file__).parent.parent
BOOKS_DIR = BASE_DIR / "data" / "books"

# ============================================================
# Schema 定义
# ============================================================

VALID_TYPES = {"实词", "虚词", "人名", "地名", "官职", "典故"}

VALID_HIGHLIGHTS = {"ancient_today", "loan", "polyphone", "rare", "fixed"}

VALID_RELATION_TYPES = {
    "父子", "母子", "兄弟", "夫妻", "君臣", "师生", "朋友", "同僚",
    "对手", "盟友", "亲属", "门客", "下属", "上司",
}

# 违禁类型 → 应该归到哪里
TYPE_MIGRATION = {
    "成语": "典故", "典故成语": "典故", "固定结构": "典故",
    "器物": "实词", "物品": "实词", "饮料": "实词", "服饰": "实词",
    "容貌": "实词", "年号": "实词", "名词": "实词", "动词": "实词",
    "代词": "虚词", "专有名词": "人名", "专名": "人名",
    "爵位": "官职",
    "词组": "实词", "短语": "实词", "实词短语": "实词", "动词短语": "实词",
    "句子": "实词", "书名": "典故",
}

# 虚词空泛检测：meaning 只含下列任一词即为空泛
VAGUE_MEANINGS = {
    "它", "他", "的", "代词", "助词", "语气词", "语气助词",
    "连词", "介词", "结构助词", "主谓间", "无义",
    "它们", "他们", "这", "那", "表语气", "语气",
}

# 多音字白名单（至少要在 meaning 里显式说明读音理由）
POLYPHONES = set("亟说遗骑为夫与强识舍乐恶纵数中重见语相属朝王长著卒不宁间应使从称省处度和缝干宿冠难当更好分将教量磨尽空累落闷兴")

# 古今异义高危词
HIGH_RISK_ARCHAIC = set([
    "去", "走", "汤", "再", "绝", "亲戚", "妻子", "牺牲", "羹", "阳",
    "牧", "谢", "购", "币", "或", "羞", "属", "穷", "所以", "卑鄙",
    "中国", "无论", "可怜", "虽然", "然则", "因为", "不必", "几何",
    "丈夫", "夫人", "小人", "君子", "感激", "烈士", "丹青", "形容",
    "书生", "经济", "交通", "抛弃", "痛恨", "开张", "不过", "祖父",
    "大风", "强盗", "故事", "非常", "气候", "学者", "便宜",
    "行李", "风流", "下车", "秋毫", "山东", "河南", "河北",
])

PUNCT_CHARS = set("，。、；：？！\u201c\u201d\u2018\u2019《》（）【】—…·\n\t ")

# ============================================================
# 校验结果
# ============================================================

@dataclass
class Issue:
    severity: str  # error / warn / info
    code: str
    message: str
    location: str = ""


@dataclass
class FileReport:
    path: str
    issues: list[Issue] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warns(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warn"]

    @property
    def needs_rerun(self) -> bool:
        """文件是否需要定向重跑"""
        return any(i.code in {"empty_words", "invalid_type", "empty_sentences"}
                   for i in self.issues)


# ============================================================
# 校验函数
# ============================================================

def _strip_punct(s: str) -> str:
    return "".join(c for c in s if c not in PUNCT_CHARS)


def validate_word(word: dict, sent_orig: str, loc: str) -> list[Issue]:
    issues = []

    # 必需字段
    for field_name in ("word", "pinyin", "meaning", "type"):
        if not word.get(field_name):
            issues.append(Issue("error", "missing_field",
                               f"词条缺少 '{field_name}' 字段: {word}", loc))

    # type 枚举
    t = word.get("type", "")
    if t and t not in VALID_TYPES:
        suggested = TYPE_MIGRATION.get(t, "?")
        issues.append(Issue("error", "invalid_type",
                           f"非法 type: '{t}' (建议改为 '{suggested}')", loc))

    # 虚词 meaning 空泛
    meaning = word.get("meaning", "").strip()
    if t == "虚词" and meaning in VAGUE_MEANINGS:
        issues.append(Issue("warn", "vague_meaning",
                           f"虚词 '{word.get('word')}' 释义空泛: '{meaning}'", loc))

    # meaning 长度
    if len(meaning) < 2:
        issues.append(Issue("warn", "meaning_too_short",
                           f"meaning 过短: '{meaning}'", loc))
    elif len(meaning) > 80:
        issues.append(Issue("warn", "meaning_too_long",
                           f"meaning 过长 ({len(meaning)}字): {meaning[:40]}...", loc))

    # highlight 字段枚举（可选字段，None/缺省 合法）
    hl = word.get("highlight")
    if hl is not None and hl != "" and hl not in VALID_HIGHLIGHTS:
        issues.append(Issue("error", "invalid_highlight",
                           f"非法 highlight: '{hl}'（合法：{sorted(VALID_HIGHLIGHTS)} 或省略）", loc))

    return issues


def validate_sentence(sent: dict, loc: str) -> list[Issue]:
    issues = []

    # error 字段存在说明生成失败
    if sent.get("error"):
        issues.append(Issue("error", "generation_error",
                           f"生成失败: {sent['error']}", loc))

    orig = sent.get("original", "")
    if not orig:
        issues.append(Issue("error", "empty_original", "句子 original 为空", loc))

    # words 数组不能为空（长度 ≥ 1 字的原文必须有词条）
    words = sent.get("words", [])
    if not words and _strip_punct(orig):
        issues.append(Issue("error", "empty_words",
                           f"句子无 words 注释: '{orig[:30]}...'", loc))

    # 覆盖率校验
    if words and orig:
        reconstructed = "".join(w.get("word", "") for w in words)
        orig_clean = _strip_punct(orig)
        recon_clean = _strip_punct(reconstructed)
        if orig_clean != recon_clean:
            issues.append(Issue("warn", "coverage_mismatch",
                               f"词条拼接与原文不匹配: 原'{orig_clean[:30]}' vs 拼'{recon_clean[:30]}'", loc))

    # 检查是否有整句作单词条（严重违反 R1）
    if len(words) == 1 and words[0].get("word", "") == _strip_punct(orig):
        if len(orig) > 6:  # >6 字的整句不应是单词条
            issues.append(Issue("warn", "whole_sentence_as_word",
                               f"整句作为单词条: '{orig[:30]}'", loc))

    # 逐词校验
    for w_idx, w in enumerate(words):
        issues.extend(validate_word(w, orig, f"{loc}.w{w_idx}"))

    return issues


def validate_characters(chars, loc: str) -> list[Issue]:
    """人物卡（可选字段）校验"""
    issues: list[Issue] = []
    if chars is None:
        return issues
    if not isinstance(chars, list):
        issues.append(Issue("error", "characters_not_list",
                           f"characters 必须为数组", loc))
        return issues

    names_in_cards = {c.get("name", "") for c in chars if isinstance(c, dict)}
    for ci, c in enumerate(chars):
        cloc = f"{loc}.c{ci}"
        if not isinstance(c, dict):
            issues.append(Issue("error", "character_not_dict",
                               f"人物卡非 dict: {c}", cloc))
            continue
        for f in ("id", "name", "role", "stance", "motive"):
            if not c.get(f):
                issues.append(Issue("warn", "character_missing_field",
                                   f"人物卡缺少/空 '{f}'", cloc))

        for ri, rel in enumerate(c.get("relations", []) or []):
            rloc = f"{cloc}.r{ri}"
            if not isinstance(rel, dict):
                issues.append(Issue("error", "relation_not_dict",
                                   f"relation 非 dict", rloc))
                continue
            rt = rel.get("type", "")
            if rt and rt not in VALID_RELATION_TYPES:
                issues.append(Issue("warn", "invalid_relation_type",
                                   f"非法 relation.type: '{rt}'", rloc))
            target = rel.get("target", "")
            if target and target not in names_in_cards:
                issues.append(Issue("warn", "relation_target_unknown",
                                   f"relation.target '{target}' 不在人物卡列表", rloc))
    return issues


def validate_document(doc: dict, path: Path) -> FileReport:
    report = FileReport(path=str(path.relative_to(BASE_DIR)))

    # 基本字段
    for field_name in ("id", "title", "paragraphs"):
        if not doc.get(field_name):
            report.issues.append(Issue("error", "missing_doc_field",
                                       f"文档缺少 '{field_name}'", "doc"))

    # 人物卡（可选）
    report.issues.extend(validate_characters(doc.get("characters"), "doc.characters"))

    paragraphs = doc.get("paragraphs", [])
    if not paragraphs:
        report.issues.append(Issue("error", "no_paragraphs", "段落为空", "doc"))
        return report

    # 统计
    total_sents = 0
    total_words = 0
    type_cnt: Counter = Counter()
    highlight_cnt: Counter = Counter()
    polyphone_readings: dict[str, set[str]] = defaultdict(set)

    for p_idx, para in enumerate(paragraphs):
        if not para.get("translation"):
            report.issues.append(Issue("warn", "empty_para_translation",
                                       f"段 {p_idx+1} 翻译为空", f"p{p_idx}"))

        sents = para.get("sentences", [])
        if not sents and para.get("original"):
            report.issues.append(Issue("error", "empty_sentences",
                                       f"段 {p_idx+1} sentences 为空", f"p{p_idx}"))

        for s_idx, sent in enumerate(sents):
            total_sents += 1
            loc = f"p{p_idx}.s{s_idx}"
            report.issues.extend(validate_sentence(sent, loc))

            for w in sent.get("words", []):
                total_words += 1
                type_cnt[w.get("type", "?")] += 1
                hl = w.get("highlight")
                if hl:
                    highlight_cnt[hl] += 1
                # 多音字读音一致性追踪
                word_char = w.get("word", "")
                pinyin = w.get("pinyin", "")
                if len(word_char) == 1 and word_char in POLYPHONES and pinyin:
                    polyphone_readings[word_char].add(pinyin.strip().lower())

    # 多音字跨文档不一致（同一文档内同字多读音可能合理，只做 info）
    multi_reading = {char: readings for char, readings in polyphone_readings.items()
                     if len(readings) > 1}
    if multi_reading:
        for char, readings in multi_reading.items():
            report.issues.append(Issue("info", "polyphone_multi_reading",
                                       f"'{char}' 本文档中出现 {len(readings)} 种读音: {readings}", "doc"))

    report.stats = {
        "paragraphs": len(paragraphs),
        "sentences": total_sents,
        "words": total_words,
        "types": dict(type_cnt),
        "highlights": dict(highlight_cnt),
        "characters": len(doc.get("characters") or []),
        "error_count": len(report.errors),
        "warn_count": len(report.warns),
    }
    return report


# ============================================================
# 遍历 / 报告
# ============================================================

def iter_doc_files(book_filter: str | None = None) -> Iterator[Path]:
    for book_dir in BOOKS_DIR.iterdir():
        if not book_dir.is_dir():
            continue
        if book_filter and book_dir.name != book_filter:
            continue
        docs_dir = book_dir / "documents"
        if not docs_dir.exists():
            continue
        for f in docs_dir.rglob("*.json"):
            yield f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", help="仅校验某本书（如 shiji, guwenguanzhi）")
    ap.add_argument("--fix", action="store_true",
                    help="输出需要重跑的文件清单到 data/rerun_list.json")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    reports: list[FileReport] = []
    for f in iter_doc_files(args.book):
        try:
            doc = json.loads(f.read_text("utf-8"))
        except Exception as e:
            print(f"❌ 无法解析 {f}: {e}", file=sys.stderr)
            continue
        reports.append(validate_document(doc, f))

    # 汇总
    total_files = len(reports)
    total_errors = sum(len(r.errors) for r in reports)
    total_warns = sum(len(r.warns) for r in reports)
    files_with_errors = sum(1 for r in reports if r.errors)
    files_need_rerun = [r for r in reports if r.needs_rerun]

    # 按 issue code 聚类
    code_cnt: Counter = Counter()
    for r in reports:
        for i in r.issues:
            code_cnt[i.code] += 1

    # 全局 type 分布
    global_types: Counter = Counter()
    for r in reports:
        for t, c in r.stats.get("types", {}).items():
            global_types[t] += c
    invalid_type_cnt = {t: c for t, c in global_types.items() if t not in VALID_TYPES}

    # 全局 highlight 分布
    global_highlights: Counter = Counter()
    for r in reports:
        for h, c in r.stats.get("highlights", {}).items():
            global_highlights[h] += c

    # 人物卡覆盖统计
    with_chars = sum(1 for r in reports if r.stats.get("characters", 0) > 0)
    without_chars = total_files - with_chars

    print("=" * 60)
    print(f"📋 Schema 校验报告")
    print("=" * 60)
    print(f"文件总数:           {total_files}")
    print(f"有错误的文件:       {files_with_errors}")
    print(f"错误总数:           {total_errors}")
    print(f"警告总数:           {total_warns}")
    print(f"需要重跑的文件:     {len(files_need_rerun)}")
    print()

    print("Issue 分类 TOP 10:")
    for code, cnt in code_cnt.most_common(10):
        print(f"  {cnt:6d}  {code}")
    print()

    print(f"type 字段使用情况（合法 6 种 + 非法 {len(invalid_type_cnt)} 种）:")
    for t, c in sorted(global_types.items(), key=lambda x: -x[1])[:20]:
        mark = "✅" if t in VALID_TYPES else "❌"
        print(f"  {mark} {t:10s} {c:8d}")
    print()

    print(f"highlight 字段分布:")
    for h, c in sorted(global_highlights.items(), key=lambda x: -x[1]):
        mark = "✅" if h in VALID_HIGHLIGHTS else "❌"
        print(f"  {mark} {h:14s} {c:8d}")
    print()

    print(f"人物卡（characters）覆盖:")
    print(f"  有人物卡: {with_chars} / 无人物卡: {without_chars}")
    print()

    if args.verbose:
        print("Top 20 问题文件:")
        worst = sorted(reports, key=lambda r: -len(r.errors))[:20]
        for r in worst:
            if not r.errors:
                break
            print(f"  {len(r.errors):3d} err / {len(r.warns):3d} warn  {r.path}")

    # 输出重跑清单
    if args.fix:
        rerun_list = sorted([r.path for r in files_need_rerun])
        out = BASE_DIR / "data" / "rerun_list.json"
        out.write_text(json.dumps({
            "generated_at": str(Path(__file__).stat().st_mtime),
            "count": len(rerun_list),
            "files": rerun_list,
        }, ensure_ascii=False, indent=2), "utf-8")
        print(f"💾 重跑清单已写入: {out} ({len(rerun_list)} 文件)")

    # 保存完整 JSON 报告
    full = {
        "summary": {
            "total_files": total_files,
            "files_with_errors": files_with_errors,
            "total_errors": total_errors,
            "total_warns": total_warns,
            "files_need_rerun": len(files_need_rerun),
            "issue_code_counts": dict(code_cnt.most_common()),
            "type_counts": dict(global_types),
            "invalid_type_counts": invalid_type_cnt,
        },
        "files": [
            {
                "path": r.path,
                "errors": len(r.errors),
                "warns": len(r.warns),
                "stats": r.stats,
                "issues": [
                    {"severity": i.severity, "code": i.code,
                     "message": i.message, "location": i.location}
                    for i in r.issues[:20]  # 每文件最多 20 条
                ],
            }
            for r in reports
        ],
    }
    (BASE_DIR / "data" / "validation_report.json").write_text(
        json.dumps(full, ensure_ascii=False, indent=2), "utf-8")

    # 退出码：有 error 非 0
    sys.exit(1 if total_errors > 0 else 0)


if __name__ == "__main__":
    main()
