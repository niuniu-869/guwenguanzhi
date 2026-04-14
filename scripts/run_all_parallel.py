#!/usr/bin/env python3
"""
古文观止全量并发管线 v2（使用 scripts/prompts/ 集中化 prompt）

升级亮点：
- Prompt 从 scripts/prompts/ 集中加载（可被 Skill 共享）
- 每个输出 JSON 嵌入 `_prompt_version`，不匹配当前版本自动重跑
- words 批次失败时 fallback 到逐句重试，消除静默空 words
- 运行完自动 migrate → data/books/guwenguanzhi/

环境变量：
  MAX_WORKERS       卷间/篇间并发（默认 20）
  MIMO_RPM          速率限制（默认 90）
  FORCE             任意非空值 = 无视版本全量重跑
  STEP              meta,trans,words,merge 任选子集

管线逻辑：02a(meta) → 02b(trans) → 02c(words) → 02d(merge)
"""

import json
import os
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))
from llm_client import call_llm_json  # noqa: E402
from prompts import load_prompt, PROMPT_VERSION  # noqa: E402

BASE_DIR = Path(__file__).parent.parent
CATALOG_FILE = BASE_DIR / "data" / "catalog.json"

MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "20"))
FORCE = bool(os.environ.get("FORCE", ""))
STEPS = set(os.environ.get("STEP", "meta,trans,words,merge").split(","))
WORDS_BATCH = int(os.environ.get("WORDS_BATCH", "2"))

DYNASTY_NAMES = {
    "pre_qin": "先秦", "han": "两汉", "wei_jin": "魏晋南北朝",
    "tang": "唐", "song": "宋", "ming": "明",
}


# ============================================================
# 工具函数
# ============================================================

def _is_current_version(path: Path) -> bool:
    """检查已存在文件是否为当前 prompt 版本"""
    if FORCE or not path.exists():
        return False
    try:
        data = json.loads(path.read_text("utf-8"))
        # dict 顶层或 list[0] 里找 _prompt_version
        if isinstance(data, dict):
            return data.get("_prompt_version") == PROMPT_VERSION
        if isinstance(data, list) and data:
            return isinstance(data[0], dict) and data[0].get("_prompt_version") == PROMPT_VERSION
    except Exception:
        return False
    return False


def _write_tagged(path: Path, data) -> None:
    """写 JSON 并打上 _prompt_version 标签"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, dict):
        data = {"_prompt_version": PROMPT_VERSION, **data}
    elif isinstance(data, list):
        # 每段（list 元素）各加一个标签，便于后续 step 兼容
        data = [{"_prompt_version": PROMPT_VERSION, **d} if isinstance(d, dict) else d
                for d in data]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def _strip_tag(data):
    """读取时去掉 _prompt_version 便于后续处理"""
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k != "_prompt_version"}
    if isinstance(data, list):
        return [_strip_tag(d) for d in data]
    return data


def load_catalog():
    return json.loads(CATALOG_FILE.read_text("utf-8"))


def all_articles(catalog):
    for dynasty in catalog["dynasties"]:
        for author in dynasty["authors"]:
            for article in author["articles"]:
                yield article, dynasty["id"]


# ============================================================
# Step 2a: 元数据（meta）
# ============================================================

def gen_meta(article, dynasty_id):
    aid = article["id"]
    out = BASE_DIR / "data/articles" / dynasty_id / f"{aid}_meta.json"
    if _is_current_version(out):
        return f"⏭ meta: {article['title']}"

    raw_file = BASE_DIR / article["raw_file"]
    if not raw_file.exists():
        return f"❌ meta: {article['title']}: 原文不存在"

    text = raw_file.read_text("utf-8")
    try:
        system = load_prompt("meta/system.md")
        user = load_prompt("meta/user_guwenguanzhi.md",
                           title=article["title"], author=article["author"],
                           dynasty=DYNASTY_NAMES.get(dynasty_id, ""),
                           source=article.get("source", ""), text=text)
        result = call_llm_json(system, user)
        _write_tagged(out, result)
        return f"✅ meta: {article['title']}"
    except Exception as e:
        return f"❌ meta: {article['title']} - {e}"


# ============================================================
# Step 2b: 逐段翻译（trans）
# ============================================================

def _trans_one_para(article, paragraph, idx, total, context):
    """翻译单段（带重试）"""
    system = load_prompt("translation/system.md")
    user = load_prompt("translation/user.md",
                       title=article["title"], author=article["author"],
                       para_idx=idx + 1, total=total,
                       context=context, paragraph=paragraph)
    r = call_llm_json(system, user)
    r["original"] = paragraph
    return r


def gen_trans(article, dynasty_id):
    aid = article["id"]
    out = BASE_DIR / "data/articles" / dynasty_id / f"{aid}_trans.json"
    if _is_current_version(out):
        return f"⏭ trans: {article['title']}"

    raw_file = BASE_DIR / article["raw_file"]
    if not raw_file.exists():
        return f"❌ trans: {article['title']}: 原文不存在"

    full_text = raw_file.read_text("utf-8")
    paragraphs = [p.strip() for p in full_text.split('\n') if p.strip()]
    if not paragraphs:
        return f"❌ trans: {article['title']}: 空文"

    results = []
    for i, para in enumerate(paragraphs):
        # 上下文：前 3 段（最多 500 字）
        if i == 0:
            context = "（本段为开篇）"
        else:
            ctx_paras = paragraphs[max(0, i - 3):i]
            context = " ".join(ctx_paras)
            if len(context) > 500:
                context = context[-500:]

        try:
            r = _trans_one_para(article, para, i, len(paragraphs), context)
            results.append(r)
        except Exception as e:
            results.append({
                "original": para, "paragraph_translation": "",
                "sentences": [], "error": str(e),
            })

    _write_tagged(out, results)
    return f"✅ trans: {article['title']} ({len(paragraphs)}段)"


# ============================================================
# Step 2c: 逐词注释（words）— 带 fallback 重试
# ============================================================

def _words_batch(article, paragraph, sentences):
    """对一批句子生成词注释。失败会由外层 fallback 处理。"""
    block = "\n".join(f'{i + 1}. "{s["original"]}"' for i, s in enumerate(sentences))
    system = load_prompt("words/system.md")
    user = load_prompt("words/user.md",
                       title=article["title"], author=article["author"],
                       paragraph=paragraph, sentences_block=block)
    r = call_llm_json(system, user)
    return r.get("sentences", [])


def _words_one_sentence(article, paragraph, sentence):
    """单句重试（fallback），保证失败只影响单句"""
    try:
        sents = _words_batch(article, paragraph, [sentence])
        if sents and sents[0].get("words"):
            return sents[0]
    except Exception:
        pass
    return {"original": sentence["original"], "words": [],
            "error": "fallback failed"}


def gen_words(article, dynasty_id):
    aid = article["id"]
    out = BASE_DIR / "data/articles" / dynasty_id / f"{aid}_words.json"
    trans_file = BASE_DIR / "data/articles" / dynasty_id / f"{aid}_trans.json"

    if _is_current_version(out):
        return f"⏭ words: {article['title']}"
    if not trans_file.exists():
        return f"❌ words: {article['title']}: 缺 trans"

    trans = _strip_tag(json.loads(trans_file.read_text("utf-8")))
    all_results = []

    for pi, para_data in enumerate(trans):
        sentences = para_data.get("sentences", [])
        if not sentences:
            all_results.append({"sentences": []})
            continue

        merged = []
        for batch_start in range(0, len(sentences), WORDS_BATCH):
            batch = sentences[batch_start:batch_start + WORDS_BATCH]
            para_text = para_data.get("original", "")

            # 尝试整批
            try:
                result = _words_batch(article, para_text, batch)
                # 校验：结果条数匹配且都有 words
                if (len(result) == len(batch) and
                        all(r.get("words") for r in result)):
                    merged.extend(result)
                    continue
            except Exception:
                pass

            # Fallback：逐句重试
            for s in batch:
                merged.append(_words_one_sentence(article, para_text, s))

        all_results.append({"sentences": merged})

    _write_tagged(out, all_results)
    return f"✅ words: {article['title']}"


# ============================================================
# Step 2d: 合并
# ============================================================

def merge(article, dynasty_id):
    aid = article["id"]
    d = BASE_DIR / "data/articles" / dynasty_id
    meta_f = d / f"{aid}_meta.json"
    trans_f = d / f"{aid}_trans.json"
    words_f = d / f"{aid}_words.json"
    out = d / f"{aid}.json"

    if not all(f.exists() for f in [meta_f, trans_f, words_f]):
        missing = [f.name for f in [meta_f, trans_f, words_f] if not f.exists()]
        return f"❌ merge: {article['title']}: 缺 {missing}"

    if _is_current_version(out):
        return f"⏭ merge: {article['title']}"

    meta = _strip_tag(json.loads(meta_f.read_text("utf-8")))
    trans = _strip_tag(json.loads(trans_f.read_text("utf-8")))
    words = _strip_tag(json.loads(words_f.read_text("utf-8")))

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
        "id": aid, "title": article["title"],
        "author": {"id": f"{dynasty_id}_{article['author']}", "name": article["author"],
                   "dynasty": dynasty_id, "bio": meta.get("author_bio", "")},
        "source": article.get("source", ""), "dynasty": dynasty_id,
        "volume": article.get("volume", 0),
        "background": meta.get("background", ""),
        "appreciation": meta.get("appreciation", ""),
        "tags": meta.get("tags", []),
        "characters": meta.get("characters", []),
        "paragraphs": paragraphs,
    }
    _write_tagged(out, final)
    return f"✅ merge: {article['title']}"


# ============================================================
# 主管线
# ============================================================

def run_step(fn, articles, step_name):
    print(f"\n{'=' * 60}")
    print(f"🚀 {step_name}  ({len(articles)} 篇, {MAX_WORKERS} workers, FORCE={FORCE})")
    print(f"{'=' * 60}", flush=True)

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
    print(f"\n📊 {step_name}: 完成{done} 跳过{skip} 失败{fail} 耗时{elapsed:.0f}s", flush=True)
    return done, skip, fail


def main():
    print("=" * 60)
    print(f"🔥 古文观止全量管线  prompt_version={PROMPT_VERSION}")
    print(f"   MAX_WORKERS={MAX_WORKERS}  STEPS={sorted(STEPS)}  FORCE={FORCE}")
    print("=" * 60, flush=True)

    catalog = load_catalog()
    articles = list(all_articles(catalog))
    print(f"   共 {len(articles)} 篇文章", flush=True)

    t_start = time.time()

    if "meta" in STEPS:
        run_step(gen_meta, articles, "Step 2a: 元数据")
    if "trans" in STEPS:
        run_step(gen_trans, articles, "Step 2b: 逐段翻译")
    if "words" in STEPS:
        run_step(gen_words, articles, "Step 2c: 逐词注释")
    if "merge" in STEPS:
        run_step(merge, articles, "Step 2d: 合并")

    total = time.time() - t_start
    print(f"\n✅ 管线完成！总耗时 {total / 60:.1f} 分钟", flush=True)

    # 统计
    count = sum(1 for a, d in articles
                if (BASE_DIR / "data/articles" / d / f"{a['id']}.json").exists())
    print(f"📁 生成 {count}/{len(articles)} 篇完整文章 JSON", flush=True)


if __name__ == "__main__":
    main()
