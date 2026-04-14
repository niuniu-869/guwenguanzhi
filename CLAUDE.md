# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目定位

古文观止在线阅读器 + 未来的古典文献 Skill。纯静态站点（Astro + React），数据由 Python + LLM 管线离线生成，通过 GitHub Pages 部署（`site: niuniu-869.github.io`, `base: /guwenguanzhi`）。

## 常用命令

### 前端（`frontend/` 下，Node ≥ 22.12）

```bash
cd frontend
npm install
npm run dev          # predev 会先跑 sync-data
npm run build        # prebuild 同样先跑 sync-data
npm run preview
```

`sync-data` 等价于 `python3 ../scripts/sync_frontend_data.py`，会在 `frontend/public/data/books/` 下为每本书分项建 symlink（只暴露 `index.json`/`book.json`/`catalog.json`/`documents/*.json`，屏蔽 `raw*/output` 等中间产物）。直接修改 `data/books/` 后无需手动同步，下一次 dev/build 自动生效。

### 数据管线（仓库根，需 `.env` 中 `MIMO_API_KEY`）

```bash
pip install opencc-python-reimplemented requests
python scripts/01_prepare_raw.py            # 从 raw 语料清洗
python scripts/run_all_parallel.py          # 全量并发：02a→02b→02c→02d
python scripts/04_quality_check.py          # 输出 data/quality_report.json
python scripts/validate_schema.py
```

管线控制环境变量：
- `MAX_WORKERS`（默认 20）、`MIMO_RPM`（默认 90）
- `STEP=meta,trans,words,merge` 任选子集
- `FORCE=1` 忽略 `_prompt_version` 全量重跑；否则只重跑版本不匹配的文件

每个中间/最终 JSON 都嵌入 `_prompt_version`（见 `scripts/prompts/VERSION`）——Prompt 改动后务必 bump 版本，让下一次 `run_all_parallel.py` 自动识别并重跑受影响的文件。

### 部署

推到 `main` 即触发 `.github/workflows/deploy.yml`（Node 22，`npm run build` → `actions/deploy-pages@v4`）。不要手动 push 到 `gh-pages`。

## 架构要点

### 1. 多书架构（单一可信源在 `data/books/`）

```
data/books/
  index.json              # 书目清单（首页读它）
  <bookId>/
    book.json             # 单本元信息
    catalog.json          # 目录（章节/朝代分组）
    documents/**/*.json   # 每篇文章一个 JSON
```

当前只挂载 `guwenguanzhi`。`shiji/` 和 `scripts/_archive/` 已在 `.gitignore` 中下线，**等待通过独立 Skill 对接开源二十四史数据后重建**——不要在本仓库内重新标注二十四史（参见 `docs/skill_design.md` 和最近 commit `b4d8f1b` "下线史记管线，保留多书架构"）。`data/catalog.json`、`data/articles/` 是旧版结构，已被 `books/` 取代，仍保留作历史参照。

### 2. 管线四段式（`scripts/`）

```
02a_generate_metadata.py   # 作者/背景/赏析
02b_generate_translations.py  # 段落 + 整句白话翻译
02c_generate_words.py      # 逐词拼音 + 释义 + 词性（失败时 fallback 到逐句重试）
02d_merge.py               # 合并到 documents/<dynasty>/<slug>.json
```

共用 `scripts/llm_client.py`（`call_llm_json` 带 JSON 校验和重试）和 `scripts/prompts/`（`meta/`, `translation/`, `words/`, `rules/` 分目录；`load_prompt` + `PROMPT_VERSION` 由 `prompts/__init__.py` 暴露）。**修改 prompt 必须更新 `scripts/prompts/VERSION`**，否则已生成文件会被误判为"当前版本"而跳过。

### 3. 前端路由

```
frontend/src/pages/
  index.astro                                # 首页：读 books/index.json 列书架
  book/[bookId]/index.astro                  # 某本书首页
  book/[bookId]/group/[groupId].astro        # 朝代/分组页
  book/[bookId]/doc/[docId].astro            # 文章详情
```

核心 React 组件：`DocumentReader.tsx`（三模式阅读器：原文/对照/逐词）与 `ReadingView.tsx`。`CatalogTree.astro` 渲染目录树。所有页面 `getStaticPaths` 读取 `frontend/public/data/books/...`（symlink）——这是前端与数据的唯一接口。

### 4. 数据 Schema（JSON 稳定约定）

文章 JSON = `{ title, author:{name,dynasty,bio}, background, appreciation, paragraphs:[{ original, translation, sentences:[{ original, translation, words:[{ word, pinyin, meaning, type }] }] }] }`。`type` 使用"实词/虚词"等中文分类。`dynasty` 取值：`pre_qin | han | wei_jin | tang | song | ming`。改动字段会同时影响管线、schema 校验和前端渲染，需三处同步。

## 约束与惯例

- **不要提交图片、raw 语料、中间 JSON**：`.gitignore` 已禁 `*.png`、`data/raw/guwenguanzhi_raw.txt`、`data/articles/**/*_meta.json|_trans.json|_words.json`、`data/books/*/output/` 等。PR 前检查 `git status`。
- **`frontend/public/data/` 永远是 symlink**，不要 `git add` 其实体内容；`sync_frontend_data.py` 会自动重建。
- **注释与提示语一律中文**（见现有代码风格），prompt 模板位于 `scripts/prompts/**/*.md`。
- **用户未主动要求时不要自行 `git commit` / `git push` / 建分支**（全局用户偏好）。
- 杀进程时用 `fuser -k <port>/tcp` 或 PID，禁止 `pkill -f` 模糊匹配（Trae 环境下会误杀 ptyHost）。

## 参考文档

- `docs/skill_design.md` — 未来 Skill 的定位与阅读器的共生关系
- `docs/pipeline_diagnosis.md`, `docs/quality_audit_2026-04-13.md` — 管线质量审计
- `README.md` — 面向用户的项目介绍和数据格式样例
