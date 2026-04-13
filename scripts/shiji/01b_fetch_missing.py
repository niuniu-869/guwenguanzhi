#!/usr/bin/env python3
"""
从维基文库（zh.wikisource.org）补齐殆知阁版史记中缺失的 26 卷。
使用 MediaWiki parse API 拿 wikitext，清洗后繁转简。
"""

import json
import os
import re
import time
from pathlib import Path
import requests
from opencc import OpenCC

FORCE = os.environ.get("FORCE", "") == "1"

BASE_DIR = Path(__file__).parent.parent.parent
RAW_DIR = BASE_DIR / "data/books/shiji/raw"
CATALOG = BASE_DIR / "data/books/shiji/catalog.json"

API = "https://zh.wikisource.org/w/api.php"

# 缺失 26 卷：(juan_num, title)
MISSING = [
    (12, "孝武本纪"),
    (15, "六国年表"), (16, "秦楚之际月表"), (17, "汉兴以来诸侯王年表"),
    (18, "高祖功臣侯者年表"), (19, "惠景间侯者年表"), (20, "建元以来侯者年表"),
    (21, "建元已来王子侯者年表"), (22, "汉兴以来将相名臣年表"),
    (23, "礼书"),
    (34, "燕召公世家"), (38, "宋微子世家"),
    (43, "赵世家"), (44, "魏世家"),
    (48, "陈涉世家"), (57, "绛侯周勃世家"),
    (62, "管晏列传"), (72, "穰侯列传"),
    (79, "范睢蔡泽列传"), (80, "乐毅列传"),
    (86, "刺客列传"), (89, "张耳陈馀列传"),
    (95, "樊郦滕灌列传"), (100, "季布栾布列传"),
    (107, "魏其武安侯列传"),
    (130, "太史公自序"),
]


UA = "guwenguanzhi-ai/0.1 (https://github.com/niuniu-869/guwenguanzhi; classical Chinese reading site; educational use)"


def fetch_wikitext(juan_num: int, page_override: str | None = None, depth: int = 0) -> str:
    """向 wikisource API 请求卷 wikitext；自动跟随 #REDIRECT"""
    if depth > 3:
        raise RuntimeError("重定向过深")
    page = page_override or f"史記/卷{juan_num:03d}"
    r = requests.get(API, params={
        "action": "parse", "page": page, "prop": "wikitext",
        "format": "json", "redirects": "1",
    }, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"API 错误 {page}: {data['error']}")
    wt = data["parse"]["wikitext"]["*"]
    # 手动跟随 #REDIRECT（redirects=1 应该自动跟随，但这里保险）
    m = re.match(r"#\s*REDIRECT\s*\[\[([^\[\]]+)\]\]", wt.strip(), re.IGNORECASE)
    if m:
        return fetch_wikitext(juan_num, page_override=m.group(1), depth=depth + 1)
    return wt


VARIANT_PRIORITY = ("zh-cn:", "zh-hans:", "simplified:", "zh-sg:", "zh-my:")


def _expand_font_convert(inner: str) -> str:
    """展开 -{xxx}- 字体转换标记
    - -{纯文字}- → 纯文字
    - -{A|zh-hans:X; zh-hant:Y}- → X
    - -{zh-hans:X; zh-hant:Y;}- （无 | 前缀，直接多变体）→ X
    - -{X; Y}- 其他 → X
    """
    body = inner.strip()
    # 去掉 "A|" / "H|" / "T|" / "R|" 前缀
    m = re.match(r"^[AHTR]\|(.*)$", body, re.DOTALL)
    if m:
        body = m.group(1)

    # 判断是否多变体：含有 "zh-xxx:" 或 "simplified:" 模式
    is_variant = any(p in body for p in VARIANT_PRIORITY) or "zh-hant:" in body or "traditional:" in body
    if not is_variant:
        return body

    # 多变体：按优先级取
    parts = [p.strip() for p in body.split(";") if p.strip()]
    for prio in VARIANT_PRIORITY:
        for p in parts:
            if p.startswith(prio):
                return p[len(prio):].strip()
    # fallback：取第一个 part 的冒号后
    if parts:
        first = parts[0]
        if ":" in first:
            return first.split(":", 1)[1].strip()
        return first
    return body


def _strip_balanced(text: str, open_tok: str, close_tok: str) -> str:
    """栈式删除 open...close 包括嵌套。open/close 为字符串字面量，不是 regex。"""
    out = []
    i = 0
    depth = 0
    ol, cl = len(open_tok), len(close_tok)
    while i < len(text):
        if text[i:i + ol] == open_tok:
            depth += 1
            i += ol
            continue
        if depth > 0 and text[i:i + cl] == close_tok:
            depth -= 1
            i += cl
            continue
        if depth == 0:
            out.append(text[i])
        i += 1
    return "".join(out)


def clean_wikitext(wt: str) -> str:
    """清洗 wikitext → 纯原文段落"""
    # 1. 截断：注疏部分（索隐述赞、附录、校勘）
    for marker in [
        "==索隱述贊==", "==索隱述讚==", "==索引述贊==",
        "===索隱述贊===", "==附錄==", "==校勘==", "==參考文獻==",
        "==参考文献==", "==注釋==",
    ]:
        idx = wt.find(marker)
        if idx != -1:
            wt = wt[:idx]
            break

    # 2. 先展开字体转换 -{xxx}-（不含嵌套 {}）—— 要在去模板之前，避免干扰模板识别
    #    使用非贪婪且不跨越 -{ 和 }- 边界的匹配，需多轮处理嵌套
    for _ in range(5):
        new = re.sub(r"-\{([^{}]*?)\}-", lambda m: _expand_font_convert(m.group(1)), wt)
        if new == wt:
            break
        wt = new

    # 3. 去魔术字 __TOC__ __NOTOC__ 等
    wt = re.sub(r"__[A-Z]+__", "", wt)

    # 4. 去 HTML 注释
    wt = re.sub(r"<!--.*?-->", "", wt, flags=re.DOTALL)

    # 5. 去 <ref>/<references>/<nowiki> 等标签及内容
    wt = re.sub(r"<ref[^>]*?/>", "", wt)
    wt = re.sub(r"<ref[^>]*?>.*?</ref>", "", wt, flags=re.DOTALL)
    wt = re.sub(r"<(references|nowiki|noinclude|includeonly)[^>]*?>.*?</\1>", "", wt, flags=re.DOTALL)
    wt = re.sub(r"<[^>]+>", "", wt)

    # 6. 栈式删除所有 {{...}}（支持任意嵌套）
    wt = _strip_balanced(wt, "{{", "}}")

    # 7. 处理 wiki 链接 [[...]]
    #    [[w:Foo|bar]] / [[Foo|bar]] → bar
    #    [[Foo]] → Foo，但 [[Category:xxx]] / [[File:xxx]] / [[Image:xxx]] 整体删
    def link_replace(m):
        inner = m.group(1)
        # 分类/文件链接：整体删
        if re.match(r"^(Category|File|Image|文件|分类):", inner, re.IGNORECASE):
            return ""
        if "|" in inner:
            return inner.split("|")[-1]
        # 去命名空间前缀
        if ":" in inner and inner.split(":", 1)[0].lower() in ("w", "wikipedia", "wikt"):
            return inner.split(":", 1)[1]
        return inner
    # 先处理非嵌套的
    for _ in range(3):
        new = re.sub(r"\[\[([^\[\]]+?)\]\]", link_replace, wt)
        if new == wt:
            break
        wt = new

    # 8. 外链 [url text] → text ； [url] → 删除
    wt = re.sub(r"\[https?://[^\s\]]+\s+([^\]]+?)\]", r"\1", wt)
    wt = re.sub(r"\[https?://[^\s\]]+\]", "", wt)

    # 9. 去章节标题行 ==xxx== / ===xxx=== / =xxx=
    wt = re.sub(r"^=+\s*.*?\s*=+\s*$", "", wt, flags=re.MULTILINE)

    # 10. 去 wiki 表格语法：以 | ! {| |} |- 开头的行全删
    def _is_table_line(ln: str) -> bool:
        s = ln.lstrip()
        if not s:
            return False
        return s.startswith(("|", "!", "{|"))
    lines = [ln for ln in wt.splitlines() if not _is_table_line(ln)]
    wt = "\n".join(lines)

    # 11. 残余清理：合并空行
    lines = [ln.strip() for ln in wt.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def validate(text: str, juan_num: int, title: str) -> str:
    """基本校验：长度、非空、不含残留模板标记
    表类（卷 13-22）允许极短，因为 wikisource 上可能只有表格无序文"""
    is_biao = 13 <= juan_num <= 22
    min_len = 20 if is_biao else 200
    if len(text) < min_len:
        if is_biao:
            # 表类：给占位内容，避免下游翻译管线出错
            return text or f"《{title}》为史记年表/月表之一，原以表格形式呈现制度沿革与人物年表。由于表格结构不适合逐字翻译，本站仅保留目录条目，完整原文请参考中华书局点校本。"
        raise ValueError(f"卷{juan_num} {title} 原文过短：{len(text)} 字")
    if "{{" in text or "}}" in text:
        raise ValueError(f"卷{juan_num} {title} 残留模板标记")
    if "[[" in text or "]]" in text:
        raise ValueError(f"卷{juan_num} {title} 残留链接")
    return text


def main():
    cc = OpenCC("t2s")
    catalog = json.loads(CATALOG.read_text("utf-8"))
    existing = {e["juan"] for e in catalog["juan"]}

    added = []
    failed = []
    # 重清洗模式：移除 catalog 里所有 MISSING 的条目，重新拉
    if FORCE:
        missing_ids = {f"shiji_{j:03d}" for j, _ in MISSING}
        catalog["juan"] = [e for e in catalog["juan"] if e["id"] not in missing_ids]
        existing = {e["juan"] for e in catalog["juan"]}
        print(f"[FORCE] 清除 {len(missing_ids)} 卷，重新拉取")

    for juan_num, title in MISSING:
        if juan_num in existing:
            print(f"⏭ 卷 {juan_num} 已存在，跳过")
            continue

        try:
            print(f"🌐 拉取 卷{juan_num} {title}...", end=" ", flush=True)
            wt = fetch_wikitext(juan_num)
            cleaned = clean_wikitext(wt)
            simplified = cc.convert(cleaned)
            text = validate(simplified, juan_num, title)

            # 写文件
            jid = f"shiji_{juan_num:03d}"
            out = RAW_DIR / f"{jid}.txt"
            out.write_text(text, "utf-8")

            paras = [p for p in text.split("\n") if p.strip()]
            print(f"✅ {len(text):,}字 / {len(paras)}段")

            # 分类
            if 1 <= juan_num <= 12:
                cat_id, cat_name = "benji", "本纪"
            elif 13 <= juan_num <= 22:
                cat_id, cat_name = "biao", "表"
            elif 23 <= juan_num <= 30:
                cat_id, cat_name = "shu", "书"
            elif 31 <= juan_num <= 60:
                cat_id, cat_name = "shijia", "世家"
            else:
                cat_id, cat_name = "liezhuan", "列传"

            # order_in_category 查表
            cat_ranges = {
                "benji": 1, "biao": 13, "shu": 23, "shijia": 31, "liezhuan": 61,
            }
            order = juan_num - cat_ranges[cat_id] + 1

            added.append({
                "id": jid,
                "juan": juan_num,
                "title": title,
                "category": cat_id,
                "category_name": cat_name,
                "order_in_category": order,
                "raw_file": f"data/books/shiji/raw/{jid}.txt",
                "char_count": len(text),
                "paragraphs_count": len(paras),
                "source_note": "from wikisource (daizhigev20 missing)",
            })

            time.sleep(0.5)  # 对 wikisource 友好
        except Exception as e:
            print(f"❌ {e}")
            failed.append((juan_num, title, str(e)))

    # 合并进 catalog 并按 juan 排序
    catalog["juan"].extend(added)
    catalog["juan"].sort(key=lambda x: x["juan"])

    # 更新 book 元数据
    total_chars = sum(e["char_count"] for e in catalog["juan"])
    total_paras = sum(e["paragraphs_count"] for e in catalog["juan"])
    catalog["book"]["total_juan"] = len(catalog["juan"])
    catalog["book"]["total_chars"] = total_chars
    catalog["book"]["total_paragraphs"] = total_paras

    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), "utf-8")

    print(f"\n📊 新增 {len(added)} 卷，失败 {len(failed)} 卷")
    if failed:
        print("失败：")
        for j, t, e in failed:
            print(f"  卷{j} {t}: {e}")
    print(f"📁 catalog 现 {len(catalog['juan'])}/130 卷，{total_chars:,} 字")


if __name__ == "__main__":
    main()
