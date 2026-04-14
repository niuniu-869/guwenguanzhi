#!/usr/bin/env python3
"""历史咨询：现代情境 → 若干历史先例（advisory_fts）。

用法：
    python skill/scripts/analogy.py "合伙人理念不合"
    python skill/scripts/analogy.py "接班人选择" --limit 5
    python skill/scripts/analogy.py "跨文化管理" --json
    python skill/scripts/analogy.py "权力交接" --book shiji

输出：
  每条命中返回 { scenario, 出处卷, title, 相关历史事件/人物 }，按 bm25 排序。
  附带三标签说明【史实 / 演绎 / 推断】使用约定。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from _corpus import query_to_fts  # noqa: E402

METADATA_DB = SCRIPT_DIR.parent / "data" / "metadata.sqlite"


def require_metadata() -> sqlite3.Connection:
    if not METADATA_DB.exists():
        print(f"[fatal] 找不到 {METADATA_DB}\n  先运行 build_index.py", file=sys.stderr)
        sys.exit(2)
    conn = sqlite3.connect(METADATA_DB)
    conn.row_factory = sqlite3.Row
    return conn


def find_analogies(
    conn: sqlite3.Connection, query: str, limit: int = 10, book: str | None = None,
) -> list[dict]:
    fts_q = query_to_fts(query)
    sql = (
        "SELECT a.book_id, a.sub_type, a.sub_index, a.scenario, "
        "       j.juan AS juan, j.title, j.juan_name, j.summary, j.historical_period, "
        "       j.appreciation, bm25(advisory_fts) AS score "
        "FROM advisory_fts "
        "JOIN advisory_items a ON a.id = advisory_fts.rowid "
        "LEFT JOIN juans j ON j.book_id = a.book_id "
        "  AND (j.sub_type = a.sub_type OR (j.sub_type IS NULL AND a.sub_type IS NULL)) "
        "  AND j.sub_index = a.sub_index "
        "WHERE advisory_fts MATCH ? "
    )
    params: list[object] = [fts_q]
    if book:
        sql += "AND a.book_id = ? "
        params.append(book)
    sql += "ORDER BY score LIMIT ?"
    params.append(limit)
    cur = conn.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def render(rows: list[dict], query: str, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"query": query, "count": len(rows), "cases": rows},
                          ensure_ascii=False, indent=2))
        return
    if not rows:
        print(f"⛔ 现代情境 {query!r} 在 advisory 库未命中")
        print("   → agent 应改用【推断·建议】标签，不得杜撰历史先例")
        sys.exit(3)
    print(f"✅ 现代情境 {query!r} → {len(rows)} 条历史先例：\n")
    for i, r in enumerate(rows, 1):
        if r["sub_type"]:
            st = f"{r['sub_type']}/{r['sub_index']:03d}"
        else:
            st = f"juan/{r.get('juan') or '-'}"
        title = (r.get("title") or "").strip()
        period = (r.get("historical_period") or "").strip()
        print(f"[{i}] 【{r['book_id']}·{st}】 {title}   ({period})")
        print(f"    场景: {r['scenario']}")
        summary = (r.get("summary") or "").strip()
        if summary:
            print(f"    卷要: {summary[:120]}{'…' if len(summary) > 120 else ''}")
        print()
    print("──────────")
    print("输出原则（agent 必读）：")
    print("  ① 【史实】：引用原文或事件用 cite.py 校验后标注 (URN)")
    print("  ② 【演绎】：从史实推出的现代对应，必须说明原事件")
    print("  ③ 【推断·建议】：若无直接史实支撑，禁用'古人言/史载'措辞")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", help="现代情境描述（如『合伙人理念不合』）")
    parser.add_argument("--limit", type=int, default=8, help="返回条数")
    parser.add_argument("--book", help="限定某本书（如 shiji）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    conn = require_metadata()
    try:
        rows = find_analogies(conn, args.query, args.limit, args.book)
        render(rows, args.query, args.json)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
