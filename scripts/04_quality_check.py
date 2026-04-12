#!/usr/bin/env python3
"""
质量抽检脚本：
1. 检查所有文章 JSON 的结构完整性
2. 验证词注释覆盖率
3. 重点抽检长篇文章
4. 输出质量报告
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CATALOG_FILE = BASE_DIR / "data" / "catalog.json"

DYNASTY_NAMES = {
    "pre_qin": "先秦", "han": "两汉", "wei_jin": "魏晋南北朝",
    "tang": "唐", "song": "宋", "ming": "明",
}


def check_article(filepath: Path) -> dict:
    """检查单篇文章的质量"""
    d = json.loads(filepath.read_text("utf-8"))
    title = d.get("title", "?")
    paras = d.get("paragraphs", [])

    total_sentences = sum(len(p.get("sentences", [])) for p in paras)
    total_words = sum(len(s.get("words", [])) for p in paras for s in p.get("sentences", []))

    # 检查各字段是否存在
    has_bg = bool(d.get("background"))
    has_app = bool(d.get("appreciation"))
    has_bio = bool(d.get("author", {}).get("bio"))

    # 空翻译
    empty_trans = sum(1 for p in paras for s in p.get("sentences", []) if not s.get("translation"))

    # 空词注释
    empty_words = sum(1 for p in paras for s in p.get("sentences", []) if not s.get("words"))

    # 词覆盖率检查
    coverage_issues = []
    for p in paras:
        for s in p.get("sentences", []):
            words = s.get("words", [])
            if not words:
                continue
            # 拼接所有 word，去掉标点后对比原文（也去掉标点）
            reconstructed = "".join(w["word"] for w in words)
            original = s.get("original", "")
            # 简化比较：去掉所有标点
            punct = "，。、；：？！""''《》（）【】—…·\n "
            orig_clean = "".join(c for c in original if c not in punct)
            recon_clean = "".join(c for c in reconstructed if c not in punct)
            if orig_clean != recon_clean:
                coverage_issues.append({
                    "original": original[:40],
                    "expected": orig_clean[:30],
                    "got": recon_clean[:30],
                })

    # 原文字符总数（用于判断文章长度）
    total_chars = sum(len(p.get("original", "")) for p in paras)

    return {
        "title": title,
        "file": str(filepath.name),
        "chars": total_chars,
        "paragraphs": len(paras),
        "sentences": total_sentences,
        "words": total_words,
        "has_background": has_bg,
        "has_appreciation": has_app,
        "has_author_bio": has_bio,
        "empty_translations": empty_trans,
        "empty_word_annotations": empty_words,
        "coverage_issues": len(coverage_issues),
        "coverage_details": coverage_issues[:3],  # 只保留前3个
        "quality_score": 0,  # 下面计算
    }


def compute_score(r: dict) -> float:
    """计算质量分 0-100"""
    score = 100
    # 缺少元数据
    if not r["has_background"]: score -= 10
    if not r["has_appreciation"]: score -= 10
    if not r["has_author_bio"]: score -= 5
    # 空翻译
    if r["sentences"] > 0:
        score -= (r["empty_translations"] / r["sentences"]) * 30
    # 空词注释
    if r["sentences"] > 0:
        score -= (r["empty_word_annotations"] / r["sentences"]) * 30
    # 覆盖率问题
    annotated = r["sentences"] - r["empty_word_annotations"]
    if annotated > 0:
        score -= (r["coverage_issues"] / annotated) * 15
    return max(0, round(score, 1))


def main():
    print("=" * 60)
    print("📋 质量抽检报告")
    print("=" * 60)

    catalog = json.loads(CATALOG_FILE.read_text("utf-8"))

    all_results = []
    missing = 0

    for dynasty in catalog["dynasties"]:
        did = dynasty["id"]
        for author in dynasty["authors"]:
            for article in author["articles"]:
                aid = article["id"]
                f = BASE_DIR / "data" / "articles" / did / f"{aid}.json"
                if f.exists():
                    r = check_article(f)
                    r["dynasty"] = DYNASTY_NAMES.get(did, did)
                    r["quality_score"] = compute_score(r)
                    all_results.append(r)
                else:
                    missing += 1

    total = len(all_results)
    if total == 0:
        print("没有找到已完成的文章 JSON")
        return

    # 总体统计
    avg_score = sum(r["quality_score"] for r in all_results) / total
    perfect = sum(1 for r in all_results if r["quality_score"] >= 95)
    good = sum(1 for r in all_results if 80 <= r["quality_score"] < 95)
    poor = sum(1 for r in all_results if r["quality_score"] < 80)

    print(f"\n📊 总体统计:")
    print(f"   已完成: {total}/222, 缺失: {missing}")
    print(f"   平均质量分: {avg_score:.1f}/100")
    print(f"   优秀(≥95): {perfect}, 良好(80-94): {good}, 差(<80): {poor}")

    # 按朝代统计
    print(f"\n📖 按朝代:")
    by_dynasty = {}
    for r in all_results:
        by_dynasty.setdefault(r["dynasty"], []).append(r)
    for dynasty, articles in by_dynasty.items():
        avg = sum(r["quality_score"] for r in articles) / len(articles)
        print(f"   {dynasty}: {len(articles)}篇, 平均 {avg:.1f}分")

    # 最差的 10 篇
    worst = sorted(all_results, key=lambda r: r["quality_score"])[:10]
    print(f"\n⚠️ 质量最差的 10 篇:")
    for r in worst:
        print(f"   {r['quality_score']:5.1f} | {r['dynasty']} | {r['title']} "
              f"({r['chars']}字) 空翻译:{r['empty_translations']} 空词:{r['empty_word_annotations']} 覆盖偏差:{r['coverage_issues']}")

    # 长篇重点抽检（字数最多的 10 篇）
    longest = sorted(all_results, key=lambda r: -r["chars"])[:10]
    print(f"\n📏 最长的 10 篇:")
    for r in longest:
        print(f"   {r['quality_score']:5.1f} | {r['chars']:4d}字 | {r['title']} "
              f"句:{r['sentences']} 词:{r['words']}")

    # 保存报告
    report = {
        "total": total,
        "missing": missing,
        "avg_score": avg_score,
        "perfect": perfect,
        "good": good,
        "poor": poor,
        "articles": all_results,
    }
    report_file = BASE_DIR / "data" / "quality_report.json"
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(f"\n💾 完整报告: {report_file}")


if __name__ == "__main__":
    main()
