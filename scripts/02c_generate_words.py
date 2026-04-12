#!/usr/bin/env python3
"""
Step 2c: 逐词注释（词组拆分 + 拼音 + 释义）
依赖 02b 的逐句拆分结果，对每个句子生成词组注释
批量处理：每次发送同一段落内的所有句子（节省 API 调用）
产出: data/articles/{dynasty}/{article_id}_words.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm_client import call_llm_json

BASE_DIR = Path(__file__).parent.parent
CATALOG_FILE = BASE_DIR / "data" / "catalog.json"

SYSTEM_PROMPT = """你是一位精通古代汉语的学者，擅长词汇训诂和音韵学。
你的回答必须是纯 JSON 格式，不要包含任何 markdown 标记或额外文字。"""

USER_PROMPT_TEMPLATE = """文章标题：{title}
作者：{author}

上下文段落：
{paragraph}

请对以下句子进行逐词注释：
{sentences_block}

要求：
1. 按**词组**拆分（不是逐字），如"郑武公"是一个词组，"泛舟"是一个词组
2. 虚词（之、乎、者、也、而、以、于、其、则、乃、为、所、且、若、焉、哉、矣、耳、兮等）单独标注
3. 每个词组提供：
   - word: 词组原文
   - pinyin: 拼音（用空格分隔多音节，如"zhèng wǔ gōng"）
   - meaning: 在本句中的具体含义（不要给通用释义，要结合上下文）
   - type: 分类，从以下选择：实词、虚词、人名、地名、官职、典故、书名
4. 注意多音字和通假字的正确标注
5. 所有词组拼接起来必须等于原文（不能遗漏任何字，包括标点符号前的字）

输出 JSON 格式：
{{
  "sentences": [
    {{
      "original": "原文句子",
      "words": [
        {{
          "word": "词组",
          "pinyin": "拼音",
          "meaning": "释义",
          "type": "类型"
        }}
      ]
    }}
  ]
}}"""


def process_article(article: dict, dynasty_id: str) -> bool:
    """处理单篇文章的逐词注释"""
    article_id = article["id"]
    output_file = BASE_DIR / "data" / "articles" / dynasty_id / f"{article_id}_words.json"
    trans_file = BASE_DIR / "data" / "articles" / dynasty_id / f"{article_id}_trans.json"

    # 增量
    if output_file.exists():
        print(f"  ⏭ 跳过: {article['title']}")
        return True

    # 依赖 02b 的翻译结果
    if not trans_file.exists():
        print(f"  ❌ 缺少翻译文件: {article['title']}")
        return False

    with open(trans_file, 'r', encoding='utf-8') as f:
        trans_data = json.load(f)

    print(f"  🔄 {article['title']} ({len(trans_data)}段)")

    all_results = []

    BATCH_SIZE = 2
    for para_idx, para_data in enumerate(trans_data):
        sentences = para_data.get("sentences", [])
        if not sentences:
            all_results.append({"sentences": []})
            continue

        merged = []
        for batch_start in range(0, len(sentences), BATCH_SIZE):
            batch = sentences[batch_start:batch_start + BATCH_SIZE]
            sentences_block = "\n".join(
                f'{i + 1}. "{s["original"]}"' for i, s in enumerate(batch)
            )
            prompt = USER_PROMPT_TEMPLATE.format(
                title=article["title"],
                author=article["author"],
                paragraph=para_data.get("original", ""),
                sentences_block=sentences_block,
            )
            try:
                result = call_llm_json(SYSTEM_PROMPT, prompt)
                merged.extend(result.get("sentences", []))
            except Exception as e:
                for s in batch:
                    merged.append({"original": s["original"], "words": [], "error": str(e)})

        all_results.append({"sentences": merged})
        print(f"    段{para_idx + 1}/{len(trans_data)} ({len(sentences)}句) ✓")

    # 保存
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"  ✅ {article['title']}")
    return True


def main():
    print("=" * 60)
    print("Step 2c: 逐词注释")
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
                if process_article(article, did):
                    success += 1

    print(f"\n📊 统计: 总计{total}篇, 成功{success}篇")


if __name__ == "__main__":
    main()
