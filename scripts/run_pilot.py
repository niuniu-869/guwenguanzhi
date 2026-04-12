#!/usr/bin/env python3
"""
试跑脚本：对指定的几篇文章运行完整管线 (2a → 2b → 2c → 2d)
用于验证 Prompt 质量和数据结构
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

BASE_DIR = Path(__file__).parent.parent
CATALOG_FILE = BASE_DIR / "data" / "catalog.json"

# 5 篇代表性名篇
PILOT_TITLES = [
    "郑伯克段于鄢",   # 先秦·左传 - 叙事经典
    "师说",           # 唐·韩愈 - 议论文
    "岳阳楼记",       # 宋·范仲淹 - 写景抒情
    "前赤壁赋",       # 宋·苏轼 - 赋
    "陈情表",         # 魏晋·李密 - 骈文抒情
]


def find_articles(catalog: dict, titles: list[str]) -> list[tuple[dict, str]]:
    """从 catalog 中找到指定标题的文章"""
    found = []
    for dynasty in catalog["dynasties"]:
        for author in dynasty["authors"]:
            for article in author["articles"]:
                if article["title"] in titles:
                    found.append((article, dynasty["id"]))
    return found


def main():
    print("=" * 60)
    print("🧪 试跑管线 (5 篇名篇)")
    print("=" * 60)

    with open(CATALOG_FILE, 'r', encoding='utf-8') as f:
        catalog = json.load(f)

    articles = find_articles(catalog, PILOT_TITLES)
    print(f"找到 {len(articles)} 篇文章:")
    for article, did in articles:
        print(f"  - {article['title']} ({article['author']}, {did})")

    # 导入各步骤的处理函数
    from scripts_02a import process_article as process_meta
    from scripts_02b import process_article as process_trans
    from scripts_02c import process_article as process_words
    from scripts_02d import merge_article

    for article, did in articles:
        print(f"\n{'=' * 40}")
        print(f"📝 {article['title']}")
        print(f"{'=' * 40}")

        print("\n--- Step 2a: 元数据 ---")
        process_meta(article, did)

        print("\n--- Step 2b: 逐段翻译 ---")
        process_trans(article, did)

        print("\n--- Step 2c: 逐词注释 ---")
        process_words(article, did)

        print("\n--- Step 2d: 合并 ---")
        merge_article(article, did)

    print("\n" + "=" * 60)
    print("✅ 试跑完成！检查输出文件:")
    for article, did in articles:
        output = BASE_DIR / "data" / "articles" / did / f"{article['id']}.json"
        if output.exists():
            size = output.stat().st_size
            print(f"  ✓ {article['title']}: {size:,} bytes")
        else:
            print(f"  ✗ {article['title']}: 未生成")


# 为了让 import 正常工作，创建模块别名
def _setup_imports():
    """让各步骤脚本可以被 import"""
    import importlib.util

    for name, filename in [
        ("scripts_02a", "02a_generate_metadata.py"),
        ("scripts_02b", "02b_generate_translations.py"),
        ("scripts_02c", "02c_generate_words.py"),
        ("scripts_02d", "02d_merge.py"),
    ]:
        spec = importlib.util.spec_from_file_location(
            name, Path(__file__).parent / filename
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)


if __name__ == "__main__":
    _setup_imports()
    main()
