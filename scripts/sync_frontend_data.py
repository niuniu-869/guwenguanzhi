#!/usr/bin/env python3
"""
在 frontend dev / build 之前同步 data/books 到 frontend/public/data

做法：软链接 frontend/public/data -> ../../data/books（顶层整挂），但只暴露：
  data/books/index.json
  data/books/<bookId>/book.json
  data/books/<bookId>/catalog.json
  data/books/<bookId>/documents/**.json
其它目录（raw / raw_source / output 等中间产物）不暴露。

实现：在 public/data/ 下为每本书创建分项 symlink，避免整挂把内部中间产物泄露。
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_BOOKS = ROOT / "data" / "books"
DST_PUBLIC = ROOT / "frontend" / "public" / "data" / "books"


def symlink(src: Path, dst: Path) -> None:
    """创建/更新相对符号链接。若目标已存在且内容一致则跳过。"""
    if dst.is_symlink() or dst.exists():
        dst.unlink() if dst.is_symlink() else None
        if dst.exists() and not dst.is_symlink():
            # 非链接的真实文件/目录（历史遗留），先移除
            if dst.is_dir():
                import shutil
                shutil.rmtree(dst)
            else:
                dst.unlink()
    dst.parent.mkdir(parents=True, exist_ok=True)
    rel = os.path.relpath(src, dst.parent)
    dst.symlink_to(rel)


def main() -> None:
    if not SRC_BOOKS.exists():
        raise SystemExit(f"源目录不存在：{SRC_BOOKS}")

    DST_PUBLIC.mkdir(parents=True, exist_ok=True)

    # 顶层 index.json
    idx = SRC_BOOKS / "index.json"
    if idx.exists():
        symlink(idx, DST_PUBLIC / "index.json")
        print(f"  📎 {DST_PUBLIC / 'index.json'}")

    # 每本书
    for book_dir in sorted(SRC_BOOKS.iterdir()):
        if not book_dir.is_dir():
            continue
        book_id = book_dir.name
        dst_book = DST_PUBLIC / book_id

        # book.json
        if (book_dir / "book.json").exists():
            symlink(book_dir / "book.json", dst_book / "book.json")

        # catalog.json
        if (book_dir / "catalog.json").exists():
            symlink(book_dir / "catalog.json", dst_book / "catalog.json")

        # documents/ 整挂
        docs_src = book_dir / "documents"
        if docs_src.exists():
            symlink(docs_src, dst_book / "documents")

        print(f"  📚 {book_id}：book.json / catalog.json / documents")

    print(f"\n✅ 同步完成：{DST_PUBLIC}")


if __name__ == "__main__":
    main()
