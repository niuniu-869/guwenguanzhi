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
  sub_type TEXT NOT NULL,
  sub_index INTEGER NOT NULL,
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
  text_truncated INTEGER,
  UNIQUE(book_id, sub_type, sub_index)
);
CREATE INDEX idx_juans_book ON juans(book_id);

DROP TABLE IF EXISTS figures;
CREATE TABLE figures (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id TEXT NOT NULL,
  sub_type TEXT NOT NULL,
  sub_index INTEGER NOT NULL,
  name TEXT NOT NULL,
  aliases_json TEXT,
  role TEXT,
  lifespan TEXT
);
CREATE INDEX idx_fig_book ON figures(book_id);
CREATE INDEX idx_fig_name ON figures(name);

DROP TABLE IF EXISTS events;
CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id TEXT NOT NULL,
  sub_type TEXT NOT NULL,
  sub_index INTEGER NOT NULL,
  name TEXT NOT NULL,
  year TEXT,
  summary TEXT
);
CREATE INDEX idx_evt_book ON events(book_id);

DROP TABLE IF EXISTS cross_refs;
CREATE TABLE cross_refs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id TEXT NOT NULL,
  sub_type TEXT NOT NULL,
  sub_index INTEGER NOT NULL,
  ref_book TEXT,
  locator TEXT,
  relation TEXT
);

DROP TABLE IF EXISTS juans_fts;
CREATE VIRTUAL TABLE juans_fts USING fts5(
  title, juan_name, summary, appreciation, historical_period,
  tokenize='unicode61'
);

DROP TABLE IF EXISTS figures_fts;
CREATE VIRTUAL TABLE figures_fts USING fts5(
  name, aliases, role,
  tokenize='unicode61'
);

DROP TABLE IF EXISTS events_fts;
CREATE VIRTUAL TABLE events_fts USING fts5(
  name, year, summary,
  tokenize='unicode61'
);
"""


def _normalize_book_name(ref_book: str) -> str:
    """去掉《》括号，方便 join。"""
    return ref_book.strip().strip("《》").strip()


def main() -> None:
    if not METADATA_DIR.exists():
        print(f"[fatal] {METADATA_DIR} 不存在", file=sys.stderr)
        sys.exit(2)

    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(DDL)

    juan_rows = 0
    fig_rows = 0
    evt_rows = 0
    ref_rows = 0

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

            sub_type = d.get("_sub_type") or ""
            sub_index = int(d.get("_sub_index") or 0)

            cur = conn.execute(
                """
                INSERT OR REPLACE INTO juans
                  (book_id, sub_type, sub_index, juan, juan_name, title, alt_title,
                   summary, appreciation, tags_json, historical_period, difficulty,
                   modern_relevance_json, geography_json, prompt_version,
                   text_chars, text_truncated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    book_id, sub_type, sub_index,
                    d.get("_juan"), d.get("_juan_name"),
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
                    "INSERT INTO figures(book_id, sub_type, sub_index, name, aliases_json, role, lifespan) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (book_id, sub_type, sub_index, f.get("name", ""),
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
                c3 = conn.execute(
                    "INSERT INTO events(book_id, sub_type, sub_index, name, year, summary) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (book_id, sub_type, sub_index,
                     e.get("name", ""), str(e.get("year", "")), e.get("summary", "")),
                )
                evt_rows += 1
                conn.execute(
                    "INSERT INTO events_fts(rowid, name, year, summary) VALUES (?, ?, ?, ?)",
                    (c3.lastrowid,
                     to_bigrams(e.get("name", "")),
                     str(e.get("year", "")),
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

    conn.commit()
    conn.close()

    print(f"📚 metadata.sqlite built @ {DB_PATH}")
    print(f"   juans     {juan_rows}")
    print(f"   figures   {fig_rows}")
    print(f"   events    {evt_rows}")
    print(f"   cross_refs {ref_rows}")
    print(f"   size      {DB_PATH.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
