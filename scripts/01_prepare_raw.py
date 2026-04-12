#!/usr/bin/env python3
"""
古文观止语料清洗脚本 v2
策略：
1. 用目录区（前260行）作为权威的 标题→作者 映射
2. 用正文区（261行+）提取文章内容
3. 通过模糊匹配将两者关联
4. 繁转简，按朝代分类，输出 catalog.json
"""

import json
import re
import os
from pathlib import Path
from opencc import OpenCC

BASE_DIR = Path(__file__).parent.parent
RAW_FILE = BASE_DIR / "data" / "raw" / "guwenguanzhi_raw.txt"
OUTPUT_DIR = BASE_DIR / "data" / "raw"
ARTICLES_DIR = BASE_DIR / "data" / "articles"
CATALOG_FILE = BASE_DIR / "data" / "catalog.json"

cc = OpenCC('t2s')

# ============================================================
# 朝代定义
# ============================================================

DYNASTIES = [
    {"id": "pre_qin", "name": "先秦", "period": "远古—公元前221年"},
    {"id": "han", "name": "两汉", "period": "公元前206年—公元220年"},
    {"id": "wei_jin", "name": "魏晋南北朝", "period": "公元220年—589年"},
    {"id": "tang", "name": "唐", "period": "公元618年—907年"},
    {"id": "song", "name": "宋", "period": "公元960年—1279年"},
    {"id": "ming", "name": "明", "period": "公元1368年—1644年"},
]

# 书籍来源 → 作者
SOURCE_AUTHOR = {
    "左传": "左丘明",
    "国语": "左丘明",
    "公羊传": "公羊高",
    "谷梁传": "谷梁赤",
    "礼记": "戴圣",
    "礼记檀弓": "戴圣",
    "战国策": "刘向",
    "史记": "司马迁",
}

# 作者 → 朝代
AUTHOR_DYNASTY = {
    # 先秦
    "左丘明": "pre_qin", "公羊高": "pre_qin", "谷梁赤": "pre_qin",
    "戴圣": "pre_qin", "刘向": "pre_qin",
    "屈原": "pre_qin", "宋玉": "pre_qin", "李斯": "pre_qin",
    # 两汉
    "司马迁": "han", "贾谊": "han", "晁错": "han", "邹阳": "han",
    "司马相如": "han", "李陵": "han", "路温舒": "han", "杨恽": "han",
    "汉高祖": "han", "汉文帝": "han", "汉景帝": "han", "汉武帝": "han",
    "汉光武帝": "han", "马援": "han",
    # 魏晋南北朝
    "诸葛亮": "wei_jin", "李密": "wei_jin", "王羲之": "wei_jin",
    "陶渊明": "wei_jin", "孔稚珪": "wei_jin",
    # 唐
    "魏征": "tang", "骆宾王": "tang", "王勃": "tang", "李白": "tang",
    "李华": "tang", "刘禹锡": "tang", "杜牧": "tang",
    "韩愈": "tang", "柳宗元": "tang",
    # 宋
    "王禹偁": "song", "李格非": "song", "范仲淹": "song",
    "司马光": "song", "钱公辅": "song", "李觏": "song",
    "欧阳修": "song", "苏洵": "song", "苏轼": "song", "苏辙": "song",
    "曾巩": "song", "王安石": "song", "张益": "song",
    # 明
    "宋濂": "ming", "刘基": "ming", "方孝孺": "ming", "王鏊": "ming",
    "王守仁": "ming", "唐顺之": "ming", "宗臣": "ming",
    "归有光": "ming", "茅坤": "ming", "王世贞": "ming",
    "袁宏道": "ming", "张溥": "ming",
}

# ============================================================
# 第一步：解析目录区（权威的标题→作者映射）
# ============================================================

def parse_toc(lines: list[str]) -> list[dict]:
    """解析目录区，返回 [{title, author_or_source, volume}]"""
    toc = []
    current_vol = 0

    vol_map = {
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
        '十一': 11, '十二': 12
    }

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 卷标题
        vol_match = re.match(r'^卷(一|二|三|四|五|六|七|八|九|十[一二]?)$', line)
        if vol_match:
            current_vol = vol_map[vol_match.group(1)]
            continue

        # 跳过朝代类型行和首行
        if line in ['周文', '汉文', '战国', '六朝 唐文', '六朝唐文',
                     '唐文', '唐宋文', '宋文', '明文'] or '古文观止' in line:
            continue

        # 文章条目：标题 + 空格 + 作者/来源
        # 从右往左找最后一个空格分隔
        parts = line.rsplit(None, 1)
        if len(parts) == 2:
            title, author = parts[0].strip(), parts[1].strip()
            toc.append({
                'title': title,
                'author_or_source': author,
                'volume': current_vol,
            })
        elif len(parts) == 1 and current_vol > 0:
            # 可能是特殊行
            pass

    return toc


def resolve_author(toc_entry: dict) -> tuple[str, str, str]:
    """
    解析目录条目，返回 (real_author, source_text, dynasty_id)
    """
    title = toc_entry['title']
    raw = toc_entry['author_or_source']

    # 尝试按书籍来源解析
    for book, author in SOURCE_AUTHOR.items():
        if raw == book:
            return author, book, AUTHOR_DYNASTY.get(author, "pre_qin")

    # 直接是作者名
    if raw in AUTHOR_DYNASTY:
        return raw, "", AUTHOR_DYNASTY[raw]

    # 处理 "司马 相如" 之类的空格问题
    cleaned = raw.replace(" ", "")
    if cleaned in AUTHOR_DYNASTY:
        return cleaned, "", AUTHOR_DYNASTY[cleaned]

    # 如果作者名有部分匹配
    for known_author, dynasty in AUTHOR_DYNASTY.items():
        if known_author in cleaned or cleaned in known_author:
            return known_author, "", dynasty

    print(f"  ⚠ 无法解析作者: title={title}, raw={raw}")
    return raw, "", "pre_qin"


# ============================================================
# 第���步：解析正文区
# ============================================================

def parse_texts(lines: list[str]) -> list[dict]:
    """解析正文区，返回 [{raw_title, paragraphs}]"""
    articles = []
    current = None

    for line in lines:
        line = line.strip()

        # 跳过卷标题行
        if re.match(r'^卷.+\s+(周文|汉文|秦文|六朝|唐文|唐、宋文|宋文|明文)', line):
            continue

        # 文章标题行 - 匹配 【...】 开头
        title_match = re.match(r'^【(.+?)】', line)
        if title_match:
            if current and current['paragraphs']:
                articles.append(current)

            raw_title = title_match.group(1).strip()
            current = {
                'raw_title': raw_title,
                'paragraphs': [],
            }
            # 标题行可能后面还有正文（极少数情况）
            remainder = line[title_match.end():].strip()
            # 去掉出处部分
            remainder = re.sub(r'^[（(].*?[）)]', '', remainder).strip()
            if remainder:
                current['paragraphs'].append(remainder)
            continue

        # 正文段落
        if line and current is not None:
            current['paragraphs'].append(line)

    if current and current['paragraphs']:
        articles.append(current)

    return articles


# ============================================================
# 第三步：匹配目录与正文
# ============================================================

def match_toc_with_texts(toc: list[dict], texts: list[dict]) -> list[dict]:
    """将目录条目与正文匹配，返回完整的文章列表"""
    matched = []
    used_text_indices = set()

    for toc_entry in toc:
        toc_title = toc_entry['title']
        author, source, dynasty = resolve_author(toc_entry)

        # 在正文中查找匹配
        best_idx = None
        best_score = 0

        for i, text in enumerate(texts):
            if i in used_text_indices:
                continue

            raw_title = text['raw_title']
            score = 0

            # 完全匹配
            if raw_title == toc_title:
                score = 100
            # 正文标题包含目录标题
            elif toc_title in raw_title:
                score = 80
            # 目录标题包含正文标题
            elif raw_title in toc_title:
                score = 70
            # 去掉作者名后匹配
            elif raw_title.startswith(author) and raw_title[len(author):] == toc_title:
                score = 90
            elif raw_title.startswith(author) and toc_title in raw_title[len(author):]:
                score = 85
            # 编辑距离≤2的近似匹配（处理异体字/异名：辨/辩、宦官/宦者等）
            elif len(toc_title) == len(raw_title):
                diff = sum(1 for a, b in zip(toc_title, raw_title) if a != b)
                if diff <= 2 and len(toc_title) >= 2:
                    score = 76 - diff
            # 去掉作者名后编辑距离1
            elif raw_title.startswith(author) and len(raw_title) - len(author) == len(toc_title):
                cleaned = raw_title[len(author):]
                diff = sum(1 for a, b in zip(toc_title, cleaned) if a != b)
                if diff <= 1:
                    score = 74
            # 部分重叠
            else:
                common = len(set(toc_title) & set(raw_title))
                if common >= len(toc_title) * 0.6:
                    score = common

            if score > best_score:
                best_score = score
                best_idx = i

        if best_idx is not None and best_score >= 3:
            used_text_indices.add(best_idx)
            text = texts[best_idx]
            matched.append({
                'title': toc_title,
                'author': author,
                'source': source,
                'dynasty': dynasty,
                'volume': toc_entry['volume'],
                'paragraphs': text['paragraphs'],
                'raw_title': text['raw_title'],
            })
        else:
            print(f"  ❌ 未匹配到正文: [{toc_title}] (作者={author})")

    # 检查未匹配的正文
    for i, text in enumerate(texts):
        if i not in used_text_indices:
            print(f"  ❓ 正文未匹配目录: [{text['raw_title']}]")

    return matched


# ============================================================
# 第四步：保存
# ============================================================

def save_articles(articles: list[dict]):
    """保存文章文件并生成 catalog.json"""

    # 清理旧的原文文件
    for dynasty in DYNASTIES:
        d = OUTPUT_DIR / dynasty['id']
        if d.exists():
            for f in d.glob('*.txt'):
                f.unlink()

    dynasty_authors = {}  # dynasty_id -> {author -> [articles]}

    for seq, article in enumerate(articles, 1):
        did = article['dynasty']
        author = article['author']

        # 文件名
        article_id = f"{seq:03d}_{article['title']}"

        # 保存原文
        raw_dir = OUTPUT_DIR / did
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_file = raw_dir / f"{article_id}.txt"
        text = '\n'.join(article['paragraphs'])
        with open(raw_file, 'w', encoding='utf-8') as f:
            f.write(text)

        # articles 输出目录
        (ARTICLES_DIR / did).mkdir(parents=True, exist_ok=True)

        # 归类
        if did not in dynasty_authors:
            dynasty_authors[did] = {}
        if author not in dynasty_authors[did]:
            dynasty_authors[did][author] = []

        dynasty_authors[did][author].append({
            "id": article_id,
            "title": article['title'],
            "author": author,
            "source": article['source'],
            "volume": article['volume'],
            "dynasty": did,
            "raw_file": str(raw_file.relative_to(BASE_DIR)),
            "paragraphs_count": len(article['paragraphs']),
        })

    # 生成 catalog.json
    catalog = {"dynasties": []}
    for dynasty_def in DYNASTIES:
        did = dynasty_def["id"]
        if did not in dynasty_authors:
            continue

        authors_list = []
        for author_name, author_articles in dynasty_authors[did].items():
            authors_list.append({
                "id": f"{did}_{author_name}",
                "name": author_name,
                "dynasty": did,
                "bio": "",
                "articles": author_articles,
            })

        catalog["dynasties"].append({
            **dynasty_def,
            "authors": authors_list,
            "article_count": sum(len(a["articles"]) for a in authors_list),
        })

    with open(CATALOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    return catalog


# ============================================================
# 主函数
# ============================================================

def main():
    print("=" * 60)
    print("古文观止语料清洗 v2")
    print("=" * 60)

    with open(RAW_FILE, 'r', encoding='utf-8') as f:
        raw_content = f.read()

    # 繁转简
    content = cc.convert(raw_content)
    lines = content.split('\n')

    # 分割目录区和正文区
    # 正文从 "卷一 周文" 开始（含卷标题+朝代在同一行的格式）
    toc_end = 0
    for i, line in enumerate(lines):
        if re.match(r'^卷一\s+周文', line.strip()) and i > 50:
            toc_end = i
            break

    print(f"\n目录区: 1-{toc_end} 行")
    print(f"正文区: {toc_end + 1}-{len(lines)} 行")

    # 1. 解析目录
    toc = parse_toc(lines[:toc_end])
    print(f"\n📖 目录解析: {len(toc)} 篇")

    # 按卷统计
    vol_count = {}
    for t in toc:
        v = t['volume']
        vol_count[v] = vol_count.get(v, 0) + 1
    for v in sorted(vol_count):
        print(f"   卷{v}: {vol_count[v]}篇")

    # 2. 解析正文
    texts = parse_texts(lines[toc_end:])
    print(f"\n📝 正文解析: {len(texts)} 篇")

    # 3. 匹配
    print(f"\n🔗 匹配目录与正文:")
    articles = match_toc_with_texts(toc, texts)
    print(f"   成功匹配: {len(articles)} 篇")

    # 4. 保存
    print(f"\n📁 保存文件:")
    catalog = save_articles(articles)

    # 统计
    print("\n📊 按朝代统计:")
    total = 0
    for d in catalog['dynasties']:
        count = d['article_count']
        total += count
        authors = len(d['authors'])
        print(f"   {d['name']}: {count}篇, {authors}位作者")
    print(f"   总计: {total}篇")

    print(f"\n✅ catalog.json: {CATALOG_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
