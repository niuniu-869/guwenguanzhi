"""corpus.sqlite 共享工具。供 search.py / cite.py / lookup.py 等脚本复用。

核心设计：Python 默认 sqlite3 的 FTS5 tokenizer 对中文无效（无法按字切词），
因此入库前把中文文本预切成 bigram 空格串（"管仲者" → "管仲 仲者"），
FTS 索引使用 unicode61 按空格切，查询时对 query 做同样转换。
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
CORPUS_DB = SKILL_ROOT / "data" / "corpus.sqlite"


def require_corpus() -> sqlite3.Connection:
    """打开 corpus.sqlite；不存在则给出明确错误并退出。"""
    if not CORPUS_DB.exists():
        print(
            f"[fatal] 找不到 {CORPUS_DB}\n"
            "  请先运行：\n"
            "    bash skill/scripts/vendor/pull_all.sh\n"
            "    python skill/scripts/build_corpus.py",
            file=sys.stderr,
        )
        sys.exit(2)
    conn = sqlite3.connect(CORPUS_DB)
    conn.row_factory = sqlite3.Row
    return conn


def format_citation(row: sqlite3.Row | dict[str, Any]) -> str:
    """把一行记录格式化为规范引用标签【书·卷N·卷名·段M】。"""
    return f"【{row['book_name']}·卷{row['juan']:03d}·{row['juan_name']}·段{row['segment']:03d}】"


# --------- 中文 bigram 索引 ---------

_CJK_RANGES = (
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0x3400, 0x4DBF),   # CJK Extension A
    (0xF900, 0xFAFF),   # CJK Compatibility Ideographs
)


def is_cjk(ch: str) -> bool:
    """是否中文汉字（含扩展区）。"""
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _CJK_RANGES)


def to_bigrams(text: str) -> str:
    """把文本切成 bigram 空格串，用于 FTS unicode61 索引。

    规则：
      - 只对相邻的 2 个汉字组 bigram
      - 非汉字字符（标点/空白）作为分隔符，切断 bigram 链
      - 单字段保留（便于单字搜索）

    Examples:
        "管仲者，颍上人也" → "管仲 仲者 颍上 上人 人也"
        "鸿门宴上"         → "鸿门 门宴 宴上"
    """
    chunks: list[str] = []
    current: list[str] = []
    for ch in text:
        if is_cjk(ch):
            current.append(ch)
        else:
            if current:
                chunks.append("".join(current))
                current = []
    if current:
        chunks.append("".join(current))

    bigrams: list[str] = []
    for chunk in chunks:
        if len(chunk) == 1:
            bigrams.append(chunk)  # 单字保留
        else:
            for i in range(len(chunk) - 1):
                bigrams.append(chunk[i : i + 2])
    return " ".join(bigrams)


def query_to_fts(query: str) -> str:
    """把用户查询字符串转换为 FTS5 MATCH 表达式。

    规则：
      - 双引号短语："民为贵" → "民为 为贵"（所有 bigram 必须相邻，近似短语匹配）
      - 单独多字词：管仲 → "管仲"
      - 多字短语（无引号）：鸿门宴 → "鸿门 门宴"（AND，近似短语匹配）
      - 含空格 OR 特殊符号：透传
      - 单字：原样返回（可能匹配多）
    """
    query = query.strip()
    if not query:
        return query

    # 保留 FTS5 操作符
    if any(op in query for op in [" OR ", " AND ", " NOT "]):
        return query

    # 双引号短语
    m = re.fullmatch(r'"(.+)"', query)
    if m:
        inner = m.group(1)
        bigrams = to_bigrams(inner)
        if not bigrams:
            return query
        # 用双引号让 unicode61 按空格切成一整个短语
        return f'"{bigrams}"'

    # 空格分隔的多个词 → 各自 bigram + AND（FTS5 默认 AND）
    if " " in query:
        parts = [to_bigrams(p) for p in query.split() if p.strip()]
        return " ".join(f'({p})' for p in parts if p)

    # 单个词
    return to_bigrams(query)


def parse_urn(urn: str) -> tuple[str, int, int] | None:
    """把 URN 字符串解析为 (book_id, juan, segment)。

    支持两种格式：
      - "shiji/006/003"
      - "shiji/6/3"
    不合法返回 None。
    """
    parts = urn.strip().split("/")
    if len(parts) != 3:
        return None
    book_id = parts[0].strip()
    try:
        juan = int(parts[1])
        segment = int(parts[2])
    except ValueError:
        return None
    if not book_id or juan < 0 or segment < 0:
        return None
    return book_id, juan, segment
