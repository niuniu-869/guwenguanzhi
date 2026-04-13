#!/usr/bin/env python3
"""
A/B 测试 words prompt v2
- 挑选代表性句子（覆盖质检发现的问题模式）
- 用 v2 prompt 重新生成
- 对比 v1 原输出与 v2 新输出
- 用 validate_schema 逐项校验

使用：
  python3 scripts/ab_test_words.py                  # 跑默认 5 篇代表性测试
  python3 scripts/ab_test_words.py --save           # 保存 v2 输出到 data/ab_test/
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm_client import call_llm_json  # noqa: E402
from prompts import load_prompt, PROMPT_VERSION  # noqa: E402
from validate_schema import validate_sentence  # noqa: E402

BASE_DIR = Path(__file__).parent.parent

# ============================================================
# 测试样本：挑选质检发现的问题案例
# ============================================================

TEST_CASES = [
    {
        "book": "guwenguanzhi",
        "doc": "pre_qin/001_郑伯克段于鄢",
        "title": "郑伯克段于鄢",
        "author": "左丘明",
        "target_paragraph_idx": 0,
        "target_sentence_indices": [0, 2, 4],
        "focus": "通假字(弟/悌)、多音字(亟/大叔)、虚词语境化(之)",
    },
    {
        "book": "guwenguanzhi",
        "doc": "pre_qin/008_曹刿论战",
        "title": "曹刿论战",
        "author": "左丘明",
        "target_paragraph_idx": 1,
        "target_sentence_indices": [0, 1, 2],
        "focus": "古今异义(加=虚报)、专名(牺牲)",
    },
    {
        "book": "guwenguanzhi",
        "doc": "tang/118_阿房宫赋",
        "title": "阿房宫赋",
        "author": "杜牧",
        "target_paragraph_idx": 0,
        "target_sentence_indices": [0, 1, 2],
        "focus": "赋体专名密度、古今异义(走)",
    },
    {
        "book": "guwenguanzhi",
        "doc": "ming/208_卖柑者言",
        "title": "卖柑者言",
        "author": "刘基",
        "target_paragraph_idx": 2,
        "target_sentence_indices": [0, 1],
        "focus": "通假字(授=受)",
    },
    {
        "book": "shiji",
        "doc": "007",
        "title": "项羽本纪",
        "author": "司马迁",
        "target_paragraph_idx": None,  # 动态挑"鸿门宴"附近
        "target_sentence_indices": None,
        "focus": "多音字(骑)、词组合并异常",
    },
]


def load_doc(book: str, doc_id: str) -> dict:
    path = BASE_DIR / "data" / "books" / book / "documents" / f"{doc_id}.json"
    return json.loads(path.read_text("utf-8"))


def pick_target_sentences(doc: dict, para_idx: int | None,
                          sent_indices: list | None) -> tuple[dict, list[dict], dict]:
    """返回 (段落, 句子列表, v1 词注释 dict)"""
    paragraphs = doc.get("paragraphs", [])
    if para_idx is None:
        # 找包含"骑"字最多的段
        best_idx, best_count = 0, 0
        for i, p in enumerate(paragraphs):
            text = p.get("original", "")
            c = text.count("骑")
            if c > best_count:
                best_count = c
                best_idx = i
        para_idx = best_idx

    para = paragraphs[para_idx]
    sents = para.get("sentences", [])
    if sent_indices is None:
        # 取前 3 句
        sent_indices = list(range(min(3, len(sents))))

    picked = [sents[i] for i in sent_indices if i < len(sents)]
    v1_annotations = {s["original"]: s.get("words", []) for s in picked}
    return para, picked, v1_annotations


def call_v2(title: str, author: str, paragraph: str, sentences: list[dict]) -> dict:
    """调用 v2 prompt 生成词注释"""
    sentences_block = "\n".join(
        f'{i + 1}. "{s["original"]}"' for i, s in enumerate(sentences)
    )
    system = load_prompt("words/system.md")
    user = load_prompt("words/user.md",
                       title=title, author=author,
                       paragraph=paragraph, sentences_block=sentences_block)
    return call_llm_json(system, user)


def score_sentence(sent: dict, v1_or_v2: str) -> dict:
    """用 validate_schema 给一个句子打分"""
    issues = validate_sentence(sent, "")
    errors = [i for i in issues if i.severity == "error"]
    warns = [i for i in issues if i.severity == "warn"]

    # 统计虚词空泛
    vague_xuci = 0
    from validate_schema import VAGUE_MEANINGS
    for w in sent.get("words", []):
        if w.get("type") == "虚词" and w.get("meaning", "").strip() in VAGUE_MEANINGS:
            vague_xuci += 1

    # 统计非法 type
    from validate_schema import VALID_TYPES
    invalid_type = sum(1 for w in sent.get("words", [])
                       if w.get("type") not in VALID_TYPES)

    return {
        "version": v1_or_v2,
        "word_count": len(sent.get("words", [])),
        "errors": len(errors),
        "warns": len(warns),
        "vague_xuci": vague_xuci,
        "invalid_type": invalid_type,
        "error_codes": [i.code for i in errors],
    }


def diff_sentences(orig: str, v1_words: list, v2_words: list) -> dict:
    """对比 v1/v2 的词注释差异"""
    v1_set = {w.get("word", ""): w for w in v1_words}
    v2_set = {w.get("word", ""): w for w in v2_words}

    v1_only = set(v1_set) - set(v2_set)
    v2_only = set(v2_set) - set(v1_set)
    common = set(v1_set) & set(v2_set)

    changed = {}
    for w in common:
        if v1_set[w].get("meaning") != v2_set[w].get("meaning") or \
           v1_set[w].get("pinyin") != v2_set[w].get("pinyin") or \
           v1_set[w].get("type") != v2_set[w].get("type"):
            changed[w] = {
                "v1": v1_set[w],
                "v2": v2_set[w],
            }

    return {
        "v1_only_words": list(v1_only),
        "v2_only_words": list(v2_only),
        "changed": changed,
    }


def run_case(case: dict) -> dict:
    print(f"\n{'='*70}")
    print(f"📖 {case['title']} ({case['book']}/{case['doc']})")
    print(f"   聚焦: {case['focus']}")
    print('='*70, flush=True)

    doc = load_doc(case["book"], case["doc"])
    para, picked, v1_map = pick_target_sentences(
        doc, case["target_paragraph_idx"], case["target_sentence_indices"]
    )

    # 调用 v2
    t0 = time.time()
    try:
        v2_result = call_v2(case["title"], case["author"],
                            para.get("original", ""), picked)
    except Exception as e:
        print(f"❌ v2 调用失败: {e}")
        return {"case": case["title"], "error": str(e)}
    elapsed = time.time() - t0

    v2_sentences = v2_result.get("sentences", [])
    v2_map = {s.get("original", ""): s.get("words", []) for s in v2_sentences}

    # 逐句打分对比
    results = []
    for orig_sent in picked:
        orig_text = orig_sent["original"]
        v1_words = v1_map.get(orig_text, [])
        v2_words = v2_map.get(orig_text, [])

        v1_sent = {"original": orig_text, "words": v1_words}
        v2_sent = {"original": orig_text, "words": v2_words}

        v1_score = score_sentence(v1_sent, "v1")
        v2_score = score_sentence(v2_sent, "v2")
        diff = diff_sentences(orig_text, v1_words, v2_words)

        results.append({
            "original": orig_text,
            "v1_score": v1_score,
            "v2_score": v2_score,
            "diff": diff,
        })

        # 打印摘要
        print(f"\n  📝 {orig_text[:40]}")
        print(f"     v1: 词{v1_score['word_count']:3d}  err{v1_score['errors']}  warn{v1_score['warns']}  "
              f"非法type{v1_score['invalid_type']}  空泛虚词{v1_score['vague_xuci']}")
        print(f"     v2: 词{v2_score['word_count']:3d}  err{v2_score['errors']}  warn{v2_score['warns']}  "
              f"非法type{v2_score['invalid_type']}  空泛虚词{v2_score['vague_xuci']}")

        # 展示典型差异（改进的词）
        if diff["changed"]:
            print(f"     变更词例（最多展示3个）:")
            for w, c in list(diff["changed"].items())[:3]:
                print(f"       『{w}』")
                print(f"         v1: {c['v1'].get('pinyin','')} | {c['v1'].get('meaning','')} [{c['v1'].get('type','')}]")
                print(f"         v2: {c['v2'].get('pinyin','')} | {c['v2'].get('meaning','')} [{c['v2'].get('type','')}]")

    print(f"\n  ⏱ v2 耗时: {elapsed:.1f}s")
    return {
        "case": case["title"],
        "focus": case["focus"],
        "elapsed": elapsed,
        "sentences": results,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true", help="保存 v2 输出到 data/ab_test/")
    args = ap.parse_args()

    print(f"🧪 A/B 测试 · prompt v2 = {PROMPT_VERSION}")
    print(f"   测试样本: {len(TEST_CASES)}")

    t_start = time.time()
    all_results = []
    for case in TEST_CASES:
        try:
            all_results.append(run_case(case))
        except Exception as e:
            print(f"❌ 用例失败 {case['title']}: {e}")
            all_results.append({"case": case["title"], "error": str(e)})

    # 汇总
    print(f"\n{'='*70}")
    print("📊 总结")
    print('='*70)

    total_v1_errors = total_v2_errors = 0
    total_v1_warns = total_v2_warns = 0
    total_v1_vague = total_v2_vague = 0
    total_v1_invalid = total_v2_invalid = 0

    for r in all_results:
        if "error" in r:
            continue
        for s in r.get("sentences", []):
            total_v1_errors += s["v1_score"]["errors"]
            total_v2_errors += s["v2_score"]["errors"]
            total_v1_warns += s["v1_score"]["warns"]
            total_v2_warns += s["v2_score"]["warns"]
            total_v1_vague += s["v1_score"]["vague_xuci"]
            total_v2_vague += s["v2_score"]["vague_xuci"]
            total_v1_invalid += s["v1_score"]["invalid_type"]
            total_v2_invalid += s["v2_score"]["invalid_type"]

    def pct(old, new):
        if old == 0:
            return "--" if new == 0 else f"+{new}"
        chg = (new - old) / old * 100
        return f"{chg:+.0f}%"

    print(f"\n{'指标':20s} {'v1':>8s} {'v2':>8s} {'变化':>10s}")
    print(f"{'-'*50}")
    print(f"{'错误数':20s} {total_v1_errors:>8d} {total_v2_errors:>8d} {pct(total_v1_errors, total_v2_errors):>10s}")
    print(f"{'警告数':20s} {total_v1_warns:>8d} {total_v2_warns:>8d} {pct(total_v1_warns, total_v2_warns):>10s}")
    print(f"{'虚词空泛释义':20s} {total_v1_vague:>8d} {total_v2_vague:>8d} {pct(total_v1_vague, total_v2_vague):>10s}")
    print(f"{'非法 type':20s} {total_v1_invalid:>8d} {total_v2_invalid:>8d} {pct(total_v1_invalid, total_v2_invalid):>10s}")

    print(f"\n⏱ 总耗时: {time.time() - t_start:.1f}s")

    if args.save:
        out = BASE_DIR / "data" / "ab_test_result.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), "utf-8")
        print(f"💾 完整结果: {out}")


if __name__ == "__main__":
    main()
