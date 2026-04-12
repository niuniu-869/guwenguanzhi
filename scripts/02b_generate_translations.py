#!/usr/bin/env python3
"""
Step 2b: 逐段翻译（整段白话翻译 + 逐句翻译）
对每篇文章的每个段落分别调用 LLM，带全文上下文
产出: data/articles/{dynasty}/{article_id}_trans.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm_client import call_llm_json

BASE_DIR = Path(__file__).parent.parent
CATALOG_FILE = BASE_DIR / "data" / "catalog.json"

SYSTEM_PROMPT = """你是一位精通古代汉语的翻译学者，翻译风格追求"信达雅"。
你的回答必须是纯 JSON 格式，不要包含任何 markdown 标记或额外文字。"""

USER_PROMPT_TEMPLATE = """文章标题：{title}
作者：{author}

全文（供参考上下文，不需要翻译全文）：
{full_text}

请翻译以下段落（第 {para_idx}/{total_paras} 段）：
---
{paragraph}
---

要求：
1. 提供整段的白话翻译（paragraph_translation）
2. 将此段按语义拆分为若干句。一句是一个完整的语义单元，通常以句号、问号、叹号结尾，但也可以将语义紧密的短句合并
3. 每句提供准确的白话翻译
4. 翻译要信达雅，自然流畅，不要翻译腔
5. 人名地名保留原文

输出 JSON 格式：
{{
  "paragraph_translation": "整段的白话翻译",
  "sentences": [
    {{
      "original": "原文句子",
      "translation": "白话翻译"
    }}
  ]
}}"""


def process_article(article: dict, dynasty_id: str) -> bool:
    """处理单篇文章的逐段翻译"""
    article_id = article["id"]
    output_file = BASE_DIR / "data" / "articles" / dynasty_id / f"{article_id}_trans.json"

    # 增量：跳过已生成的
    if output_file.exists():
        print(f"  ⏭ 跳过: {article['title']}")
        return True

    # 读取原文
    raw_file = BASE_DIR / article["raw_file"]
    if not raw_file.exists():
        print(f"  ❌ 原文不存在: {raw_file}")
        return False

    full_text = raw_file.read_text(encoding='utf-8')
    paragraphs = [p.strip() for p in full_text.split('\n') if p.strip()]

    if not paragraphs:
        print(f"  ❌ 原文为空: {article['title']}")
        return False

    print(f"  🔄 {article['title']} ({len(paragraphs)}段)")

    results = []
    for i, para in enumerate(paragraphs):
        prompt = USER_PROMPT_TEMPLATE.format(
            title=article["title"],
            author=article["author"],
            full_text=full_text,
            para_idx=i + 1,
            total_paras=len(paragraphs),
            paragraph=para,
        )

        try:
            result = call_llm_json(SYSTEM_PROMPT, prompt)
            result["original"] = para
            results.append(result)
            print(f"    段{i + 1}/{len(paragraphs)} ✓")
        except Exception as e:
            print(f"    段{i + 1}/{len(paragraphs)} ❌ {e}")
            # 保存部分结果以支持断点续跑
            results.append({
                "original": para,
                "paragraph_translation": "",
                "sentences": [],
                "error": str(e),
            })

    # 保存
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"  ✅ {article['title']}")
    return True


def main():
    print("=" * 60)
    print("Step 2b: 逐段翻译")
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
