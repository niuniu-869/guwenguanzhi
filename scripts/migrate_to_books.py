#!/usr/bin/env python3
"""
Phase 1 数据层迁移
将现有两份数据统一到 data/books/<bookId>/ 下

输出结构：
  data/books/guwenguanzhi/
    book.json            # 书身份证
    catalog.json         # 统一树形目录
    documents/
      pre_qin/001_xxx.json  # 保留朝代子目录作为物理分组

  data/books/shiji/
    book.json            # 升级已存在的 catalog
    catalog.json
    documents/
      001.json           # 去掉 shiji_ 前缀
      ...

旧路径保留不动（防止回滚），等前端切换完再清理。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SRC_ARTICLES = ROOT / "data" / "articles"
SRC_CATALOG = ROOT / "data" / "catalog.json"
SRC_SHIJI = ROOT / "data" / "books" / "shiji"
OUT_BOOKS = ROOT / "data" / "books"

DYNASTY_META = {
    "pre_qin": {"name": "先秦", "period": "远古—前 221 年", "color": "#8B6914"},
    "han": {"name": "两汉", "period": "前 202—220 年", "color": "#C84032"},
    "wei_jin": {"name": "魏晋南北朝", "period": "220—589 年", "color": "#4A7C59"},
    "tang": {"name": "唐", "period": "618—907 年", "color": "#2A5CAA"},
    "song": {"name": "宋", "period": "960—1279 年", "color": "#7B4B94"},
    "ming": {"name": "明", "period": "1368—1644 年", "color": "#B8860B"},
}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- 古文观止 ----------

def migrate_guwenguanzhi() -> None:
    print("=== 迁移古文观止 ===")
    dst = OUT_BOOKS / "guwenguanzhi"
    dst_docs = dst / "documents"
    src_catalog = json.loads(SRC_CATALOG.read_text(encoding="utf-8"))

    # 1. book.json
    total_docs = sum(len(a["articles"]) for d in src_catalog["dynasties"] for a in d["authors"])
    total_authors = sum(len(d["authors"]) for d in src_catalog["dynasties"])
    book = {
        "id": "guwenguanzhi",
        "name": "古文观止",
        "displayName": "古文觀止",
        "author": None,
        "editor": "吴楚材 吴调侯",
        "dynasty": "qing",
        "period": "清 · 康熙三十四年（1695）成书",
        "summary": "中国清代吴楚材、吴调侯叔侄编选的古代散文选本，收录自东周至明末的 222 篇经典古文，是近三百年来流传最广的古文入门读物。",
        "structureType": "collection",
        "hierarchy": ["dynasty", "author", "document"],
        "totalDocuments": total_docs,
        "totalAuthors": total_authors,
        "source": "维基文库 / 中国哲学书电子化计划",
        "license": "原文公有领域",
        "cover": {"theme": "ink", "pattern": "classic"},
        "order": 1,
    }
    write_json(dst / "book.json", book)

    # 2. catalog.json（朝代 → 作者 → 文档）
    groups = []
    for dyn in src_catalog["dynasties"]:
        dyn_meta = DYNASTY_META.get(dyn["id"], {"name": dyn["name"]})
        author_groups = []
        for author in dyn["authors"]:
            docs = []
            for art in author["articles"]:
                docs.append({
                    "id": art["id"],
                    "title": art["title"],
                    "paragraphCount": art.get("paragraphs_count", 0),
                    "author": author["name"],
                    "source": art.get("source", ""),
                    "volume": art.get("volume", 0),
                })
            author_groups.append({
                "id": author["id"],
                "name": author["name"],
                "description": author.get("bio", ""),
                "documents": docs,
            })
        groups.append({
            "id": dyn["id"],
            "name": dyn["name"],
            "description": dyn.get("period", ""),
            "meta": {"period": dyn_meta.get("period"), "color": dyn_meta.get("color")},
            "subgroups": author_groups,
        })
    catalog = {
        "bookId": "guwenguanzhi",
        "hierarchy": ["dynasty", "author", "document"],
        "groups": groups,
    }
    write_json(dst / "catalog.json", catalog)

    # 3. 复制文档 JSON（只拷合并后的完整文件，不拷 meta/trans/words 中间文件）
    copied = 0
    for dyn_dir in SRC_ARTICLES.iterdir():
        if not dyn_dir.is_dir():
            continue
        for src_file in dyn_dir.glob("*.json"):
            name = src_file.stem
            # 排除中间产物
            if name.endswith("_meta") or name.endswith("_trans") or name.endswith("_words"):
                continue
            dst_file = dst_docs / dyn_dir.name / src_file.name
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            copied += 1
    print(f"  ✅ 复制 {copied} 份文档 → {dst_docs}")
    print(f"  ✅ book.json / catalog.json 写入 {dst}")


# ---------- 史记 ----------

def migrate_shiji() -> None:
    print("=== 迁移史记 ===")
    dst = OUT_BOOKS / "shiji"
    dst_docs = dst / "documents"
    old_catalog = json.loads((SRC_SHIJI / "catalog.json").read_text(encoding="utf-8"))

    # 1. book.json
    b = old_catalog["book"]
    book = {
        "id": "shiji",
        "name": "史记",
        "displayName": "史記",
        "author": b.get("author", "司马迁"),
        "editor": None,
        "dynasty": "han",
        "period": b.get("period", "西汉 · 约前 109 - 前 91 年"),
        "summary": "二十四史之首，西汉司马迁撰，纪传体通史，记载自上古黄帝至汉武帝太初年间约三千年历史，共 130 卷。",
        "structureType": "jizhuan",
        "hierarchy": ["category", "document"],
        "totalDocuments": b.get("total_juan", 130),
        "totalChars": b.get("total_chars", 0),
        "totalParagraphs": b.get("total_paragraphs", 0),
        "source": b.get("source", ""),
        "license": b.get("license", "原文公有领域"),
        "cover": {"theme": "crimson", "pattern": "bamboo"},
        "order": 2,
    }
    write_json(dst / "book.json", book)

    # 2. catalog.json（五类 → 卷）
    juan_by_id = {j["id"]: j for j in old_catalog["juan"]}
    groups = []
    for cat in old_catalog["categories"]:
        docs = []
        lo, hi = cat["range"]
        for j in range(lo, hi + 1):
            old_id = f"shiji_{j:03d}"
            meta = juan_by_id.get(old_id)
            if not meta:
                continue
            docs.append({
                "id": f"{j:03d}",                       # 新短 ID
                "title": meta["title"],
                "paragraphCount": meta.get("paragraphs_count", 0),
                "juan": j,
                "charCount": meta.get("char_count", 0),
                "legacyId": old_id,                     # 保留用于可能的旧链接
            })
        groups.append({
            "id": cat["id"],
            "name": cat["name"],
            "description": cat.get("description", ""),
            "meta": {"range": cat["range"]},
            "documents": docs,
        })
    catalog = {
        "bookId": "shiji",
        "hierarchy": ["category", "document"],
        "groups": groups,
    }
    write_json(dst / "catalog.json", catalog)

    # 3. 复制 & 重命名文档 JSON（只要合并后的 shiji_XXX.json，不要 meta/trans/words）
    src_out = SRC_SHIJI / "output"
    copied = 0
    for src_file in sorted(src_out.glob("shiji_[0-9][0-9][0-9].json")):
        # 跳过 _meta/_trans/_words 中间产物（它们匹配不到上面模式）
        name = src_file.stem  # shiji_001
        juan = int(name.split("_")[1])
        new_id = f"{juan:03d}"
        dst_file = dst_docs / f"{new_id}.json"

        # 读取后改写 id 字段保持一致（新 id 更短）
        data = json.loads(src_file.read_text(encoding="utf-8"))
        data["id"] = new_id
        data["bookId"] = "shiji"
        data["legacyId"] = name
        # 字段规范化
        if "summary" in data and "background" not in data:
            # 史记用 summary，无需额外改
            pass
        write_json(dst_file, data)
        copied += 1
    print(f"  ✅ 复制 {copied} 份卷文档 → {dst_docs}")
    print(f"  ✅ book.json / catalog.json 写入 {dst}")


# ---------- 顶层 books 索引 ----------

def build_books_index() -> None:
    print("=== 生成 books 顶层索引 ===")
    books = []
    for book_dir in sorted(OUT_BOOKS.iterdir()):
        if not book_dir.is_dir():
            continue
        book_json = book_dir / "book.json"
        if not book_json.exists():
            continue
        b = json.loads(book_json.read_text(encoding="utf-8"))
        books.append({
            "id": b["id"],
            "name": b["name"],
            "displayName": b.get("displayName", b["name"]),
            "author": b.get("author"),
            "editor": b.get("editor"),
            "dynasty": b["dynasty"],
            "period": b["period"],
            "summary": b["summary"],
            "totalDocuments": b["totalDocuments"],
            "structureType": b["structureType"],
            "cover": b.get("cover"),
            "order": b.get("order", 99),
        })
    books.sort(key=lambda x: x["order"])
    write_json(OUT_BOOKS / "index.json", {"books": books})
    print(f"  ✅ 顶层索引：{[b['id'] for b in books]}")


if __name__ == "__main__":
    migrate_guwenguanzhi()
    migrate_shiji()
    build_books_index()
    print("\n✅ Phase 1 迁移完成")
