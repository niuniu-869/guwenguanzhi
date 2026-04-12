#!/usr/bin/env python3
"""
修复脚本：
1. 补齐缺失文章的 meta/trans/words
2. 重跑质量差的 words
3. 重新 merge 所有受影响的文章
"""

import json, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))
from llm_client import call_llm_json

BASE = Path(__file__).parent.parent
CATALOG = json.loads((BASE / "data/catalog.json").read_text())

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

WORDS_SYSTEM = "你是精通古代汉语的训诂学者。回答纯JSON。"
WORDS_USER = """文章：{title}（{author}）  段落上下文：{paragraph}

逐词注释：
{sentences_block}

要求：按词组拆分(非逐字)，虚词单独标注，每个词提供 word/pinyin/meaning(10字以内)/type(实词|虚词|人名|地名|官职|典故)。标点不要作为词条。meaning务必简短。所有词拼接后去掉标点必须等于原文去掉标点。

JSON：{{"sentences":[{{"original":"原文","words":[{{"word":"词","pinyin":"拼音","meaning":"释义","type":"类型"}}]}}]}}"""

DYNASTY_NAMES = {"pre_qin":"先秦","han":"两汉","wei_jin":"魏晋南北朝","tang":"唐","song":"宋","ming":"明"}
BATCH = 3


def find_article(aid):
    for d in CATALOG["dynasties"]:
        for a in d["authors"]:
            for art in a["articles"]:
                if art["id"] == aid:
                    return art, d["id"]
    return None, None


def gen_meta(article, did):
    raw = (BASE / article["raw_file"]).read_text("utf-8")
    r = call_llm_json(META_SYSTEM, META_USER.format(
        title=article["title"], author=article["author"],
        dynasty=DYNASTY_NAMES.get(did,""), source=article.get("source",""), text=raw))
    out = BASE / "data/articles" / did / f"{article['id']}_meta.json"
    out.write_text(json.dumps(r, ensure_ascii=False, indent=2), "utf-8")
    return r


def gen_trans(article, did):
    raw = (BASE / article["raw_file"]).read_text("utf-8")
    paras = [p.strip() for p in raw.split('\n') if p.strip()]
    results = []
    for i, p in enumerate(paras):
        r = call_llm_json(TRANS_SYSTEM, TRANS_USER.format(
            title=article["title"], author=article["author"],
            full_text=raw, para_idx=i+1, total=len(paras), paragraph=p))
        r["original"] = p
        results.append(r)
    out = BASE / "data/articles" / did / f"{article['id']}_trans.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), "utf-8")
    return results


def gen_words(article, did):
    trans = json.loads((BASE / "data/articles" / did / f"{article['id']}_trans.json").read_text())
    all_results = []
    for tp in trans:
        sentences = tp.get("sentences", [])
        if not sentences:
            all_results.append({"sentences": []})
            continue
        merged = []
        for i in range(0, len(sentences), BATCH):
            batch = sentences[i:i+BATCH]
            block = "\n".join(f'{j+1}. "{s["original"]}"' for j, s in enumerate(batch))
            try:
                r = call_llm_json(WORDS_SYSTEM, WORDS_USER.format(
                    title=article["title"], author=article["author"],
                    paragraph=tp.get("original","")[:300], sentences_block=block))
                merged.extend(r.get("sentences", []))
            except Exception as e:
                for s in batch:
                    merged.append({"original": s["original"], "words": [], "error": str(e)})
        all_results.append({"sentences": merged})
    out = BASE / "data/articles" / did / f"{article['id']}_words.json"
    out.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), "utf-8")
    return all_results


def merge(article, did):
    d = BASE / "data/articles" / did
    meta = json.loads((d / f"{article['id']}_meta.json").read_text())
    trans = json.loads((d / f"{article['id']}_trans.json").read_text())
    words = json.loads((d / f"{article['id']}_words.json").read_text())
    paragraphs = []
    for i, tp in enumerate(trans):
        wp = words[i] if i < len(words) else {"sentences": []}
        wm = {ws["original"]: ws.get("words", []) for ws in wp.get("sentences", [])}
        paragraphs.append({
            "original": tp.get("original", ""),
            "translation": tp.get("paragraph_translation", ""),
            "sentences": [{"original": s["original"], "translation": s.get("translation",""),
                          "words": wm.get(s["original"], [])} for s in tp.get("sentences", [])],
        })
    final = {
        "id": article["id"], "title": article["title"],
        "author": {"id": f"{did}_{article['author']}", "name": article["author"],
                    "dynasty": did, "bio": meta.get("author_bio", "")},
        "source": article.get("source",""), "dynasty": did,
        "volume": article.get("volume",0),
        "background": meta.get("background",""),
        "appreciation": meta.get("appreciation",""),
        "tags": meta.get("tags",[]), "paragraphs": paragraphs,
    }
    (d / f"{article['id']}.json").write_text(json.dumps(final, ensure_ascii=False, indent=2), "utf-8")


# ============================================================

def fix_missing(aid, did):
    article, _ = find_article(aid)
    if not article:
        return f"❌ 找不到 {aid}"
    print(f"  🔧 补齐: {article['title']} (meta+trans+words+merge)", flush=True)
    gen_meta(article, did)
    gen_trans(article, did)
    gen_words(article, did)
    merge(article, did)
    return f"  ✅ 补齐: {article['title']}"


def fix_words(aid, did):
    article, _ = find_article(aid)
    if not article:
        return f"❌ 找不到 {aid}"
    # 删除旧的 words 和 merged
    (BASE / "data/articles" / did / f"{aid}_words.json").unlink(missing_ok=True)
    (BASE / "data/articles" / did / f"{aid}.json").unlink(missing_ok=True)
    gen_words(article, did)
    merge(article, did)
    return f"  ✅ 重跑: {article['title']}"


def main():
    print("=" * 60)
    print("🔧 修复与重跑")
    print("=" * 60, flush=True)

    # 1. 缺失文章
    missing = [("033_子产论政宽猛", "pre_qin")]
    print(f"\n补齐 {len(missing)} 篇缺失:", flush=True)
    for aid, did in missing:
        print(fix_missing(aid, did), flush=True)

    # 2. 质量差的文章 - 只重跑 words
    poor_ids = [
        "001_郑伯克段于鄢","004_臧僖伯谏观鱼","007_季梁谏追楚师","008_曹刿论战",
        "009_齐桓公伐楚盟屈完","010_宫之奇谏假道","011_齐桓下拜受胙","012_阴饴甥对秦伯",
        "015_介之推不言禄","016_展喜犒师","021_齐国佐不辱命","022_楚归晋知䓨",
        "025_祁奚请免叔向","027_晏子不死君难","028_季札观周乐","030_子产论尹何为邑",
        "032_子革对灵王","047_宋人及楚人平","050_虞师晋师灭夏阳","051_晋献公杀世子申生",
        "052_曾子易箦","053_有子之言似夫子","054_子重耳对秦客","055_杜篑扬觯",
        "056_晋献文子成室","060_邹忌讽齐王纳谏","061_颜斶说秦王","062_冯谖客孟尝君",
        "065_触詟说赵太后","066_鲁仲连义不帝秦","067_鲁共公择言","068_唐雎说信陵君",
        "069_唐雎不辱使命","078_孔子世家赞","085_滑稽列传","087_太史公自序",
        "097_上书谏猎司马","127_讳辨","138_送石处士序","188_放鹤亭记",
        "207_司马季主论卜","218_沧浪亭记",
    ]

    # 确定每篇的 dynasty
    poor = []
    for aid in poor_ids:
        art, did = find_article(aid)
        if art:
            poor.append((aid, did))

    print(f"\n重跑 {len(poor)} 篇质量差的 words (10并发):", flush=True)
    t0 = time.time()
    ok, fail = 0, 0
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(fix_words, aid, did): aid for aid, did in poor}
        for f in as_completed(futures):
            try:
                msg = f.result()
                print(msg, flush=True)
                ok += 1
            except Exception as e:
                fail += 1
                print(f"  ❌ {futures[f]}: {e}", flush=True)

    elapsed = time.time() - t0
    print(f"\n📊 重跑完成: {ok}成功 {fail}失败 耗时{elapsed:.0f}s", flush=True)


if __name__ == "__main__":
    main()
