#!/usr/bin/env python3
"""
Step 2d: 合并元数据、翻译、词注释为最终 JSON
产出: data/articles/{dynasty}/{article_id}.json
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CATALOG_FILE = BASE_DIR / "data" / "catalog.json"


def merge_article(article: dict, dynasty_id: str) -> bool:
    """合并单篇文章的所有数据"""
    article_id = article["id"]
    articles_dir = BASE_DIR / "data" / "articles" / dynasty_id

    meta_file = articles_dir / f"{article_id}_meta.json"
    trans_file = articles_dir / f"{article_id}_trans.json"
    words_file = articles_dir / f"{article_id}_words.json"
    output_file = articles_dir / f"{article_id}.json"

    # 检查依赖文件
    missing = []
    if not meta_file.exists():
        missing.append("meta")
    if not trans_file.exists():
        missing.append("trans")
    if not words_file.exists():
        missing.append("words")

    if missing:
        print(f"  ❌ {article['title']}: 缺少 {', '.join(missing)}")
        return False

    # 读取数据
    with open(meta_file, 'r', encoding='utf-8') as f:
        meta = json.load(f)
    with open(trans_file, 'r', encoding='utf-8') as f:
        trans = json.load(f)
    with open(words_file, 'r', encoding='utf-8') as f:
        words = json.load(f)

    # 读取原文
    raw_file = BASE_DIR / article["raw_file"]
    full_text = raw_file.read_text(encoding='utf-8') if raw_file.exists() else ""

    # 合并段落
    paragraphs = []
    for i, trans_para in enumerate(trans):
        para = {
            "original": trans_para.get("original", ""),
            "translation": trans_para.get("paragraph_translation", ""),
            "sentences": [],
        }

        # 合并句子和词注释
        trans_sentences = trans_para.get("sentences", [])
        word_sentences = words[i].get("sentences", []) if i < len(words) else []

        # 按原文匹配句子
        word_map = {ws["original"]: ws.get("words", []) for ws in word_sentences}

        for ts in trans_sentences:
            original = ts["original"]
            sentence = {
                "original": original,
                "translation": ts.get("translation", ""),
                "words": word_map.get(original, []),
            }
            paragraphs.append(None)  # placeholder
            para["sentences"].append(sentence)

        paragraphs.pop() if paragraphs and paragraphs[-1] is None else None
        paragraphs.append(para) if para["sentences"] or para["original"] else None

    # 重建 paragraphs（去掉 None placeholder）
    paragraphs = []
    for i, trans_para in enumerate(trans):
        para = {
            "original": trans_para.get("original", ""),
            "translation": trans_para.get("paragraph_translation", ""),
            "sentences": [],
        }

        trans_sentences = trans_para.get("sentences", [])
        word_sentences = words[i].get("sentences", []) if i < len(words) else []
        word_map = {ws["original"]: ws.get("words", []) for ws in word_sentences}

        for ts in trans_sentences:
            para["sentences"].append({
                "original": ts["original"],
                "translation": ts.get("translation", ""),
                "words": word_map.get(ts["original"], []),
            })

        paragraphs.append(para)

    # 构建最终 JSON
    final = {
        "id": article_id,
        "title": article["title"],
        "author": {
            "id": f"{dynasty_id}_{article['author']}",
            "name": article["author"],
            "dynasty": dynasty_id,
            "bio": meta.get("author_bio", ""),
        },
        "source": article.get("source", ""),
        "dynasty": dynasty_id,
        "volume": article.get("volume", 0),
        "background": meta.get("background", ""),
        "appreciation": meta.get("appreciation", ""),
        "tags": meta.get("tags", []),
        "paragraphs": paragraphs,
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    print(f"  ✅ {article['title']}")
    return True


def main():
    print("=" * 60)
    print("Step 2d: 合并为最终 JSON")
    print("=" * 60)

    with open(CATALOG_FILE, 'r', encoding='utf-8') as f:
        catalog = json.load(f)

    total = 0
    success = 0

    for dynasty in catalog["dynasties"]:
        did = dynasty["id"]
        print(f"\n📖 {dynasty['name']}:")

        for author in dynasty["authors"]:
            for article in author["articles"]:
                total += 1
                if merge_article(article, did):
                    success += 1

    print(f"\n📊 统计: 总计{total}篇, 成功合并{success}篇")


if __name__ == "__main__":
    main()
