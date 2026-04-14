#!/usr/bin/env python3
"""把 skill/data/metadata/**/*.json 合并为 skill/data/metadata.sqlite。

Schema：
  juans(book_id, sub_type, sub_index, juan, juan_name, title, summary,
        appreciation, tags_json, historical_period, difficulty,
        modern_relevance_json, geography_json, prompt_version)
  figures(book_id, sub_type, sub_index, name, aliases_json, role, lifespan)
  events (book_id, sub_type, sub_index, name, year, summary)
  cross_refs(book_id, sub_type, sub_index, ref_book, locator, relation)

+ FTS5 全文索引：
  juans_fts(title, summary, appreciation, historical_period)
  figures_fts(name, aliases, role)   -- 用 bigram 预处理
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
from _corpus import to_bigrams  # noqa: E402

METADATA_DIR = SKILL_ROOT / "data" / "metadata"
DB_PATH = SKILL_ROOT / "data" / "metadata.sqlite"


DDL = """
PRAGMA journal_mode=WAL;

DROP TABLE IF EXISTS juans;
CREATE TABLE juans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id TEXT NOT NULL,
  sub_type TEXT,
  sub_index INTEGER,
  juan INTEGER,
  juan_name TEXT,
  title TEXT,
  alt_title TEXT,
  summary TEXT,
  appreciation TEXT,
  tags_json TEXT,
  historical_period TEXT,
  difficulty INTEGER,
  modern_relevance_json TEXT,
  geography_json TEXT,
  prompt_version TEXT,
  text_chars INTEGER,
  text_truncated INTEGER
);
CREATE INDEX idx_juans_book ON juans(book_id);
CREATE INDEX idx_juans_subtype ON juans(book_id, sub_type, sub_index);

DROP TABLE IF EXISTS figures;
CREATE TABLE figures (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id TEXT NOT NULL,
  sub_type TEXT,
  sub_index INTEGER,
  juan INTEGER,
  name TEXT NOT NULL,
  aliases_json TEXT,
  role TEXT,
  lifespan TEXT
);
CREATE INDEX idx_fig_book ON figures(book_id);
CREATE INDEX idx_fig_name ON figures(name);

-- figure_cards：跨卷人物卡（合并同名人物，跨书跨卷聚合）
DROP TABLE IF EXISTS figure_cards;
CREATE TABLE figure_cards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical_name TEXT NOT NULL UNIQUE,
  aliases_json TEXT,
  lifespan TEXT,
  occurrences INTEGER,
  appearances_json TEXT  -- [{book, sub_type, sub_index, role, lifespan}, ...]
);
CREATE INDEX idx_card_name ON figure_cards(canonical_name);

DROP TABLE IF EXISTS events;
CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id TEXT NOT NULL,
  sub_type TEXT,
  sub_index INTEGER,
  juan INTEGER,
  name TEXT NOT NULL,
  year TEXT,
  year_num INTEGER,  -- 从 year 字段解析出的整数（前 100 = -100），用于 timeline 筛选
  summary TEXT
);
CREATE INDEX idx_evt_book ON events(book_id);
CREATE INDEX idx_evt_year ON events(year_num);

DROP TABLE IF EXISTS cross_refs;
CREATE TABLE cross_refs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id TEXT NOT NULL,
  sub_type TEXT,
  sub_index INTEGER,
  ref_book TEXT,
  locator TEXT,
  relation TEXT
);

-- juans_fts: 标题/卷名/摘要/赏析/时期
DROP TABLE IF EXISTS juans_fts;
CREATE VIRTUAL TABLE juans_fts USING fts5(
  title, juan_name, summary, appreciation, historical_period,
  tokenize='unicode61'
);

-- figures_fts: 人物 name/aliases/role
DROP TABLE IF EXISTS figures_fts;
CREATE VIRTUAL TABLE figures_fts USING fts5(
  name, aliases, role,
  tokenize='unicode61'
);

-- events_fts: 事件 name/summary（year 不入 fts，直接查 events.year_num）
DROP TABLE IF EXISTS events_fts;
CREATE VIRTUAL TABLE events_fts USING fts5(
  event_name, event_summary,
  tokenize='unicode61'
);

-- advisory_fts: modern_relevance 历史咨询场景
DROP TABLE IF EXISTS advisory_fts;
CREATE VIRTUAL TABLE advisory_fts USING fts5(
  scenario, tokenize='unicode61'
);

-- advisory_items: modern_relevance 条目（每条一行），与 advisory_fts rowid 对齐
DROP TABLE IF EXISTS advisory_items;
CREATE TABLE advisory_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id TEXT NOT NULL,
  sub_type TEXT,
  sub_index INTEGER,
  scenario TEXT NOT NULL
);

-- geography_items: 地名 → 出处
DROP TABLE IF EXISTS geography_items;
CREATE TABLE geography_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id TEXT NOT NULL,
  sub_type TEXT,
  sub_index INTEGER,
  place TEXT NOT NULL
);
CREATE INDEX idx_geo_place ON geography_items(place);
"""


import re as _re

_YEAR_PATTERNS = [
    (_re.compile(r"[^\d一二三四五六七八九十百千]*前\s*(\d+)"), -1),
    (_re.compile(r"[^\d一二三四五六七八九十百千]*公元前\s*(\d+)"), -1),
    (_re.compile(r"(\d{2,4})\s*年"), 1),
    (_re.compile(r"^\s*(\d{2,4})\b"), 1),
]


def parse_year(year_str: str) -> int | None:
    """从「前207」「1363」「206-202」「建安五年（200年）」等提取首个年份为 int。
    前 = 负数。"""
    if not year_str:
        return None
    s = str(year_str).strip()
    if not s or s in ("不详", "?", "未详"):
        return None
    # 优先"前 N"
    m = _re.search(r"前\s*(\d+)", s)
    if m:
        return -int(m.group(1))
    # "公元前 N"
    m = _re.search(r"公元前\s*(\d+)", s)
    if m:
        return -int(m.group(1))
    # N 年 或 纯数字
    m = _re.search(r"(\d{2,4})", s)
    if m:
        return int(m.group(1))
    return None


def _normalize_book_name(ref_book: str) -> str:
    """去掉《》括号，方便 join。"""
    return ref_book.strip().strip("《》").strip()


def _build_figure_cards(conn: sqlite3.Connection) -> int:
    """合并 figures 表的同名记录：以 canonical_name 为主键聚合。
    lifespan 取出现频次最多的非"不详"值；aliases 取并集。
    """
    from collections import Counter
    # 取所有 figures
    cur = conn.execute(
        "SELECT book_id, sub_type, sub_index, juan, name, aliases_json, role, lifespan FROM figures"
    )
    buckets: dict[str, dict] = {}
    for r in cur:
        name = (r["name"] or "").strip()
        if not name:
            continue
        bucket = buckets.setdefault(name, {
            "aliases": set(),
            "lifespans": [],
            "appearances": [],
        })
        try:
            aliases = json.loads(r["aliases_json"] or "[]")
            if isinstance(aliases, list):
                bucket["aliases"].update(a for a in aliases if isinstance(a, str) and a)
        except json.JSONDecodeError:
            pass
        ls = (r["lifespan"] or "").strip()
        if ls and ls not in ("不详", "?", "未详"):
            bucket["lifespans"].append(ls)
        bucket["appearances"].append({
            "book": r["book_id"], "sub_type": r["sub_type"],
            "sub_index": r["sub_index"], "juan": r["juan"],
            "role": r["role"], "lifespan": ls,
        })

    rows = 0
    for name, b in buckets.items():
        if b["lifespans"]:
            lifespan = Counter(b["lifespans"]).most_common(1)[0][0]
        else:
            lifespan = "不详"
        conn.execute(
            "INSERT INTO figure_cards(canonical_name, aliases_json, lifespan, "
            "occurrences, appearances_json) VALUES (?, ?, ?, ?, ?)",
            (name, json.dumps(sorted(b["aliases"]), ensure_ascii=False),
             lifespan, len(b["appearances"]),
             json.dumps(b["appearances"], ensure_ascii=False)),
        )
        rows += 1
    return rows


def main() -> None:
    if not METADATA_DIR.exists():
        print(f"[fatal] {METADATA_DIR} 不存在", file=sys.stderr)
        sys.exit(2)

    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL)

    juan_rows = 0
    fig_rows = 0
    evt_rows = 0
    ref_rows = 0
    adv_rows = 0
    geo_rows = 0

    for book_dir in sorted(METADATA_DIR.iterdir()):
        if not book_dir.is_dir():
            continue
        book_id = book_dir.name
        for json_file in sorted(book_dir.glob("*.json")):
            try:
                d = json.loads(json_file.read_text("utf-8"))
            except Exception as e:
                print(f"⚠️ 解析失败 {json_file}: {e}", file=sys.stderr)
                continue

            sub_type = d.get("_sub_type") or None
            sub_index = d.get("_sub_index")
            juan_val = d.get("_juan")

            cur = conn.execute(
                """
                INSERT INTO juans
                  (book_id, sub_type, sub_index, juan, juan_name, title, alt_title,
                   summary, appreciation, tags_json, historical_period, difficulty,
                   modern_relevance_json, geography_json, prompt_version,
                   text_chars, text_truncated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    book_id, sub_type, sub_index,
                    juan_val, d.get("_juan_name"),
                    d.get("title", ""), d.get("alt_title", ""),
                    d.get("summary", ""), d.get("appreciation", ""),
                    json.dumps(d.get("tags", []), ensure_ascii=False),
                    d.get("historical_period", ""),
                    d.get("difficulty") if isinstance(d.get("difficulty"), int) else None,
                    json.dumps(d.get("modern_relevance", []), ensure_ascii=False),
                    json.dumps(d.get("geography", []), ensure_ascii=False),
                    d.get("_prompt_version", ""),
                    d.get("_text_chars"),
                    1 if d.get("_text_truncated") else 0,
                ),
            )
            juan_rows += 1

            # juans_fts 同步
            conn.execute(
                "INSERT INTO juans_fts(rowid, title, juan_name, summary, appreciation, historical_period) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    cur.lastrowid,
                    to_bigrams(d.get("title", "")),
                    to_bigrams(d.get("_juan_name") or ""),
                    to_bigrams(d.get("summary", "")),
                    to_bigrams(d.get("appreciation", "")),
                    to_bigrams(d.get("historical_period", "")),
                ),
            )

            # figures
            for f in d.get("key_figures", []) or []:
                if not isinstance(f, dict):
                    continue
                aliases = f.get("aliases") or []
                if not isinstance(aliases, list):
                    aliases = []
                c2 = conn.execute(
                    "INSERT INTO figures(book_id, sub_type, sub_index, juan, name, aliases_json, role, lifespan) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (book_id, sub_type, sub_index, juan_val, f.get("name", ""),
                     json.dumps(aliases, ensure_ascii=False),
                     f.get("role", ""), f.get("lifespan", "")),
                )
                fig_rows += 1
                conn.execute(
                    "INSERT INTO figures_fts(rowid, name, aliases, role) VALUES (?, ?, ?, ?)",
                    (c2.lastrowid,
                     to_bigrams(f.get("name", "")),
                     to_bigrams(" ".join(aliases)),
                     to_bigrams(f.get("role", ""))),
                )

            # events
            for e in d.get("key_events", []) or []:
                if not isinstance(e, dict):
                    continue
                year_str = str(e.get("year", ""))
                year_num = parse_year(year_str)
                c3 = conn.execute(
                    "INSERT INTO events(book_id, sub_type, sub_index, juan, name, year, year_num, summary) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (book_id, sub_type, sub_index, juan_val,
                     e.get("name", ""), year_str, year_num, e.get("summary", "")),
                )
                evt_rows += 1
                conn.execute(
                    "INSERT INTO events_fts(rowid, event_name, event_summary) VALUES (?, ?, ?)",
                    (c3.lastrowid,
                     to_bigrams(e.get("name", "")),
                     to_bigrams(e.get("summary", ""))),
                )

            # cross_refs
            for cr in d.get("cross_refs", []) or []:
                if not isinstance(cr, dict):
                    continue
                conn.execute(
                    "INSERT INTO cross_refs(book_id, sub_type, sub_index, ref_book, locator, relation) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (book_id, sub_type, sub_index,
                     _normalize_book_name(cr.get("book", "")),
                     cr.get("locator", ""), cr.get("relation", "")),
                )
                ref_rows += 1

            # modern_relevance → advisory
            for scenario in d.get("modern_relevance", []) or []:
                if not isinstance(scenario, str) or not scenario.strip():
                    continue
                c4 = conn.execute(
                    "INSERT INTO advisory_items(book_id, sub_type, sub_index, scenario) "
                    "VALUES (?, ?, ?, ?)",
                    (book_id, sub_type, sub_index, scenario),
                )
                adv_rows += 1
                conn.execute(
                    "INSERT INTO advisory_fts(rowid, scenario) VALUES (?, ?)",
                    (c4.lastrowid, to_bigrams(scenario)),
                )

            # geography
            for place in d.get("geography", []) or []:
                if not isinstance(place, str) or not place.strip():
                    continue
                conn.execute(
                    "INSERT INTO geography_items(book_id, sub_type, sub_index, place) "
                    "VALUES (?, ?, ?, ?)",
                    (book_id, sub_type, sub_index, place),
                )
                geo_rows += 1

    # 人物卡合并
    card_rows = _build_figure_cards(conn)

    conn.commit()
    conn.close()

    print(f"📚 metadata.sqlite built @ {DB_PATH}")
    print(f"   juans        {juan_rows}")
    print(f"   figures      {fig_rows}")
    print(f"   figure_cards {card_rows}")
    print(f"   events       {evt_rows}")
    print(f"   cross_refs   {ref_rows}")
    print(f"   advisory     {adv_rows}")
    print(f"   geography    {geo_rows}")
    print(f"   size         {DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
