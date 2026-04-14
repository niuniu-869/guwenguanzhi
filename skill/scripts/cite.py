#!/usr/bin/env python3
"""原文引用校验器。给定 URN 或待校验片段，返回规范【书·卷·段】引用 + 原文。

用法：
    python skill/scripts/cite.py shiji/006/001             # URN 格式
    python skill/scripts/cite.py "shiji/6/1"                # 非零填充也接受
    python skill/scripts/cite.py --verify "民为贵社稷次之"  # 校验片段是否在库
    python skill/scripts/cite.py --verify "君子之交淡若水" --strict

场景：
  - agent 要引用原文前调此脚本，不存在则拒答（反幻觉）
  - --verify 支持片段校验：若片段在某处原文出现则返回命中，否则返回 {"found": false}
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from _corpus import require_corpus, format_citation, parse_urn, query_to_fts


def lookup_by_urn(conn: sqlite3.Connection, book_id: str, juan: int, segment: int) -> dict | None:
    cur = conn.execute(
        "SELECT book_id, book_name, juan, juan_name, segment, text, urn "
        "FROM documents "
        "WHERE book_id = ? AND juan = ? AND segment = ? "
        "LIMIT 1",
        (book_id, juan, segment),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "urn": row["urn"],
        "book_id": row["book_id"],
        "book_name": row["book_name"],
        "juan": row["juan"],
        "juan_name": row["juan_name"],
        "segment": row["segment"],
        "text": row["text"],
        "citation": format_citation(row),
    }


def verify_phrase(conn: sqlite3.Connection, phrase: str, strict: bool = False) -> list[dict]:
    """校验一个片段是否存在于语料库中。

    非严格模式：trigram FTS 查询，允许部分匹配
    严格模式：LIKE '%phrase%' 完整连续匹配
    """
    if strict:
        cur = conn.execute(
            "SELECT book_id, book_name, juan, juan_name, segment, text, urn "
            "FROM documents "
            "WHERE text LIKE ? "
            "LIMIT 5",
            (f"%{phrase}%",),
        )
    else:
        # 非严格：用 bigram FTS 查近似短语
        fts_query = query_to_fts(f'"{phrase}"')
        cur = conn.execute(
            "SELECT d.book_id, d.book_name, d.juan, d.juan_name, "
            "       d.segment, d.text, d.urn "
            "FROM documents_fts JOIN documents d ON d.id = documents_fts.rowid "
            "WHERE documents_fts MATCH ? "
            "ORDER BY bm25(documents_fts) LIMIT 5",
            (fts_query,),
        )

    rows = cur.fetchall()
    return [
        {
            "urn": r["urn"],
            "book_name": r["book_name"],
            "juan": r["juan"],
            "juan_name": r["juan_name"],
            "segment": r["segment"],
            "text": r["text"],
            "citation": format_citation(r),
            "exact_match": phrase in r["text"],
        }
        for r in rows
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("arg", nargs="?", help="URN 或片段（配合 --verify）")
    parser.add_argument("--verify", type=str, help="校验片段是否在库")
    parser.add_argument("--strict", action="store_true", help="严格连续匹配（配合 --verify）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    if not args.arg and not args.verify:
        parser.error("必须提供 URN 或 --verify 片段")

    conn = require_corpus()
    try:
        if args.verify:
            hits = verify_phrase(conn, args.verify, strict=args.strict)
            payload = {
                "phrase": args.verify,
                "strict": args.strict,
                "found": len(hits) > 0,
                "count": len(hits),
                "hits": hits,
            }
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                if not hits:
                    print(f"⛔ 片段 {args.verify!r} 未在语料库找到")
                    print("  → agent 应拒绝引用，或降级标注【推断】")
                    sys.exit(3)
                print(f"✅ 片段 {args.verify!r} 命中 {len(hits)} 处：")
                for i, h in enumerate(hits, 1):
                    marker = "=" if h["exact_match"] else "~"
                    print(f"  {i}. {marker} {h['citation']}")
                    print(f"     {h['text'][:100]}{'...' if len(h['text']) > 100 else ''}")
        else:
            # URN 模式
            parsed = parse_urn(args.arg)
            if not parsed:
                print(f"[fatal] URN 格式错误：{args.arg!r}", file=sys.stderr)
                print("  应为 book_id/juan/segment，如 shiji/006/001", file=sys.stderr)
                sys.exit(1)
            book_id, juan, segment = parsed
            result = lookup_by_urn(conn, book_id, juan, segment)
            if not result:
                if args.json:
                    print(json.dumps({"urn": args.arg, "found": False}, ensure_ascii=False))
                else:
                    print(f"⛔ URN {args.arg!r} 未命中")
                sys.exit(3)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(result["citation"])
                print("-" * 60)
                print(result["text"])
    finally:
        conn.close()


if __name__ == "__main__":
    main()
