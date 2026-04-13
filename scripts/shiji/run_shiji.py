#!/usr/bin/env python3
"""
史记 LLM 翻译管线（复用古文观止 run_all_parallel 架构）
- 支持多书结构：data/books/{book}/raw/*.txt → data/books/{book}/output/*.json
- 拉满并发：MAX_WORKERS 可通过 ENV 调整
- 支持 PILOT=juan1,juan7,juan86 模式只跑指定卷

用法：
  python3 scripts/shiji/run_shiji.py              # 全量 130 卷
  PILOT=1,7,86 python3 scripts/shiji/run_shiji.py # 只跑 3 卷 pilot
  STEP=meta,trans python3 scripts/shiji/run_shiji.py # 只跑指定步骤
  MAX_WORKERS=50 python3 scripts/shiji/run_shiji.py
"""

import json
import os
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))
from llm_client import call_llm_json  # noqa: E402

BASE_DIR = Path(__file__).parent.parent.parent
BOOK_DIR = BASE_DIR / "data/books/shiji"
CATALOG_FILE = BOOK_DIR / "catalog.json"
RAW_DIR = BOOK_DIR / "raw"
OUT_DIR = BOOK_DIR / "output"

MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "20"))     # 卷间并发
INNER_WORKERS = int(os.environ.get("INNER_WORKERS", "30"))  # 卷内段落/批次并发
PILOT = os.environ.get("PILOT", "").strip()
STEPS = set(os.environ.get("STEP", "meta,trans,words,merge").split(","))

# ============================================================
# Prompts
# ============================================================

META_SYSTEM = "你是一位精通古代汉语、汉史与《史记》研究的学者。回答必须是纯 JSON 格式，不含 markdown 标记。"
META_USER = """《史记》卷{juan}《{title}》（{category}）
作者：司马迁
全文（可能较长，以下为节选或全文）：
{text}

请为本卷生成 JSON，内容简明、务实、避免套话：
{{
  "summary": "本卷内容提要（150-250字，概括主要人物/事件/时代背景）",
  "appreciation": "文学与史学价值评析（250-400字，谈叙事技法、思想立场、名句）",
  "tags": ["标签1", "标签2", "标签3"],
  "key_figures": ["本卷主要人物1", "人物2"],
  "historical_period": "本卷涉及的历史时期（如：春秋末至战国中期）"
}}"""

TRANS_SYSTEM = "你是精通古代汉语与史记的翻译学者，风格信达雅，不加解释不输出无关内容。回答必须是纯 JSON。"
TRANS_USER = """《史记·{title}》第 {para_idx}/{total} 段

前文摘要（供理解人物关系）：
{context}

本段原文：
---
{paragraph}
---

翻译要求：
1. 将本段按语义拆分为若干句（允许跨标点，如"壬戌之秋，七月既望"可合为一句）
2. 每句给出白话翻译，人名/地名/官职保留原文
3. 整段给出流畅白话翻译
4. 不加"本段讲述..."之类评注

输出 JSON：
{{"paragraph_translation":"整段白话","sentences":[{{"original":"原文句","translation":"白话翻译"}}]}}"""

WORDS_SYSTEM = "你是精通古代汉语训诂与史记专名的学者。回答必须是纯 JSON。"
WORDS_USER = """《史记·{title}》段落上下文：
{paragraph}

对以下句子做逐词注释（词组级，非逐字）：
{sentences_block}

要求：
1. 词组切分：「郑武公」「伍子胥」「太史公曰」「燕雀安知鸿鹄之志哉」是一个词或成语，不要拆
2. 虚词（之乎者也而以于）单独标注
3. 每词提供 word/pinyin/meaning(12字内)/type
4. type 枚举：实词|虚词|人名|地名|官职|年号|典故|成语|器物
5. 标点不要作为词条
6. meaning 务必简短，不写"本段中..."这种

JSON：{{"sentences":[{{"original":"原文句","words":[{{"word":"词","pinyin":"拼音","meaning":"释义","type":"类型"}}]}}]}}"""


# ============================================================
# I/O
# ============================================================

def load_catalog() -> dict:
    return json.loads(CATALOG_FILE.read_text("utf-8"))


def pick_juans(catalog: dict) -> list[dict]:
    juans = catalog["juan"]
    if not PILOT:
        return juans
    ids = set()
    for x in PILOT.split(","):
        x = x.strip()
        if x.isdigit():
            ids.add(int(x))
    return [j for j in juans if j["juan"] in ids]


def paragraphs_of(juan: dict) -> list[str]:
    raw = RAW_DIR / f"{juan['id']}.txt"
    if not raw.exists():
        return []
    return [p.strip() for p in raw.read_text("utf-8").split("\n") if p.strip()]


# ============================================================
# Step 1: metadata
# ============================================================

def gen_meta(juan: dict) -> str:
    jid = juan["id"]
    out = OUT_DIR / f"{jid}_meta.json"
    if out.exists():
        return f"⏭ meta: {juan['title']}"

    paras = paragraphs_of(juan)
    if not paras:
        return f"❌ meta: {juan['title']}: 原文缺失"

    # 截断超长文本（元数据生成不需要全文）
    text = "\n".join(paras)
    if len(text) > 8000:
        text = text[:8000] + "\n...(后略)"

    prompt = META_USER.format(
        juan=juan["juan"], title=juan["title"],
        category=juan["category_name"], text=text,
    )
    try:
        result = call_llm_json(META_SYSTEM, prompt)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
        return f"✅ meta: {juan['title']}"
    except Exception as e:
        return f"❌ meta: {juan['title']} - {e}"


# ============================================================
# Step 2: 逐段翻译
# ============================================================

def _trans_one_para(juan: dict, para: str, idx: int, total: int, context: str) -> dict:
    """翻译单段（供并发调用）"""
    prompt = TRANS_USER.format(
        title=juan["title"], para_idx=idx + 1, total=total,
        context=context, paragraph=para,
    )
    try:
        r = call_llm_json(TRANS_SYSTEM, prompt)
        r["original"] = para
        return r
    except Exception as e:
        return {"original": para, "paragraph_translation": "", "sentences": [], "error": str(e)}


def gen_trans(juan: dict) -> str:
    """整卷翻译：段落级并发（卷内 ThreadPool），大幅加速"""
    jid = juan["id"]
    out = OUT_DIR / f"{jid}_trans.json"
    if out.exists():
        return f"⏭ trans: {juan['title']}"

    paras = paragraphs_of(juan)
    if not paras:
        return f"❌ trans: {juan['title']}: 原文缺失"

    # 预计算每段 context（滚动前 3 段，<=500 字）
    contexts = []
    for i in range(len(paras)):
        if i == 0:
            contexts.append("（本段为开篇）")
        else:
            ctx = " ".join(paras[max(0, i - 3):i])
            contexts.append(ctx[-500:] if len(ctx) > 500 else ctx)

    results = [None] * len(paras)
    # 卷内段落并发（复用全局 RPM 限流）
    with ThreadPoolExecutor(max_workers=min(INNER_WORKERS, len(paras))) as pool:
        futures = {
            pool.submit(_trans_one_para, juan, p, i, len(paras), contexts[i]): i
            for i, p in enumerate(paras)
        }
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                results[i] = fut.result()
            except Exception as e:
                results[i] = {"original": paras[i], "paragraph_translation": "",
                              "sentences": [], "error": str(e)}

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), "utf-8")
    return f"✅ trans: {juan['title']} ({len(paras)}段)"


# ============================================================
# Step 3: 逐词注释
# ============================================================

def _words_one_batch(juan: dict, para_text: str, batch: list) -> list:
    """对一批句子生成逐词注释（供并发调用），失败时返回空词列表"""
    block = "\n".join(f'{i+1}. "{s["original"]}"' for i, s in enumerate(batch))
    prompt = WORDS_USER.format(title=juan["title"], paragraph=para_text, sentences_block=block)
    try:
        r = call_llm_json(WORDS_SYSTEM, prompt)
        return r.get("sentences", [])
    except Exception as e:
        return [{"original": s["original"], "words": [], "error": str(e)} for s in batch]


def gen_words(juan: dict) -> str:
    """逐词注释：所有 (段, 批) 组合并发"""
    jid = juan["id"]
    out = OUT_DIR / f"{jid}_words.json"
    trans_f = OUT_DIR / f"{jid}_trans.json"

    if out.exists():
        return f"⏭ words: {juan['title']}"
    if not trans_f.exists():
        return f"❌ words: {juan['title']}: 缺 trans"

    trans = json.loads(trans_f.read_text("utf-8"))

    BATCH = int(os.environ.get("WORDS_BATCH", "5"))
    # 收集所有要发的批次：(para_idx, batch_idx, para_text, batch)
    tasks = []
    for pi, para_data in enumerate(trans):
        sents = para_data.get("sentences", [])
        para_text = para_data.get("original", "")
        for bi, b_start in enumerate(range(0, len(sents), BATCH)):
            batch = sents[b_start:b_start + BATCH]
            tasks.append((pi, bi, para_text, batch))

    # 并发执行所有批次
    results_by_pi_bi = {}
    if tasks:
        with ThreadPoolExecutor(max_workers=min(INNER_WORKERS, len(tasks))) as pool:
            futures = {
                pool.submit(_words_one_batch, juan, para_text, batch): (pi, bi)
                for pi, bi, para_text, batch in tasks
            }
            for fut in as_completed(futures):
                pi, bi = futures[fut]
                try:
                    results_by_pi_bi[(pi, bi)] = fut.result()
                except Exception as e:
                    results_by_pi_bi[(pi, bi)] = [
                        {"original": s["original"], "words": [], "error": str(e)}
                        for s in tasks[[t[:2] for t in tasks].index((pi, bi))][3]
                    ]

    # 按段重组
    all_results = []
    for pi, para_data in enumerate(trans):
        sents = para_data.get("sentences", [])
        merged = []
        bi = 0
        while bi * BATCH < len(sents):
            merged.extend(results_by_pi_bi.get((pi, bi), []))
            bi += 1
        all_results.append({"sentences": merged})

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), "utf-8")
    return f"✅ words: {juan['title']}"


# ============================================================
# Step 4: merge
# ============================================================

def merge(juan: dict) -> str:
    jid = juan["id"]
    meta_f = OUT_DIR / f"{jid}_meta.json"
    trans_f = OUT_DIR / f"{jid}_trans.json"
    words_f = OUT_DIR / f"{jid}_words.json"
    out = OUT_DIR / f"{jid}.json"

    if not all(f.exists() for f in [meta_f, trans_f, words_f]):
        missing = [f.name for f in [meta_f, trans_f, words_f] if not f.exists()]
        return f"❌ merge: {juan['title']}: 缺 {missing}"

    meta = json.loads(meta_f.read_text("utf-8"))
    trans = json.loads(trans_f.read_text("utf-8"))
    words = json.loads(words_f.read_text("utf-8"))

    paragraphs = []
    for i, tp in enumerate(trans):
        wp = words[i] if i < len(words) else {"sentences": []}
        word_map = {ws["original"]: ws.get("words", []) for ws in wp.get("sentences", [])}
        paragraphs.append({
            "original": tp.get("original", ""),
            "translation": tp.get("paragraph_translation", ""),
            "sentences": [{
                "original": s["original"],
                "translation": s.get("translation", ""),
                "words": word_map.get(s["original"], []),
            } for s in tp.get("sentences", [])],
        })

    final = {
        "id": jid,
        "book": "shiji",
        "juan": juan["juan"],
        "title": juan["title"],
        "category": juan["category"],
        "category_name": juan["category_name"],
        "order_in_category": juan["order_in_category"],
        "author": {"name": "司马迁", "dynasty": "西汉"},
        "summary": meta.get("summary", ""),
        "appreciation": meta.get("appreciation", ""),
        "tags": meta.get("tags", []),
        "key_figures": meta.get("key_figures", []),
        "historical_period": meta.get("historical_period", ""),
        "paragraphs": paragraphs,
    }
    out.write_text(json.dumps(final, ensure_ascii=False, indent=2), "utf-8")
    return f"✅ merge: {juan['title']}"


# ============================================================
# 并发执行器
# ============================================================

def run_step(fn, juans: list[dict], step_name: str):
    print(f"\n{'='*60}")
    print(f"🚀 {step_name} ({len(juans)} 卷, {MAX_WORKERS} workers)")
    print(f"{'='*60}", flush=True)

    done = skip = fail = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fn, j): j for j in juans}
        for future in as_completed(futures):
            try:
                msg = future.result()
                if "⏭" in msg:
                    skip += 1
                elif "✅" in msg:
                    done += 1
                    print(f"  {msg}", flush=True)
                else:
                    fail += 1
                    print(f"  {msg}", flush=True)
            except Exception as e:
                fail += 1
                j = futures[future]
                print(f"  ❌ {j['title']}: {e}", flush=True)

    elapsed = time.time() - t0
    print(f"\n📊 {step_name}: 完成{done} 跳过{skip} 失败{fail} 耗时{elapsed:.0f}s", flush=True)


def main():
    catalog = load_catalog()
    juans = pick_juans(catalog)
    print("=" * 60)
    print(f"🔥 史记 LLM 管线（{len(juans)}/{len(catalog['juan'])} 卷）")
    print(f"   MAX_WORKERS={MAX_WORKERS}  STEPS={sorted(STEPS)}")
    print("=" * 60, flush=True)

    total_chars = sum(j["char_count"] for j in juans)
    print(f"   目标字数: {total_chars:,}")
    print(f"   预计段落: {sum(j['paragraphs_count'] for j in juans):,}")

    t_start = time.time()

    if "meta" in STEPS:
        run_step(gen_meta, juans, "Step 1: 元数据")
    if "trans" in STEPS:
        run_step(gen_trans, juans, "Step 2: 逐段翻译")
    if "words" in STEPS:
        run_step(gen_words, juans, "Step 3: 逐词注释")
    if "merge" in STEPS:
        run_step(merge, juans, "Step 4: 合并")

    total = time.time() - t_start
    print(f"\n✅ 全部完成！总耗时 {total/60:.1f} 分钟")

    # 统计
    complete = sum(1 for j in juans if (OUT_DIR / f"{j['id']}.json").exists())
    print(f"📁 生成 {complete}/{len(juans)} 卷完整 JSON")


if __name__ == "__main__":
    main()
