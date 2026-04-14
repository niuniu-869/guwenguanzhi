#!/usr/bin/env python3
"""Evals Runner —— skill 工具层反幻觉测试。

评测 4 个自动化维度 + 1 个 prompts 输出（traps 需人工或 LLM 判分）：
  citation → cite.py 是否正确拒绝伪例、命中正例
  figures  → lookup.py 是否返回 canonical 卡；伪例是否返空
  dynasty  → 两人 lifespan 交叉判断
  advisory → analogy.py 是否返回先例；现代专属场景是否返空

traps 输出 prompts 清单（需 LLM 或人工评估是否给出古义）。

用法：
  python skill/evals/run_evals.py            # 跑全部
  python skill/evals/run_evals.py citation  # 只跑一类
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
SKILL_ROOT = EVAL_DIR.parent
SCRIPT_DIR = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from _corpus import require_corpus, query_to_fts  # noqa: E402


# ============= citation =============

def eval_citation() -> dict:
    items = _load("test_citation.jsonl")
    conn = require_corpus()
    try:
        hit = miss = fp = fn = 0
        fails: list[str] = []
        for it in items:
            expected = it["expected_hit"]
            frag = it["fragment"]
            found = _cite_verify(conn, frag)
            if expected and found:
                hit += 1
            elif expected and not found:
                fn += 1
                fails.append(f"[FN] {it['id']}: '{frag}' 应命中却未命中")
            elif not expected and not found:
                miss += 1  # 正确拒绝
            else:  # not expected and found
                fp += 1
                fails.append(f"[FP] {it['id']}: '{frag}' 应拒却命中")
    finally:
        conn.close()

    total = len(items)
    correct = hit + miss
    return {
        "category": "citation",
        "total": total,
        "correct": correct,
        "accuracy": correct / total,
        "true_positive": hit,
        "true_negative": miss,
        "false_positive": fp,
        "false_negative": fn,
        "fails": fails[:10],
    }


def _cite_verify(conn: sqlite3.Connection, fragment: str) -> bool:
    """模拟 cite.py --verify 的核心：片段 → FTS 查询 → 是否命中。"""
    if len(fragment) < 2:
        return False
    fts_q = query_to_fts(f'"{fragment}"')
    try:
        cur = conn.execute(
            "SELECT COUNT(*) as c FROM documents_fts WHERE documents_fts MATCH ?",
            (fts_q,),
        )
        return cur.fetchone()["c"] > 0
    except sqlite3.OperationalError:
        return False


# ============= figures =============

def eval_figures() -> dict:
    items = _load("test_figures.jsonl")
    conn = _meta_conn()
    try:
        hit = miss = fp = fn = 0
        fails: list[str] = []
        for it in items:
            expected = it["expected_hit"]
            name = it["query"]
            card = _lookup_person(conn, name)
            if expected and card:
                # 额外：canonical 应匹配或是 alias
                canon_ok = card["canonical_name"] == it["expected_canonical"]
                if canon_ok:
                    hit += 1
                else:
                    fn += 1
                    fails.append(f"[canonical mismatch] {it['id']}: 查 {name} → {card['canonical_name']} ≠ {it['expected_canonical']}")
            elif expected and not card:
                fn += 1
                fails.append(f"[FN] {it['id']}: {name} 应命中却返回空")
            elif not expected and not card:
                miss += 1
            else:
                fp += 1
                fails.append(f"[FP] {it['id']}: {name} 应拒却命中 → {card['canonical_name']}")
    finally:
        conn.close()

    total = len(items)
    correct = hit + miss
    return {
        "category": "figures",
        "total": total,
        "correct": correct,
        "accuracy": correct / total,
        "true_positive": hit,
        "true_negative": miss,
        "false_positive": fp,
        "false_negative": fn,
        "fails": fails[:10],
    }


def _lookup_person(conn: sqlite3.Connection, name: str) -> dict | None:
    cur = conn.execute(
        "SELECT canonical_name, aliases_json, lifespan, occurrences "
        "FROM figure_cards WHERE canonical_name = ? LIMIT 1",
        (name,),
    )
    row = cur.fetchone()
    if row:
        return dict(row)
    cur = conn.execute(
        "SELECT canonical_name, aliases_json, lifespan, occurrences "
        "FROM figure_cards WHERE aliases_json LIKE ? LIMIT 1",
        (f'%"{name}"%',),
    )
    row = cur.fetchone()
    return dict(row) if row else None


# ============= dynasty =============

YEAR_RE = re.compile(r"前?\d+")


def _parse_years(lifespan: str) -> tuple[int | None, int | None]:
    """从 lifespan 如 '前250-前186' / '1472-1529' / '约前551-前479' 抽年份。"""
    if not lifespan or lifespan == "None":
        return None, None
    text = lifespan.replace("约", "").replace("？", "").replace("?", "")
    parts = re.split(r"[-—–~]", text)
    if len(parts) < 2:
        return None, None

    def num(s: str) -> int | None:
        s = s.strip()
        m = re.search(r"前?(\d+)", s)
        if not m:
            return None
        year = int(m.group(1))
        return -year if s.startswith("前") else year

    return num(parts[0]), num(parts[1])


def eval_dynasty() -> dict:
    items = _load("test_dynasty.jsonl")
    conn = _meta_conn()
    try:
        hit = partial = wrong = missing = 0
        fails: list[str] = []
        for it in items:
            a_card = _lookup_person(conn, it["person_a"])
            b_card = _lookup_person(conn, it["person_b"])
            if not a_card or not b_card:
                missing += 1
                fails.append(f"[MISS] {it['id']}: 人物卡缺失 {it['person_a']}/{it['person_b']}")
                continue
            a_birth, a_death = _parse_years(a_card.get("lifespan") or "")
            b_birth, b_death = _parse_years(b_card.get("lifespan") or "")
            if None in (a_birth, a_death, b_birth, b_death):
                partial += 1
                continue
            # 活期交叉
            can_meet_inferred = not (a_death < b_birth or b_death < a_birth)
            if can_meet_inferred == it["expected_can_meet"]:
                hit += 1
            else:
                wrong += 1
                fails.append(
                    f"[WRONG] {it['id']}: {it['person_a']}({a_birth}—{a_death}) vs "
                    f"{it['person_b']}({b_birth}—{b_death}) "
                    f"推断={can_meet_inferred} 期望={it['expected_can_meet']}"
                )
    finally:
        conn.close()

    total = len(items)
    return {
        "category": "dynasty",
        "total": total,
        "correct": hit,
        "accuracy": hit / total,
        "partial_data": partial,
        "missing_data": missing,
        "wrong": wrong,
        "fails": fails[:10],
    }


# ============= advisory =============

def eval_advisory() -> dict:
    """判分规则（与 advisory 三标签精神一致）：
    - expected_direct=True：应能通过 strict 命中，或 loose ≥ 100（"大量相关 scenarios 提到关键词"）
    - expected_direct=False：strict 必须 = 0（现代专有词不应触发伪先例）
    - loose 命中只是提示参考，不作为"直接先例"证据
    """
    items = _load("test_advisory.jsonl")
    conn = _meta_conn()
    try:
        hit = miss = fp = fn = 0
        fails: list[str] = []
        for it in items:
            expected = it["expected_direct"]
            strict_cnt, loose_cnt = _analogy_two_stage(conn, it["query"])
            if expected:
                ok = strict_cnt > 0 or loose_cnt >= 100
                if ok:
                    hit += 1
                else:
                    fn += 1
                    fails.append(f"[FN] {it['id']}: '{it['query']}' 应有先例却 strict={strict_cnt} loose={loose_cnt}")
            else:
                # 期望 strict = 0（避免伪先例）
                if strict_cnt == 0:
                    miss += 1
                else:
                    fp += 1
                    fails.append(f"[FP] {it['id']}: '{it['query']}' 应 strict=0 却命中 strict={strict_cnt}")
    finally:
        conn.close()

    total = len(items)
    correct = hit + miss
    return {
        "category": "advisory",
        "total": total,
        "correct": correct,
        "accuracy": correct / total,
        "true_positive": hit,
        "true_negative": miss,
        "false_positive": fp,
        "false_negative": fn,
        "fails": fails[:10],
    }


def _analogy_two_stage(conn: sqlite3.Connection, query: str) -> tuple[int, int]:
    """分别返回 (严格命中数, 宽松命中数)。"""
    strict_q = query_to_fts(query)
    strict_cnt = 0
    try:
        cur = conn.execute(
            "SELECT COUNT(*) AS c FROM advisory_fts WHERE advisory_fts MATCH ?",
            (strict_q,),
        )
        strict_cnt = cur.fetchone()["c"]
    except sqlite3.OperationalError:
        pass
    # bigram OR 回退
    chunks = re.findall(r"[\u4e00-\u9fff]+", query)
    bigrams: list[str] = []
    for chunk in chunks:
        if len(chunk) == 1:
            bigrams.append(chunk)
        else:
            bigrams += [chunk[i] + chunk[i + 1] for i in range(len(chunk) - 1)]
    loose_cnt = 0
    if bigrams:
        loose_q = " OR ".join(f"({bg})" for bg in bigrams)
        try:
            cur = conn.execute(
                "SELECT COUNT(*) AS c FROM advisory_fts WHERE advisory_fts MATCH ?",
                (loose_q,),
            )
            loose_cnt = cur.fetchone()["c"]
        except sqlite3.OperationalError:
            pass
    return strict_cnt, loose_cnt


# ============= traps（输出 prompts，不自动判分） =============

def eval_traps() -> dict:
    items = _load("test_traps.jsonl")
    return {
        "category": "traps",
        "total": len(items),
        "note": "trap 题需 LLM 或人工判分：检查 agent 输出是否给出 expected_meaning_keyword 的关键词；本工具层无法自动评测。",
        "sample_prompts": [
            {"id": it["id"], "prompt": it["prompt"], "expected_keyword": it["expected_meaning_keyword"]}
            for it in items[:5]
        ],
    }


# ============= shared =============

def _load(name: str) -> list[dict]:
    path = EVAL_DIR / name
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def _meta_conn() -> sqlite3.Connection:
    path = SKILL_ROOT / "data" / "metadata.sqlite"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    runners = {
        "citation": eval_citation,
        "figures": eval_figures,
        "dynasty": eval_dynasty,
        "advisory": eval_advisory,
        "traps": eval_traps,
    }
    if target != "all" and target not in runners:
        print(f"未知目标 {target}。可选：{list(runners)} 或 all")
        sys.exit(2)

    names = [target] if target != "all" else list(runners)
    results = []
    for n in names:
        r = runners[n]()
        results.append(r)
        print(f"\n══ {r['category'].upper()} ══")
        for k, v in r.items():
            if k == "fails":
                continue
            if k == "sample_prompts":
                continue
            print(f"  {k}: {v}")
        if r.get("fails"):
            print(f"  ⚠️ 前 10 条失败样例：")
            for f in r["fails"]:
                print(f"    {f}")

    print("\n══ 汇总 ══")
    for r in results:
        acc = r.get("accuracy")
        if acc is not None:
            print(f"  {r['category']:10s}  {acc*100:.1f}%  ({r['correct']}/{r['total']})")
        else:
            print(f"  {r['category']:10s}  (prompts only: {r['total']})")


if __name__ == "__main__":
    main()
