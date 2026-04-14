#!/usr/bin/env python3
"""L2 元数据生成器。从 corpus.sqlite 读整卷文本，调小米 LLM 生成结构化 JSON。

产物：skill/data/metadata/<book_id>/<sub_type>_<sub_index:03d>.json
  其中 sub_type 为「本纪/世家/列传/书/表/志」等。

环境变量：
  MAX_WORKERS      并发数 (默认 30)
  MIMO_RPM         速率限制 (默认 200; mimo 实测可上 200-300)
  FORCE            非空 = 无视已有版本全量重跑
  MAX_TEXT_CHARS   单卷原文截断 (默认 12000，控制 token 成本)
  PROMPT_VERSION   覆盖 prompts/VERSION

用法：
  # pilot：单本书 + 卷过滤
  python skill/scripts/metadata/generate.py --book shiji \\
      --juans 本纪/1,本纪/7,世家/17,列传/1,列传/22,书/1,书/8,表/1

  # 全量某书
  python skill/scripts/metadata/generate.py --book shiji

  # 限定数量
  python skill/scripts/metadata/generate.py --book shiji --limit 10
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# 跨脚本依赖
SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
from _corpus import require_corpus  # noqa: E402

# 复用根仓库 LLM 客户端
sys.path.insert(0, str(SKILL_ROOT.parent / "scripts"))
from llm_client import call_llm_json  # noqa: E402

from books_registry import get_book_meta  # noqa: E402

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
METADATA_OUT = SKILL_ROOT / "data" / "metadata"

MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "30"))
FORCE = bool(os.environ.get("FORCE", ""))
MAX_TEXT_CHARS = int(os.environ.get("MAX_TEXT_CHARS", "12000"))


def load_prompt_version() -> str:
    return (PROMPT_DIR / "VERSION").read_text("utf-8").strip()


def load_prompt(name: str, **vars) -> str:
    text = (PROMPT_DIR / name).read_text("utf-8")
    for k, v in vars.items():
        text = text.replace("{" + k + "}", str(v))
    return text


PROMPT_VERSION = load_prompt_version()


# ------------------------------------------------------------
# 卷数据加载
# ------------------------------------------------------------

def list_juans(conn: sqlite3.Connection, book_id: str) -> list[dict]:
    """列出某本书的所有「卷」。

    混合策略：
      - 有 sub_type 的段按 (sub_type, sub_index) 聚合
      - 无 sub_type 的段按 juan 聚合
    同一本书两种卷共存（如汉书 22 sub_type + 78 juan）。
    """
    # 有 sub_type 的卷
    cur = conn.execute(
        """
        SELECT sub_type, sub_index,
               MIN(juan) AS juan, MIN(juan_name) AS juan_name,
               MIN(book_name) AS book_name,
               GROUP_CONCAT(text, char(10)) AS full_text,
               COUNT(*) AS segs, SUM(LENGTH(text)) AS chars
        FROM (
          SELECT * FROM documents
          WHERE book_id = ? AND sub_type IS NOT NULL AND sub_index IS NOT NULL
          ORDER BY sub_type, sub_index, segment
        )
        GROUP BY sub_type, sub_index
        ORDER BY sub_type, sub_index
        """,
        (book_id,),
    )
    rows = []
    for r in cur:
        rows.append({
            "sub_type": r["sub_type"],
            "sub_index": r["sub_index"],
            "juan": r["juan"],
            "juan_name": r["juan_name"],
            "book_name": r["book_name"],
            "text": r["full_text"] or "",
            "segs": r["segs"],
            "chars": r["chars"],
        })

    # 无 sub_type 的卷
    cur = conn.execute(
        """
        SELECT juan, MIN(juan_name) AS juan_name,
               MIN(book_name) AS book_name,
               GROUP_CONCAT(text, char(10)) AS full_text,
               COUNT(*) AS segs, SUM(LENGTH(text)) AS chars
        FROM (
          SELECT * FROM documents
          WHERE book_id = ? AND sub_type IS NULL
          ORDER BY juan, segment
        )
        GROUP BY juan
        ORDER BY juan
        """,
        (book_id,),
    )
    for r in cur:
        rows.append({
            "sub_type": None,
            "sub_index": None,
            "juan": r["juan"],
            "juan_name": r["juan_name"],
            "book_name": r["book_name"],
            "text": r["full_text"] or "",
            "segs": r["segs"],
            "chars": r["chars"],
        })

    return rows


def filter_juans(juans: list[dict], spec: str | None, limit: int | None) -> list[dict]:
    """按 --juans 「sub_type/sub_index,...」筛选。"""
    if spec:
        wanted = set()
        for item in spec.split(","):
            item = item.strip()
            if not item:
                continue
            parts = item.split("/")
            if len(parts) != 2:
                print(f"[warn] 忽略非法 juan spec: {item!r}", file=sys.stderr)
                continue
            try:
                wanted.add((parts[0], int(parts[1])))
            except ValueError:
                print(f"[warn] 忽略非整数序号: {item!r}", file=sys.stderr)
        juans = [j for j in juans if (j["sub_type"], j["sub_index"]) in wanted]
    if limit:
        juans = juans[:limit]
    return juans


# ------------------------------------------------------------
# 单卷生成
# ------------------------------------------------------------

def output_path(book_id: str, sub_type: str | None, sub_index: int | None, juan: int) -> Path:
    """按是否有 sub_type 生成不同命名：
    有 subtype → 本纪_001.json / 列传_025.json
    无 subtype → juan_001.json
    """
    if sub_type and sub_index is not None:
        return METADATA_OUT / book_id / f"{sub_type}_{sub_index:03d}.json"
    return METADATA_OUT / book_id / f"juan_{juan:03d}.json"


def is_current_version(path: Path) -> bool:
    if FORCE or not path.exists():
        return False
    try:
        data = json.loads(path.read_text("utf-8"))
        return isinstance(data, dict) and data.get("_prompt_version") == PROMPT_VERSION
    except Exception:
        return False


def truncate_text(text: str, limit: int = MAX_TEXT_CHARS) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    head = limit * 2 // 3
    tail = limit - head - 50
    return text[:head] + "\n…(节略)…\n" + text[-tail:], True


def gen_one(juan: dict, book_meta: dict[str, str], book_id: str) -> str:
    sub_type = juan["sub_type"]
    sub_index = juan["sub_index"]
    juan_num = juan["juan"] or 0
    out = output_path(book_id, sub_type, sub_index, juan_num)
    tag = f"{sub_type}/{sub_index:03d}" if sub_type else f"juan/{juan_num:03d}"
    if is_current_version(out):
        return f"⏭ {book_id}/{tag} 已是 {PROMPT_VERSION}"

    text, truncated = truncate_text(juan["text"])
    system = load_prompt("system.md")
    user = load_prompt(
        "user.md",
        book_name=book_meta["name"],
        author=book_meta["author"],
        dynasty=book_meta["dynasty"],
        juan=juan["juan"] or "?",
        juan_name=juan["juan_name"] or "(无卷名)",
        sub_type=sub_type,
        sub_index=sub_index,
        text=text,
    )

    try:
        result = call_llm_json(system, user)
    except Exception as e:
        return f"❌ {book_id}/{tag}: {type(e).__name__}: {e}"

    if not isinstance(result, dict):
        return f"❌ {book_id}/{tag}: LLM 返回非 dict ({type(result).__name__})"

    # 注入元信息
    payload = {
        "_prompt_version": PROMPT_VERSION,
        "_book_id": book_id,
        "_sub_type": sub_type,
        "_sub_index": sub_index,
        "_juan": juan["juan"],
        "_juan_name": juan["juan_name"],
        "_text_chars": juan["chars"],
        "_text_truncated": truncated,
        **result,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    return f"✅ {book_id}/{tag} {(juan['juan_name'] or '')[:20]}"


# ------------------------------------------------------------
# 主流程
# ------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--book", required=True, help="book_id，如 shiji / mingshi")
    parser.add_argument("--juans", help="筛选「sub_type/index,...」如 本纪/1,世家/17")
    parser.add_argument("--limit", type=int, help="最多生成 N 卷")
    parser.add_argument("--list", action="store_true", help="仅列出该书所有卷")
    args = parser.parse_args()

    conn = require_corpus()
    try:
        all_juans = list_juans(conn, args.book)
    finally:
        conn.close()

    if not all_juans:
        print(f"[fatal] book_id {args.book!r} 在 corpus 中没有 sub_type 分卷数据", file=sys.stderr)
        sys.exit(2)

    if args.list:
        for j in all_juans:
            print(f"  {j['sub_type']}/{j['sub_index']:03d} juan={j['juan']:>3} {j['juan_name']!r:25} segs={j['segs']:>3} chars={j['chars']:>6}")
        print(f"\n总计 {len(all_juans)} 卷")
        return

    juans = filter_juans(all_juans, args.juans, args.limit)
    if not juans:
        print("[fatal] 筛选后无卷可处理", file=sys.stderr)
        sys.exit(2)

    book_meta = get_book_meta(args.book, fallback_name=juans[0]["book_name"])

    print("=" * 70)
    print(f"🔥 L2 metadata generator  prompt={PROMPT_VERSION}")
    print(f"   book={args.book} ({book_meta['name']}) author={book_meta['author']} dynasty={book_meta['dynasty']}")
    print(f"   待生成 {len(juans)} 卷  / 全书 {len(all_juans)} 卷")
    print(f"   MAX_WORKERS={MAX_WORKERS}  MAX_TEXT_CHARS={MAX_TEXT_CHARS}  FORCE={FORCE}")
    print("=" * 70, flush=True)

    done = skip = fail = 0
    t0 = time.time()
    failures: list[str] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(gen_one, j, book_meta, args.book): j for j in juans}
        for fut in as_completed(futures):
            try:
                msg = fut.result()
            except Exception as e:
                j = futures[fut]
                msg = f"❌ {args.book}/{j['sub_type']}/{j['sub_index']:03d}: 未捕获 {e}"
            if msg.startswith("⏭"):
                skip += 1
            elif msg.startswith("✅"):
                done += 1
                print(f"  {msg}", flush=True)
            else:
                fail += 1
                failures.append(msg)
                print(f"  {msg}", flush=True)

    elapsed = time.time() - t0
    print()
    print("=" * 70)
    print(f"📊 完成 {done} / 跳过 {skip} / 失败 {fail}    耗时 {elapsed:.0f}s")
    print("=" * 70)
    if failures:
        log = METADATA_OUT / f"_failures_{args.book}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("\n".join(failures) + "\n", "utf-8")
        print(f"⚠️ 失败日志: {log}")
        sys.exit(1)


if __name__ == "__main__":
    main()
