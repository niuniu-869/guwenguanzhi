#!/usr/bin/env python3
"""
并发版全量管线：充分利用 100 RPM，最大化吞吐
管线逻辑：02a(meta) → 02b(trans) → 02c(words) → 02d(merge)
- 02a 对所有文章并发执行
- 02b 依赖 02a 完成，对所有文章并发执行
- 02c 依赖 02b 完成，对所有文章并发执行
- 02d 最后合并
实际上 02a 不依赖 02b，可以对不同文章交叉并行。
"""

import json
import sys
import time
import re
import os
import traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))
from llm_client import call_llm_json, call_llm, parse_json_response

BASE_DIR = Path(__file__).parent.parent
CATALOG_FILE = BASE_DIR / "data" / "catalog.json"

# 并发数：RPM=100，留余量，每个请求约 3-5s，20 并发足够打满
MAX_WORKERS = 20

# ============================================================
# Prompt 模板
# ============================================================

META_SYSTEM = "你是一位精通古代汉语的文学学者。回答必须是纯 JSON 格式，不含 markdown 标记。"
META_USER = """以下是《古文观止》中的一篇文章：
标题：{title}  作者：{author}（{dynasty}）  出处：{source}
原文：
{text}

生成 JSON：
{{"background":"写作背景(200-300字)","appreciation":"文学赏析(300-500字)","tags":["标签1","标签2","标签3"],"author_bio":"作者简介(100-200字，含字号生卒年)"}}"""

TRANS_SYSTEM = "你是精通古代汉语的翻译学者，风格信达雅。回答必须是纯 JSON。"
TRANS_USER = """文章：{title}（{author}）
全文上下文：
{full_text}

翻译第{para_idx}/{total}段：
---
{paragraph}
---

JSON格式：{{"paragraph_translation":"整段白话翻译","sentences":[{{"original":"原文句","translation":"白话翻译"}}]}}
按语义拆句，人名地名保留原文。"""

WORDS_SYSTEM = "你是精通古代汉语的训诂学者。回答必须是纯 JSON。"
WORDS_USER = """文章：{title}（{author}）
段落上下文：{paragraph}

逐词注释：
{sentences_block}

要求：按词组拆分(非逐字)，虚词单独标注，每个词提供 word/pinyin/meaning(10字以内)/type(实词|虚词|人名|地名|官职|典故)。
标点符号不要单独作为词条。meaning 务必简短。

JSON：{{"sentences":[{{"original":"原文","words":[{{"word":"词","pinyin":"拼音","meaning":"释义","type":"类型"}}]}}]}}"""

DYNASTY_NAMES = {
    "pre_qin": "先秦", "han": "两汉", "wei_jin": "魏晋南北朝",
    "tang": "唐", "song": "宋", "ming": "明",
}


def load_catalog():
    with open(CATALOG_FILE) as f:
        return json.load(f)


def all_articles(catalog):
    """展平所有文章"""
    for dynasty in catalog["dynasties"]:
        for author in dynasty["authors"]:
            for article in author["articles"]:
                yield article, dynasty["id"]


# ============================================================
# Step 2a: 元数据
# ============================================================

def gen_meta(article, dynasty_id):
    aid = article["id"]
    out = BASE_DIR / "data/articles" / dynasty_id / f"{aid}_meta.json"
    if out.exists():
        return f"⏭ {article['title']}"

    raw_file = BASE_DIR / article["raw_file"]
    if not raw_file.exists():
        return f"❌ {article['title']}: 原文不存在"

    text = raw_file.read_text("utf-8")
    prompt = META_USER.format(
        title=article["title"], author=article["author"],
        dynasty=DYNASTY_NAMES.get(dynasty_id, ""), source=article.get("source", ""),
        text=text,
    )
    try:
        result = call_llm_json(META_SYSTEM, prompt)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
        return f"✅ meta: {article['title']}"
    except Exception as e:
        return f"❌ meta: {article['title']} - {e}"


# ============================================================
# Step 2b: 逐段翻译
# ============================================================

def gen_trans(article, dynasty_id):
    aid = article["id"]
    out = BASE_DIR / "data/articles" / dynasty_id / f"{aid}_trans.json"
    if out.exists():
        return f"⏭ {article['title']}"

    raw_file = BASE_DIR / article["raw_file"]
    if not raw_file.exists():
        return f"❌ {article['title']}: 原文不存在"

    full_text = raw_file.read_text("utf-8")
    paragraphs = [p.strip() for p in full_text.split('\n') if p.strip()]
    if not paragraphs:
        return f"❌ {article['title']}: 空文"

    results = []
    for i, para in enumerate(paragraphs):
        prompt = TRANS_USER.format(
            title=article["title"], author=article["author"],
            full_text=full_text, para_idx=i+1, total=len(paragraphs),
            paragraph=para,
        )
        try:
            r = call_llm_json(TRANS_SYSTEM, prompt)
            r["original"] = para
            results.append(r)
        except Exception as e:
            results.append({"original": para, "paragraph_translation": "", "sentences": [], "error": str(e)})

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), "utf-8")
    return f"✅ trans: {article['title']} ({len(paragraphs)}段)"


# ============================================================
# Step 2c: 逐词注释
# ============================================================

def gen_words(article, dynasty_id):
    aid = article["id"]
    out = BASE_DIR / "data/articles" / dynasty_id / f"{aid}_words.json"
    trans_file = BASE_DIR / "data/articles" / dynasty_id / f"{aid}_trans.json"

    if out.exists():
        return f"⏭ {article['title']}"
    if not trans_file.exists():
        return f"❌ {article['title']}: 缺 trans"

    trans = json.loads(trans_file.read_text("utf-8"))
    all_results = []

    BATCH_SIZE = 3  # 每批3句（推理模型需 16384 max_tokens）
    for pi, para_data in enumerate(trans):
        sentences = para_data.get("sentences", [])
        if not sentences:
            all_results.append({"sentences": []})
            continue

        # 分批处理
        merged_sentences = []
        for batch_start in range(0, len(sentences), BATCH_SIZE):
            batch = sentences[batch_start:batch_start + BATCH_SIZE]
            block = "\n".join(f'{i+1}. "{s["original"]}"' for i, s in enumerate(batch))
            prompt = WORDS_USER.format(
                title=article["title"], author=article["author"],
                paragraph=para_data.get("original", ""),
                sentences_block=block,
            )
            try:
                r = call_llm_json(WORDS_SYSTEM, prompt)
                merged_sentences.extend(r.get("sentences", []))
            except Exception as e:
                # 为本批每句填空
                for s in batch:
                    merged_sentences.append({"original": s["original"], "words": [], "error": str(e)})
        all_results.append({"sentences": merged_sentences})

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), "utf-8")
    return f"✅ words: {article['title']}"


# ============================================================
# Step 2d: 合并
# ============================================================

def merge(article, dynasty_id):
    aid = article["id"]
    d = BASE_DIR / "data/articles" / dynasty_id
    meta_f, trans_f, words_f = d/f"{aid}_meta.json", d/f"{aid}_trans.json", d/f"{aid}_words.json"
    out = d / f"{aid}.json"

    if not all(f.exists() for f in [meta_f, trans_f, words_f]):
        return f"❌ merge: {article['title']}: 缺文件"

    meta = json.loads(meta_f.read_text("utf-8"))
    trans = json.loads(trans_f.read_text("utf-8"))
    words = json.loads(words_f.read_text("utf-8"))

    paragraphs = []
    for i, tp in enumerate(trans):
        wp = words[i] if i < len(words) else {"sentences": []}
        word_map = {ws["original"]: ws.get("words", []) for ws in wp.get("sentences", [])}
        para = {
            "original": tp.get("original", ""),
            "translation": tp.get("paragraph_translation", ""),
            "sentences": [{
                "original": s["original"],
                "translation": s.get("translation", ""),
                "words": word_map.get(s["original"], []),
            } for s in tp.get("sentences", [])],
        }
        paragraphs.append(para)

    final = {
        "id": aid, "title": article["title"],
        "author": {"id": f"{dynasty_id}_{article['author']}", "name": article["author"],
                    "dynasty": dynasty_id, "bio": meta.get("author_bio", "")},
        "source": article.get("source", ""), "dynasty": dynasty_id,
        "volume": article.get("volume", 0),
        "background": meta.get("background", ""),
        "appreciation": meta.get("appreciation", ""),
        "tags": meta.get("tags", []),
        "paragraphs": paragraphs,
    }
    out.write_text(json.dumps(final, ensure_ascii=False, indent=2), "utf-8")
    return f"✅ merge: {article['title']}"


# ============================================================
# 主管线
# ============================================================

def run_step(fn, articles, step_name):
    """并发执行一个步骤"""
    print(f"\n{'='*50}")
    print(f"🚀 {step_name} ({len(articles)}篇, {MAX_WORKERS}并发)")
    print(f"{'='*50}", flush=True)

    done, skip, fail = 0, 0, 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fn, a, d): (a, d) for a, d in articles}
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
                a, d = futures[future]
                print(f"  ❌ {a['title']}: {e}", flush=True)

    elapsed = time.time() - t0
    print(f"\n📊 {step_name}: 新增{done} 跳过{skip} 失败{fail} 耗时{elapsed:.0f}s", flush=True)


def main():
    print("=" * 60)
    print("🔥 全量并发管线")
    print("=" * 60, flush=True)

    catalog = load_catalog()
    articles = list(all_articles(catalog))
    print(f"共 {len(articles)} 篇文章", flush=True)

    t_start = time.time()

    # Step 1: 元数据（互相不依赖，全部并发）
    run_step(gen_meta, articles, "Step 2a: 元数据")

    # Step 2: 逐段翻译（依赖原文，互相不依赖，全部并发）
    run_step(gen_trans, articles, "Step 2b: 逐段翻译")

    # Step 3: 逐词注释（依赖 trans，互相不依赖，全部并发）
    run_step(gen_words, articles, "Step 2c: 逐词注释")

    # Step 4: 合并（纯本地操作，极快）
    run_step(merge, articles, "Step 2d: 合并")

    total = time.time() - t_start
    print(f"\n✅ 全部完成！总耗时 {total/60:.1f} 分钟", flush=True)

    # 统计最终文件
    count = 0
    for a, d in articles:
        f = BASE_DIR / "data/articles" / d / f"{a['id']}.json"
        if f.exists():
            count += 1
    print(f"📁 生成 {count}/{len(articles)} 篇完整文章 JSON", flush=True)


if __name__ == "__main__":
    main()
