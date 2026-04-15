#!/usr/bin/env python3
"""原文引用校验器。给定 URN（数字或语义）或待校验片段，返回规范【书·卷·段】引用 + 原文。

用法：
    # 数字 URN（书 / 卷号 / 段号）
    python skill/scripts/cite.py shiji/006/001
    python skill/scripts/cite.py "shiji/6/1"

    # 语义 URN（书 / 体裁 / 体裁内序号[/段号]）★Stage 1.5 新增
    python skill/scripts/cite.py shiji/世家/030          # 史记·留侯世家 全卷段1
    python skill/scripts/cite.py shiji/世家/030/003      # 史记·留侯世家 段3
    python skill/scripts/cite.py shiji/本纪/7            # 史记·项羽本纪
    python skill/scripts/cite.py mingshi/本纪/1          # 明史·太祖本纪

    # 片段校验
    python skill/scripts/cite.py --verify "民为贵社稷次之"
    python skill/scripts/cite.py --verify "君子之交淡若水" --strict

场景：
  - agent 要引用原文前调此脚本，不存在则拒答（反幻觉）
  - --verify 支持片段校验：若片段在某处原文出现则返回命中，否则返回 {"found": false}
  - 语义 URN 让"《史记·留侯世家》"这种典籍引用方式直接可达，跨书统一
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from _corpus import (
    require_corpus,
    format_citation,
    parse_urn,
    parse_semantic_urn,
    query_to_fts,
    normalize_query,
)


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "urn": row["urn"],
        "book_id": row["book_id"],
        "book_name": row["book_name"],
        "juan": row["juan"],
        "juan_name": row["juan_name"],
        "segment": row["segment"],
        "sub_type": row["sub_type"] if "sub_type" in row.keys() else None,
        "sub_index": row["sub_index"] if "sub_index" in row.keys() else None,
        "text": row["text"],
        "citation": format_citation(row),
    }


def lookup_by_urn(conn: sqlite3.Connection, book_id: str, juan: int, segment: int) -> dict | None:
    cur = conn.execute(
        "SELECT book_id, book_name, juan, juan_name, segment, sub_type, sub_index, text, urn "
        "FROM documents "
        "WHERE book_id = ? AND juan = ? AND segment = ? "
        "LIMIT 1",
        (book_id, juan, segment),
    )
    row = cur.fetchone()
    return _row_to_dict(row) if row else None


def lookup_by_semantic(
    conn: sqlite3.Connection,
    book_id: str,
    sub_type: str,
    sub_index: int,
    segment: int | None,
) -> list[dict]:
    """按 (book_id, sub_type, sub_index) 查整卷或单段。

    若 segment 给定 → 返回单段 dict 列表 (0/1 元素)
    若 segment 为 None → 返回该卷所有段（按 segment 升序）
    """
    if segment is not None:
        cur = conn.execute(
            "SELECT book_id, book_name, juan, juan_name, segment, sub_type, sub_index, text, urn "
            "FROM documents "
            "WHERE book_id = ? AND sub_type = ? AND sub_index = ? AND segment = ? "
            "LIMIT 1",
            (book_id, sub_type, sub_index, segment),
        )
    else:
        cur = conn.execute(
            "SELECT book_id, book_name, juan, juan_name, segment, sub_type, sub_index, text, urn "
            "FROM documents "
            "WHERE book_id = ? AND sub_type = ? AND sub_index = ? "
            "ORDER BY segment LIMIT 100",
            (book_id, sub_type, sub_index),
        )
    rows = cur.fetchall()
    return [_row_to_dict(r) for r in rows]


def verify_phrase(
    conn: sqlite3.Connection,
    phrase: str,
    strict: bool = False,
    include_commentary: bool = False,
) -> list[dict]:
    """校验一个片段是否存在于语料库中。

    非严格模式：bigram FTS 查询，允许部分匹配
    严格模式：LIKE '%phrase%' 完整连续匹配
    两种模式都对 phrase 做 normalize_query（繁→简）再比对，消除字形差异假阴性。
    默认排除 book_type='commentary'（史评/考异/纂误）——这些非正史原典，不应作为反幻觉引用来源。
    """
    normalized = normalize_query(phrase)
    # 默认只在 zhengshi + supplement 中校验；commentary 需显式开启
    type_filter = "" if include_commentary else " AND d.book_type != 'commentary'"
    if strict:
        cur = conn.execute(
            f"SELECT book_id, book_name, juan, juan_name, segment, text, urn, book_type "
            f"FROM documents d "
            f"WHERE text LIKE ? {type_filter} "
            f"LIMIT 5",
            (f"%{normalized}%",),
        )
    else:
        fts_query = query_to_fts(f'"{phrase}"')
        cur = conn.execute(
            f"SELECT d.book_id, d.book_name, d.juan, d.juan_name, "
            f"       d.segment, d.text, d.urn, d.book_type "
            f"FROM documents_fts JOIN documents d ON d.id = documents_fts.rowid "
            f"WHERE documents_fts MATCH ? {type_filter} "
            f"ORDER BY bm25(documents_fts) LIMIT 5",
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
            "exact_match": normalized in r["text"],
            "book_type": r["book_type"] if "book_type" in r.keys() else "zhengshi",
        }
        for r in rows
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("arg", nargs="?", help="URN 或片段（配合 --verify）")
    parser.add_argument("--verify", type=str, help="校验片段是否在库")
    parser.add_argument("--strict", action="store_true", help="严格连续匹配（配合 --verify）")
    parser.add_argument("--include-commentary", action="store_true",
                        help="允许在史评/考异类书目中校验（默认仅在正史原典中查，杜绝他人考据混入）")
    parser.add_argument("--full", action="store_true", help="输出段全文，不做长度截断")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    if not args.arg and not args.verify:
        parser.error("必须提供 URN 或 --verify 片段")

    conn = require_corpus()
    try:
        if args.verify:
            hits = verify_phrase(
                conn, args.verify,
                strict=args.strict,
                include_commentary=args.include_commentary,
            )
            normalized = normalize_query(args.verify)
            normalized_note = (
                f"（查询已归一：{args.verify!r} → {normalized!r}）"
                if normalized != args.verify
                else ""
            )
            payload = {
                "phrase": args.verify,
                "normalized": normalized,
                "strict": args.strict,
                "found": len(hits) > 0,
                "count": len(hits),
                "hits": hits,
            }
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                if not hits:
                    print(f"⛔ 片段 {args.verify!r} 未在语料库找到 {normalized_note}")
                    print("  → 不得复述原文具体字句（即使标【推断】也不行）；只能声明归属")
                    print("  建议兜底（按顺序尝试）：")
                    print(f"    1) 缩短片段：cite.py --verify '<核心 4-6 字>'")
                    print(f"    2) 关键词检索：search.py '<关键词>' --limit 10")
                    print(f"    3) 取整卷核验：cite.py <book>/<sub_type>/<N>  如 shiji/本纪/8")
                    print(f"    4) 若疑为史评/考异：加 --include-commentary")
                    print(f"    5) 仍未中 → 明示 'skill 库未收录，请他处核验'")
                    sys.exit(3)
                print(f"✅ 片段 {args.verify!r} 命中 {len(hits)} 处 {normalized_note}")
                for i, h in enumerate(hits, 1):
                    marker = "=" if h["exact_match"] else "~"
                    type_tag = "" if h.get("book_type") == "zhengshi" else f" [{h.get('book_type')}]"
                    print(f"  {i}. {marker} {h['citation']}{type_tag}")
                    print(f"     {h['text'][:100]}{'...' if len(h['text']) > 100 else ''}")
        else:
            # 优先尝试语义 URN（如 shiji/世家/030 或 shiji/世家/030/001）
            sem = parse_semantic_urn(args.arg)
            if sem:
                book_id, sub_type, sub_index, segment = sem
                results = lookup_by_semantic(conn, book_id, sub_type, sub_index, segment)
                if not results:
                    msg = f"⛔ 语义 URN {args.arg!r} 未命中（{book_id}·{sub_type}第{sub_index}）"
                    if args.json:
                        print(json.dumps({"urn": args.arg, "found": False}, ensure_ascii=False))
                    else:
                        print(msg)
                    sys.exit(3)
                if args.json:
                    payload = {"urn": args.arg, "found": True, "count": len(results), "segments": results}
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print(f"✅ 语义 URN {args.arg!r} 命中 {len(results)} 段")
                    print("-" * 60)
                    for r in results[:10]:
                        print(r["citation"])
                        text = r["text"]
                        if args.full or len(text) <= 300:
                            print(text)
                        else:
                            print(f"{text[:300]}...  （段共 {len(text)} 字，加 --full 输出全文）")
                        print()
                    if len(results) > 10:
                        print(f"...（共 {len(results)} 段，仅示前 10）")
                return

            # 回退到数字 URN
            parsed = parse_urn(args.arg)
            if not parsed:
                print(f"[fatal] URN 格式错误：{args.arg!r}", file=sys.stderr)
                print("  数字 URN: book_id/juan/segment，如 shiji/006/001", file=sys.stderr)
                print("  语义 URN: book_id/<体裁>/<序号>[/segment]，如 shiji/世家/030", file=sys.stderr)
                print("  支持的体裁: 本纪/列传/世家/志/表/书", file=sys.stderr)
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
                text = result["text"]
                if args.full or len(text) <= 500:
                    print(text)
                else:
                    print(f"{text[:500]}...  （段共 {len(text)} 字，加 --full 输出全文）")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
