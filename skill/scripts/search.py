#!/usr/bin/env python3
"""全文检索：FTS5 + trigram 分词，支持短语/布尔/书目过滤。

用法：
    python skill/scripts/search.py "管仲"
    python skill/scripts/search.py "管仲 鲍叔" --limit 20      # 空格 = AND
    python skill/scripts/search.py '"民为贵"' --limit 5        # 双引号 = 短语精确
    python skill/scripts/search.py "商鞅" --book shiji         # 限书目
    python skill/scripts/search.py "诸葛亮" --json              # JSON 输出

输出默认为可读表格；--json 给 agent 调用。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from _corpus import require_corpus, format_citation, query_to_fts

SNIPPET_CHARS = 80  # 命中上下文字数


def search(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 10,
    book: str | None = None,
    include_commentary: bool = False,
) -> list[dict]:
    """在 FTS5 上执行查询，返回命中列表。

    FTS5 查询语法：
      - "管仲"     → 精确短语（双引号）
      - 管仲       → 按 trigram 切 → 管+仲 (三元组索引自动匹配相邻)
      - 管仲 鲍叔  → AND
      - 管仲 OR 鲍叔
    """
    # 用户的中文查询 → bigram 空格串（unicode61 tokenizer 能用）
    fts_query = query_to_fts(query)
    sql_parts = [
        "SELECT d.id, d.book_id, d.book_name, d.juan, d.juan_name, "
        "       d.segment, d.text, d.urn, d.book_type, bm25(documents_fts) AS rank "
        "FROM documents_fts "
        "JOIN documents d ON d.id = documents_fts.rowid "
        "WHERE documents_fts MATCH ? "
    ]
    params: list[object] = [fts_query]

    if book:
        sql_parts.append("AND d.book_id = ? ")
        params.append(book)

    if not include_commentary:
        sql_parts.append("AND d.book_type != 'commentary' ")

    sql_parts.append("ORDER BY rank LIMIT ?")
    params.append(limit)

    cur = conn.execute(" ".join(sql_parts), params)
    rows = cur.fetchall()

    # 手动生成命中 snippet（text_ngram 不适合直接显示，故从 text 取）
    def _snippet(text: str, q: str, ctx: int = SNIPPET_CHARS) -> str:
        # 找 query 原始字符串中任一 bigram 在 text 中的首次出现
        probes = [q[i:i+2] for i in range(len(q) - 1)] if len(q) >= 2 else [q]
        best = -1
        for p in probes:
            idx = text.find(p)
            if idx >= 0 and (best < 0 or idx < best):
                best = idx
        if best < 0:
            return text[:ctx] + ("..." if len(text) > ctx else "")
        start = max(0, best - ctx // 2)
        end = min(len(text), best + ctx // 2)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(text) else ""
        return prefix + text[start:end] + suffix

    return [
        {
            "urn": row["urn"],
            "book_id": row["book_id"],
            "book_name": row["book_name"],
            "juan": row["juan"],
            "juan_name": row["juan_name"],
            "segment": row["segment"],
            "snippet": _snippet(row["text"], query),
            "rank": row["rank"],
            "citation": format_citation(row),
            "book_type": row["book_type"] if "book_type" in row.keys() else "zhengshi",
        }
        for row in rows
    ]


def render_table(hits: list[dict]) -> str:
    if not hits:
        return "（无命中）"
    lines = []
    for i, h in enumerate(hits, 1):
        lines.append(f"{i}. {h['citation']}")
        lines.append(f"   {h['snippet']}")
        lines.append(f"   urn: {h['urn']}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", help="FTS5 查询字符串")
    parser.add_argument("--limit", type=int, default=10, help="最大返回数（默认 10）")
    parser.add_argument("--book", type=str, help="限定 book_id（如 shiji）")
    parser.add_argument("--include-commentary", action="store_true",
                        help="把史评/考异类（book_type=commentary）一并纳入搜索")
    parser.add_argument("--json", action="store_true", help="输出 JSON（供 agent 调用）")
    args = parser.parse_args()

    conn = require_corpus()
    try:
        hits = search(conn, args.query, limit=args.limit, book=args.book,
                      include_commentary=args.include_commentary)
    except sqlite3.OperationalError as e:
        print(f"[fatal] FTS5 查询错误：{e}", file=sys.stderr)
        print("  提示：短语用双引号包裹，如 '\"民为贵\"'", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

    if args.json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
    else:
        print(f"查询: {args.query!r}  命中: {len(hits)}")
        print("-" * 60)
        print(render_table(hits))


if __name__ == "__main__":
    main()
