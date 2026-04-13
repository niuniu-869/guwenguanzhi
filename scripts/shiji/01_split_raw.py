#!/usr/bin/env python3
"""
史记原文拆卷脚本
- 输入：data/books/shiji/raw_source/shiji_raw.txt（殆知阁 daizhigev20 版本）
- 输出：
  - data/books/shiji/raw/shiji_XXX.txt （130 卷原文，简体）
  - data/books/shiji/catalog.json （卷目录 + 类别 + 元数据）
特点：
  - 原文已是简体，无需繁简转换（若发现繁体字再转）
  - 按 "卷X XXX第X" 行切分
  - 五大类别：本纪(1-12) 表(13-22) 书(23-30) 世家(31-60) 列传(61-130)
"""

import json
import re
from pathlib import Path
from opencc import OpenCC

BASE_DIR = Path(__file__).parent.parent.parent
SRC = BASE_DIR / "data/books/shiji/raw_source/shiji_raw.txt"
RAW_DIR = BASE_DIR / "data/books/shiji/raw"
CATALOG = BASE_DIR / "data/books/shiji/catalog.json"

# 中文数字 → 阿拉伯
CN_DIGIT = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "百": 100}


def cn_to_int(s: str) -> int:
    """中文数字（最多 "一百三十"）→ 阿拉伯数字"""
    s = s.strip()
    if not s:
        return 0
    # 特殊：一百三十、一百二十八
    if "百" in s:
        parts = s.split("百")
        hundreds = CN_DIGIT.get(parts[0], 1) if parts[0] else 1
        rest = parts[1]
        n = hundreds * 100
        if not rest:
            return n
        # rest: "三十"、"二十八"、"五"
        if "十" in rest:
            tens_part = rest.split("十")
            tens = CN_DIGIT.get(tens_part[0], 1) if tens_part[0] else 1
            ones = CN_DIGIT.get(tens_part[1], 0) if len(tens_part) > 1 and tens_part[1] else 0
            return n + tens * 10 + ones
        return n + CN_DIGIT.get(rest, 0)
    if "十" in s:
        parts = s.split("十")
        tens = CN_DIGIT.get(parts[0], 1) if parts[0] else 1
        ones = CN_DIGIT.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
        return tens * 10 + ones
    return CN_DIGIT.get(s, 0)


def classify(juan: int) -> tuple[str, str]:
    """卷号 → (类别 id, 类别名)"""
    if 1 <= juan <= 12:
        return "benji", "本纪"
    if 13 <= juan <= 22:
        return "biao", "表"
    if 23 <= juan <= 30:
        return "shu", "书"
    if 31 <= juan <= 60:
        return "shijia", "世家"
    if 61 <= juan <= 130:
        return "liezhuan", "列传"
    return "unknown", "未知"


HEAD_RE = re.compile(r"^卷([一二三四五六七八九十百]+)\s+(.+?)第([一二三四五六七八九十百]+)$")


def split_juan(raw: str) -> list[dict]:
    """把原文切成 130 卷"""
    lines = raw.splitlines()
    juan_list = []
    current = None
    for line in lines:
        m = HEAD_RE.match(line.strip())
        if m:
            juan_num = cn_to_int(m.group(1))
            title = m.group(2).strip()
            order_in_cat = cn_to_int(m.group(3))
            # 跳过目录部分：正文中第二次出现卷一才是真正开始
            if current is None and juan_num != 1:
                # 目录行，尚未进入正文
                continue
            if current is None:
                # 首次遇到卷一（可能是目录也可能是正文，用"是否紧跟正文"判断）
                current = {
                    "juan": juan_num,
                    "title": title,
                    "order_in_category": order_in_cat,
                    "paragraphs": [],
                }
                continue
            # 新一卷开始，保存旧的
            # 若旧卷没有段落，说明之前那个是目录行，替换为当前
            if not current["paragraphs"]:
                current = {
                    "juan": juan_num,
                    "title": title,
                    "order_in_category": order_in_cat,
                    "paragraphs": [],
                }
                continue
            juan_list.append(current)
            current = {
                "juan": juan_num,
                "title": title,
                "order_in_category": order_in_cat,
                "paragraphs": [],
            }
            continue
        if current is None:
            continue
        text = line.strip()
        if text:
            current["paragraphs"].append(text)
    if current and current["paragraphs"]:
        juan_list.append(current)
    return juan_list


def has_traditional(text: str) -> bool:
    """检测是否含常见繁体字"""
    sample = text[:3000]
    return any(c in sample for c in "國學東長門內亂來萬軍書寫愛讀")


def main():
    raw = SRC.read_text("utf-8")
    print(f"原文长度：{len(raw)} 字")

    # 检测繁简
    if has_traditional(raw):
        print("检测到繁体，转换为简体...")
        cc = OpenCC("t2s")
        raw = cc.convert(raw)
    else:
        print("原文已是简体")

    juan_list = split_juan(raw)
    print(f"切出 {len(juan_list)} 卷")

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    catalog_entries = []
    total_chars = 0
    total_paras = 0
    for j in juan_list:
        num = j["juan"]
        cat_id, cat_name = classify(num)
        jid = f"shiji_{num:03d}"
        out_file = RAW_DIR / f"{jid}.txt"
        content = "\n".join(j["paragraphs"])
        out_file.write_text(content, "utf-8")

        char_count = len(content)
        para_count = len(j["paragraphs"])
        total_chars += char_count
        total_paras += para_count

        catalog_entries.append({
            "id": jid,
            "juan": num,
            "title": j["title"],
            "category": cat_id,
            "category_name": cat_name,
            "order_in_category": j["order_in_category"],
            "raw_file": f"data/books/shiji/raw/{jid}.txt",
            "char_count": char_count,
            "paragraphs_count": para_count,
        })

    catalog = {
        "book": {
            "id": "shiji",
            "name": "史记",
            "author": "司马迁",
            "dynasty": "西汉",
            "period": "约公元前 109 - 前 91 年",
            "source": "殆知阁古代文献藏书（garychowcmu/daizhigev20）",
            "total_juan": len(catalog_entries),
            "total_chars": total_chars,
            "total_paragraphs": total_paras,
            "license": "原文公有领域",
        },
        "categories": [
            {"id": "benji", "name": "本纪", "range": [1, 12], "description": "帝王传记"},
            {"id": "biao", "name": "表", "range": [13, 22], "description": "大事年表"},
            {"id": "shu", "name": "书", "range": [23, 30], "description": "典章制度"},
            {"id": "shijia", "name": "世家", "range": [31, 60], "description": "诸侯传记"},
            {"id": "liezhuan", "name": "列传", "range": [61, 130], "description": "人物传记"},
        ],
        "juan": catalog_entries,
    }
    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), "utf-8")

    print(f"\n✅ 完成")
    print(f"  总卷数：{len(catalog_entries)}")
    print(f"  总字数：{total_chars:,}")
    print(f"  总段数：{total_paras:,}")
    print(f"  平均每卷：{total_chars // len(catalog_entries):,} 字 / {total_paras // len(catalog_entries)} 段")
    print(f"  输出目录：{RAW_DIR}")
    print(f"  目录：{CATALOG}")

    # 按类别统计
    by_cat = {}
    for e in catalog_entries:
        by_cat.setdefault(e["category_name"], {"count": 0, "chars": 0})
        by_cat[e["category_name"]]["count"] += 1
        by_cat[e["category_name"]]["chars"] += e["char_count"]
    print("\n按类别分布：")
    for name, v in by_cat.items():
        print(f"  {name}: {v['count']}卷 / {v['chars']:,}字 / 平均{v['chars']//v['count']:,}字")


if __name__ == "__main__":
    main()
