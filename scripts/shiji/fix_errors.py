#!/usr/bin/env python3
"""
修复 shiji 管线中 error 段/批：重跑失败段的 trans，重跑失败句的 words。
不重跑已成功的内容，只替换 error 记录。
"""

import json
import os
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))
from llm_client import call_llm_json  # noqa: E402
# 从 run_shiji 导入 prompt 模板与辅助（避免重复定义）
sys.path.insert(0, str(Path(__file__).parent))
from run_shiji import (  # noqa: E402
    TRANS_SYSTEM, TRANS_USER, WORDS_SYSTEM, WORDS_USER,
    paragraphs_of, load_catalog, pick_juans,
)

BASE_DIR = Path(__file__).parent.parent.parent
OUT_DIR = BASE_DIR / "data/books/shiji/output"
WORDS_BATCH = int(os.environ.get("WORDS_BATCH", "5"))
INNER = int(os.environ.get("INNER_WORKERS", "15"))
MAX_W = int(os.environ.get("MAX_WORKERS", "10"))


def fix_trans_one(juan: dict, para_text: str, idx: int, total: int, ctx: str) -> dict:
    """重翻一段"""
    prompt = TRANS_USER.format(
        title=juan["title"], para_idx=idx + 1, total=total,
        context=ctx, paragraph=para_text,
    )
    try:
        r = call_llm_json(TRANS_SYSTEM, prompt)
        r["original"] = para_text
        return r
    except Exception as e:
        return {"original": para_text, "paragraph_translation": "",
                "sentences": [], "error": str(e)}


def fix_words_batch(juan: dict, para_text: str, batch: list) -> list:
    """重做一批逐词注释"""
    block = "\n".join(f'{i+1}. "{s["original"]}"' for i, s in enumerate(batch))
    prompt = WORDS_USER.format(title=juan["title"], paragraph=para_text, sentences_block=block)
    try:
        r = call_llm_json(WORDS_SYSTEM, prompt)
        return r.get("sentences", [])
    except Exception as e:
        return [{"original": s["original"], "words": [], "error": str(e)} for s in batch]


def fix_juan_trans(juan: dict) -> tuple[str, int, int]:
    """修复一卷的 trans 错误段"""
    jid = juan["id"]
    trans_f = OUT_DIR / f"{jid}_trans.json"
    if not trans_f.exists():
        return (f"❌ trans 不存在: {jid}", 0, 0)

    trans = json.loads(trans_f.read_text("utf-8"))
    paras = paragraphs_of(juan)

    # 找 error 段 index
    err_idx = [i for i, p in enumerate(trans) if p.get("error") or not p.get("sentences")]
    if not err_idx:
        return (f"⏭ {juan['title']}: 无错误段", 0, 0)

    # 构造 context
    def ctx_of(i: int) -> str:
        if i == 0:
            return "（本段为开篇）"
        ctx_paras = paras[max(0, i - 3):i]
        ctx = " ".join(ctx_paras)
        return ctx[-500:] if len(ctx) > 500 else ctx

    fixed = 0
    with ThreadPoolExecutor(max_workers=min(INNER, len(err_idx))) as pool:
        futures = {
            pool.submit(fix_trans_one, juan, paras[i], i, len(paras), ctx_of(i)): i
            for i in err_idx
        }
        for fut in as_completed(futures):
            i = futures[fut]
            r = fut.result()
            if not r.get("error") and r.get("sentences"):
                trans[i] = r
                fixed += 1
            else:
                # 仍失败，保留原来的 error
                trans[i] = r

    trans_f.write_text(json.dumps(trans, ensure_ascii=False, indent=2), "utf-8")
    return (f"✅ {juan['title']}: 修复 {fixed}/{len(err_idx)}", fixed, len(err_idx))


def fix_juan_words(juan: dict) -> tuple[str, int, int]:
    """修复一卷的 words 错误句"""
    jid = juan["id"]
    words_f = OUT_DIR / f"{jid}_words.json"
    trans_f = OUT_DIR / f"{jid}_trans.json"
    if not words_f.exists() or not trans_f.exists():
        return (f"❌ words/trans 不存在: {jid}", 0, 0)

    words = json.loads(words_f.read_text("utf-8"))
    trans = json.loads(trans_f.read_text("utf-8"))

    # 收集 error 批：(para_idx, batch_start, batch_sents, para_text)
    err_batches = []
    for pi, (trans_p, words_p) in enumerate(zip(trans, words)):
        para_text = trans_p.get("original", "")
        sents_trans = trans_p.get("sentences", [])
        sents_words = words_p.get("sentences", [])
        # words 数组可能缺漏或长度不匹配
        if len(sents_words) < len(sents_trans):
            # 补齐
            for _ in range(len(sents_trans) - len(sents_words)):
                sents_words.append({"original": "", "words": [], "error": "missing"})
            words_p["sentences"] = sents_words

        # 找错误句，按 BATCH 分组
        error_sent_idx = [i for i, s in enumerate(sents_words) if s.get("error") or not s.get("words")]
        if not error_sent_idx:
            continue
        # 按连续区间分批
        for b_start in range(0, len(sents_trans), WORDS_BATCH):
            b_end = min(b_start + WORDS_BATCH, len(sents_trans))
            # 本批中是否有 error 句？
            if any(i >= b_start and i < b_end for i in error_sent_idx):
                batch = sents_trans[b_start:b_end]
                err_batches.append((pi, b_start, b_end, batch, para_text))

    if not err_batches:
        return (f"⏭ {juan['title']}: 无错误批", 0, 0)

    fixed = 0
    with ThreadPoolExecutor(max_workers=min(INNER, len(err_batches))) as pool:
        futures = {
            pool.submit(fix_words_batch, juan, ptxt, batch): (pi, bs, be)
            for pi, bs, be, batch, ptxt in err_batches
        }
        for fut in as_completed(futures):
            pi, bs, be = futures[fut]
            new_sents = fut.result()
            # 把 new_sents 写回对应位置
            for offset, ns in enumerate(new_sents):
                target_idx = bs + offset
                if target_idx < len(words[pi]["sentences"]):
                    if not ns.get("error") and ns.get("words"):
                        words[pi]["sentences"][target_idx] = ns
                        fixed += 1

    words_f.write_text(json.dumps(words, ensure_ascii=False, indent=2), "utf-8")
    return (f"✅ {juan['title']}: 修复 {fixed}", fixed, len(err_batches))


def merge_juan(juan: dict) -> str:
    """重新合并一卷"""
    from run_shiji import merge
    return merge(juan)


def main():
    catalog = load_catalog()
    juans = pick_juans(catalog)

    STEPS = set(os.environ.get("STEP", "trans,words,merge").split(","))

    print(f"🔧 Fix 模式 ({len(juans)} 卷, STEPS={sorted(STEPS)})")

    if "trans" in STEPS:
        print(f"\n{'='*60}")
        print(f"Step A: 修复 trans")
        print(f"{'='*60}", flush=True)
        t0 = time.time()
        total_fixed = total_errs = 0
        with ThreadPoolExecutor(max_workers=MAX_W) as pool:
            futures = {pool.submit(fix_juan_trans, j): j for j in juans}
            for fut in as_completed(futures):
                msg, f, e = fut.result()
                total_fixed += f
                total_errs += e
                if "✅" in msg and f > 0:
                    print(f"  {msg}", flush=True)
        print(f"📊 trans 修复: {total_fixed}/{total_errs} 段 ({time.time()-t0:.0f}s)")

    if "words" in STEPS:
        print(f"\n{'='*60}")
        print(f"Step B: 修复 words")
        print(f"{'='*60}", flush=True)
        t0 = time.time()
        total_fixed = total_errs = 0
        with ThreadPoolExecutor(max_workers=MAX_W) as pool:
            futures = {pool.submit(fix_juan_words, j): j for j in juans}
            for fut in as_completed(futures):
                msg, f, e = fut.result()
                total_fixed += f
                total_errs += e
                if "✅" in msg and f > 0:
                    print(f"  {msg}", flush=True)
        print(f"📊 words 修复: {total_fixed} 句 ({time.time()-t0:.0f}s)")

    if "merge" in STEPS:
        print(f"\n{'='*60}")
        print(f"Step C: 重新合并")
        print(f"{'='*60}", flush=True)
        for j in juans:
            merge_juan(j)
        print(f"✅ 合并完成")


if __name__ == "__main__":
    main()
