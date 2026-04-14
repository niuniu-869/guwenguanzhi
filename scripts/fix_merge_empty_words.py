#!/usr/bin/env python3
"""
修复 merge 阶段因引号/空格差异造成的 words 空

根因：02b 翻译输出的 sentences[].original 可能带外部双引号（如 "若舍郑..."），
而 02c 词注输出在 batch 时 strip 了引号。两者 key 不匹配导致 word_map miss。

做法：对已 merge 的 data/articles/<dyn>/<id>.json 重新合并，查找 words 时
用 strip 引号 + normalize 空白的 key 作 fallback。

不重跑 LLM。完成后需要再跑一次 sync articles→books。
"""
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
ARTICLES = BASE / "data/articles"

QUOTE_CHARS = "\"'\u201c\u201d\u2018\u2019"


def norm(s: str) -> str:
    """标准化 key：strip 首尾引号/空白，内部空白折叠"""
    s = s.strip().strip(QUOTE_CHARS).strip()
    s = re.sub(r"\s+", "", s)
    return s


def fix_article(final_path: Path) -> int:
    """返回修复的句子数"""
    aid = final_path.stem
    dyn = final_path.parent.name
    words_path = ARTICLES / dyn / f"{aid}_words.json"
    if not words_path.exists():
        return -1

    final = json.loads(final_path.read_text("utf-8"))
    words_data = json.loads(words_path.read_text("utf-8"))

    # 建立两套 word_map：原 key + 标准化 key
    flat = []  # 按 paragraph 索引
    for para in words_data:
        if not isinstance(para, dict):
            continue
        m_exact = {}
        m_norm = {}
        for ws in para.get("sentences", []):
            orig = ws.get("original", "")
            words = ws.get("words", [])
            if not words:
                continue
            m_exact[orig] = words
            m_norm[norm(orig)] = words
        flat.append((m_exact, m_norm))

    fixed = 0
    for pi, para in enumerate(final.get("paragraphs", [])):
        if pi >= len(flat):
            continue
        m_exact, m_norm = flat[pi]
        for s in para.get("sentences", []):
            if s.get("words"):
                continue
            orig = s.get("original", "")
            words = m_exact.get(orig) or m_norm.get(norm(orig))
            if words:
                s["words"] = words
                fixed += 1
    if fixed > 0:
        final_path.write_text(
            json.dumps(final, ensure_ascii=False, indent=2), "utf-8"
        )
    return fixed


def main():
    total_fixed = 0
    total_files = 0
    for final in sorted(ARTICLES.rglob("*.json")):
        name = final.stem
        if name.endswith(("_meta", "_trans", "_words")):
            continue
        n = fix_article(final)
        if n > 0:
            total_fixed += n
            total_files += 1
            print(f"  ✅ {final.name}: 补齐 {n} 句")
        elif n == -1:
            print(f"  ⏭  {final.name}: 无 _words.json")
    print(f"\n总计：{total_files} 篇文件中补齐 {total_fixed} 句")


if __name__ == "__main__":
    main()
