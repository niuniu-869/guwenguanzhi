#!/usr/bin/env python3
"""
Step 2a: 为每篇文章生成元数据（背景、赏析、标签、作者简介）
产出: data/articles/{dynasty}/{article_id}_meta.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm_client import call_llm_json

BASE_DIR = Path(__file__).parent.parent
CATALOG_FILE = BASE_DIR / "data" / "catalog.json"

SYSTEM_PROMPT = """你是一位精通古代汉语的文学学者，对《古文观止》的每一篇文章都了如指掌。
你的回答必须是纯 JSON 格式，不要包含任何 markdown 标记或额外文字。"""

USER_PROMPT_TEMPLATE = """以下是《古文观止》中的一篇文章：

标题：{title}
作者：{author}（{dynasty}）
出处：{source}

原文：
{text}

请为这篇文章生成以下信息（JSON格式）：

{{
  "background": "写作背景介绍（200-300字，交代时代背景、写作动机、历史事件）",
  "appreciation": "文学赏析（300-500字，分析艺术特色、修辞手法、思想内涵、文学地位）",
  "tags": ["标签1", "标签2", "标签3"],
  "author_bio": "作者简介（100-200字，包含字号、生卒年、主要成就）"
}}

要求：
1. background 要有具体的历史事件和人物
2. appreciation 要有文学专业性，分析修辞、结构、意境
3. tags 3-5个，从以下类别选择或自拟：叙事、议论、抒情、山水、哲理、政治、军事、人物、书信、序跋、碑铭、赋、骈文、策论、奏疏、祭文
4. author_bio 包含字号、朝代、代表作"""


def get_dynasty_name(dynasty_id: str) -> str:
    names = {
        "pre_qin": "先秦", "han": "两汉", "wei_jin": "魏晋南北朝",
        "tang": "唐", "song": "宋", "ming": "明",
    }
    return names.get(dynasty_id, dynasty_id)


def process_article(article: dict, dynasty_id: str) -> dict | None:
    """处理单篇文章，返回元数据"""
    article_id = article["id"]
    output_file = BASE_DIR / "data" / "articles" / dynasty_id / f"{article_id}_meta.json"

    # 增量：跳过已生成的
    if output_file.exists():
        print(f"  ⏭ 跳过(已存在): {article['title']}")
        return None

    # 读取原文
    raw_file = BASE_DIR / article["raw_file"]
    if not raw_file.exists():
        print(f"  ❌ 原文不存在: {raw_file}")
        return None

    text = raw_file.read_text(encoding='utf-8')

    prompt = USER_PROMPT_TEMPLATE.format(
        title=article["title"],
        author=article["author"],
        dynasty=get_dynasty_name(dynasty_id),
        source=article.get("source", ""),
        text=text,
    )

    print(f"  🔄 生成: {article['title']} ({article['author']})")

    try:
        result = call_llm_json(SYSTEM_PROMPT, prompt)
        # 保存
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"  ✅ 完成: {article['title']}")
        return result
    except Exception as e:
        print(f"  ❌ 失败: {article['title']} - {e}")
        return None


def main():
    print("=" * 60)
    print("Step 2a: 生成文章元数据")
    print("=" * 60)

    with open(CATALOG_FILE, 'r', encoding='utf-8') as f:
        catalog = json.load(f)

    total = 0
    success = 0
    skipped = 0

    for dynasty in catalog["dynasties"]:
        did = dynasty["id"]
        print(f"\n📖 {dynasty['name']}:")

        for author in dynasty["authors"]:
            for article in author["articles"]:
                total += 1
                result = process_article(article, did)
                if result is not None:
                    success += 1
                else:
                    # 检查是否是跳过（已存在）
                    output_file = BASE_DIR / "data" / "articles" / did / f"{article['id']}_meta.json"
                    if output_file.exists():
                        skipped += 1

    print(f"\n📊 统计: 总计{total}篇, 新生成{success}篇, 跳过{skipped}篇, 失败{total - success - skipped}篇")


if __name__ == "__main__":
    main()
