#!/usr/bin/env python3
"""按年代筛事件（events.year_num）。

用法：
    # 单年
    python skill/scripts/timeline.py --year 前202
    python skill/scripts/timeline.py --year 626

    # 年代区间
    python skill/scripts/timeline.py --from -221 --to -202    # 秦末楚汉
    python skill/scripts/timeline.py --from 755 --to 763      # 安史之乱
    python skill/scripts/timeline.py --from 1363 --to 1368    # 明朝开国

    # 关键词 + 时段
    python skill/scripts/timeline.py --from 907 --to 979 --q "立国"
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
        print(f"[fatal] 找不到 {METADATA_DB}", file=sys.stderr)
        sys.exit(2)
    conn = sqlite3.connect(METADATA_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _year_to_int(y: str) -> int:
    """把 '前202' / '-202' / '200' / '220' 转成 int。"""
    y = y.strip()
    if y.startswith("前"):
        return -int(y[1:].strip())
    return int(y)


def query_timeline(
    conn: sqlite3.Connection, year_from: int, year_to: int, kw: str | None, limit: int
) -> list[dict]:
    if kw:
        fts_q = query_to_fts(kw)
        cur = conn.execute(
            "SELECT e.book_id, e.sub_type, e.sub_index, e.juan, e.name, e.year, e.year_num, e.summary, "
            "       j.title "
            "FROM events_fts "
            "JOIN events e ON e.id = events_fts.rowid "
            "LEFT JOIN juans j ON j.book_id=e.book_id AND "
            "  (j.sub_type=e.sub_type OR (j.sub_type IS NULL AND e.sub_type IS NULL)) AND "
            "  j.sub_index=e.sub_index "
            "WHERE events_fts MATCH ? AND e.year_num BETWEEN ? AND ? "
            "ORDER BY e.year_num LIMIT ?",
            (fts_q, year_from, year_to, limit),
        )
    else:
        cur = conn.execute(
            "SELECT e.book_id, e.sub_type, e.sub_index, e.juan, e.name, e.year, e.year_num, e.summary, "
            "       j.title "
            "FROM events e "
            "LEFT JOIN juans j ON j.book_id=e.book_id AND "
            "  (j.sub_type=e.sub_type OR (j.sub_type IS NULL AND e.sub_type IS NULL)) AND "
            "  j.sub_index=e.sub_index "
            "WHERE e.year_num BETWEEN ? AND ? "
            "ORDER BY e.year_num LIMIT ?",
            (year_from, year_to, limit),
        )
    return [dict(r) for r in cur.fetchall()]


def _fmt_year(n: int | None) -> str:
    if n is None:
        return "?"
    return f"前{-n}" if n < 0 else str(n)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", help="单年份（如 前202 / 626）")
    parser.add_argument("--from", dest="from_year", help="起始年（负数或『前N』为公元前）")
    parser.add_argument("--to", dest="to_year", help="结束年")
    parser.add_argument("--q", help="关键词过滤（事件名/摘要）")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.year:
        y = _year_to_int(args.year)
        year_from, year_to = y, y
    elif args.from_year and args.to_year:
        year_from = _year_to_int(args.from_year)
        year_to = _year_to_int(args.to_year)
    else:
        parser.error("需提供 --year 或 --from/--to")

    conn = require_metadata()
    try:
        rows = query_timeline(conn, year_from, year_to, args.q, args.limit)
    finally:
        conn.close()

    if args.json:
        print(json.dumps({
            "from": year_from, "to": year_to, "keyword": args.q,
            "count": len(rows), "events": rows,
        }, ensure_ascii=False, indent=2))
        return

    if not rows:
        print(f"⛔ {_fmt_year(year_from)}—{_fmt_year(year_to)} 区间无事件" + (f"（关键词 {args.q!r}）" if args.q else ""))
        sys.exit(3)
    print(f"✅ {_fmt_year(year_from)}—{_fmt_year(year_to)} 区间 {len(rows)} 条事件"
          + (f"（关键词 {args.q!r}）" if args.q else "") + "：\n")
    for r in rows:
        if r["sub_type"]:
            st = f"{r['sub_type']}/{r['sub_index']:03d}"
        else:
            st = f"juan/{r.get('juan') or '-'}"
        ys = _fmt_year(r["year_num"])
        print(f"  [{ys}] {r['book_id']:10s}/{st:12s} {r['name']}")
        summary = (r.get("summary") or "").strip()
        if summary:
            print(f"          {summary[:90]}{'…' if len(summary) > 90 else ''}")


if __name__ == "__main__":
    main()
