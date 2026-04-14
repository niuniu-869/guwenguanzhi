#!/usr/bin/env python3
"""人物 / 地名 一键查找（L2 metadata + figure_cards 合并）。

用法：
    # 人物查询（优先 figure_cards 合并视图）
    python skill/scripts/lookup.py 张良
    python skill/scripts/lookup.py 留侯             # alias 反查
    python skill/scripts/lookup.py 张良 --json

    # 地名查询（geography_items）
    python skill/scripts/lookup.py --place 咸阳
    python skill/scripts/lookup.py --place 长安 --limit 20

输出：
  人物 → canonical_name + aliases + lifespan + 出现于哪些卷（附 role）
  地名 → 哪些卷/书/体裁提到此地
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
        print(
            f"[fatal] 找不到 {METADATA_DB}\n"
            "  请先运行：python skill/scripts/metadata/build_index.py",
            file=sys.stderr,
        )
        sys.exit(2)
    conn = sqlite3.connect(METADATA_DB)
    conn.row_factory = sqlite3.Row
    return conn


def lookup_person(conn: sqlite3.Connection, name: str) -> list[dict]:
    """人物查询：先精确匹配 canonical_name，再 alias，再 FTS 模糊。返回合并视图。"""
    # 1. 精确 canonical_name
    cur = conn.execute(
        "SELECT canonical_name, aliases_json, lifespan, occurrences, appearances_json "
        "FROM figure_cards WHERE canonical_name = ? LIMIT 1",
        (name,),
    )
    rows = cur.fetchall()
    if rows:
        return [dict(r) for r in rows]

    # 2. 作为 alias 精确命中
    cur = conn.execute(
        "SELECT canonical_name, aliases_json, lifespan, occurrences, appearances_json "
        "FROM figure_cards WHERE aliases_json LIKE ? LIMIT 10",
        (f'%"{name}"%',),
    )
    rows = cur.fetchall()
    if rows:
        return [dict(r) for r in rows]

    # 3. FTS 模糊（figures_fts，再 join figure_cards）
    fts_q = query_to_fts(f'"{name}"')
    cur = conn.execute(
        "SELECT DISTINCT f.name AS match_name FROM figures_fts "
        "JOIN figures f ON f.id = figures_fts.rowid "
        "WHERE figures_fts MATCH ? LIMIT 20",
        (fts_q,),
    )
    names = sorted({r["match_name"] for r in cur if r["match_name"]})
    if not names:
        return []
    placeholders = ",".join("?" * len(names))
    cur = conn.execute(
        f"SELECT canonical_name, aliases_json, lifespan, occurrences, appearances_json "
        f"FROM figure_cards WHERE canonical_name IN ({placeholders}) "
        f"ORDER BY occurrences DESC LIMIT 10",
        names,
    )
    return [dict(r) for r in cur.fetchall()]


def lookup_place(conn: sqlite3.Connection, place: str, limit: int = 10) -> list[dict]:
    """地名查询：精确或 LIKE。"""
    cur = conn.execute(
        "SELECT g.book_id, g.sub_type, g.sub_index, g.place, "
        "       j.juan, j.title, j.juan_name, j.historical_period "
        "FROM geography_items g "
        "LEFT JOIN juans j ON j.book_id = g.book_id "
        "  AND (j.sub_type = g.sub_type OR (j.sub_type IS NULL AND g.sub_type IS NULL)) "
        "  AND j.sub_index = g.sub_index "
        "WHERE g.place = ? OR g.place LIKE ? "
        "ORDER BY g.book_id LIMIT ?",
        (place, f"%{place}%", limit),
    )
    return [dict(r) for r in cur.fetchall()]


def _render_person(cards: list[dict], as_json: bool) -> None:
    if as_json:
        print(json.dumps(cards, ensure_ascii=False, indent=2))
        return
    if not cards:
        print("⛔ 未找到")
        sys.exit(3)
    for c in cards:
        aliases = json.loads(c["aliases_json"] or "[]")
        apps = json.loads(c["appearances_json"] or "[]")
        print(f"【{c['canonical_name']}】  生卒: {c['lifespan']}  出现 {c['occurrences']} 卷")
        if aliases:
            print(f"  别名: {' / '.join(aliases)}")
        print(f"  出处:")
        for a in apps[:15]:
            if a.get("sub_type"):
                st = f"{a['sub_type']}/{a['sub_index']:03d}"
            else:
                st = f"juan/{a.get('juan') or '-'}"
            role = (a.get("role") or "")[:40]
            print(f"    {a.get('book'):10s}/{st:12s}  {role}")
        if len(apps) > 15:
            print(f"    ...（共 {len(apps)} 条）")
        print()


def _render_place(rows: list[dict], place: str, as_json: bool) -> None:
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        print(f"⛔ 地名 {place!r} 未命中")
        sys.exit(3)
    print(f"✅ 地名 {place!r} 在 {len(rows)} 卷出现：")
    for r in rows:
        if r["sub_type"]:
            st = f"{r['sub_type']}/{r['sub_index']:03d}"
        else:
            st = f"juan/{r.get('juan') or '-'}"
        title = (r.get("title") or "")[:30]
        period = (r.get("historical_period") or "")[:20]
        print(f"  {r['book_id']:10s}/{st:12s}  {title:30s}  ({period})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name", nargs="?", help="人物名称（或别名）")
    parser.add_argument("--place", help="地名（改地名查询模式）")
    parser.add_argument("--limit", type=int, default=10, help="地名模式限返回条数")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    if not args.name and not args.place:
        parser.error("必须提供人物名或 --place 地名")

    conn = require_metadata()
    try:
        if args.place:
            _render_place(lookup_place(conn, args.place, args.limit), args.place, args.json)
        else:
            _render_person(lookup_person(conn, args.name), args.json)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
