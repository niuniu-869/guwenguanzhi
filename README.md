# 古文观止

> 222 篇经典古文 · 逐句翻译 · 逐词注释 · 拼音标注

一个面向古文学习者的开源工具，收录《古文观止》全部 222 篇文章，提供三种阅读模式和 AI 生成的结构化翻译数据。

**在线预览**: [https://niuniu-869.github.io/guwenguanzhi](https://niuniu-869.github.io/guwenguanzhi)

## 特性

- **按朝代分类** — 先秦 · 两汉 · 魏晋南北朝 · 唐 · 宋 · 明
- **三种阅读模式**
  - **原文模式** — 沉浸阅读，点击任意词弹出释义
  - **对照模式** — 每段原文配整段白话翻译
  - **逐词模式** — 拼音标注 + 词组释义 + 逐句翻译
- **结构化数据** — 每篇文章含写作背景、文学赏析、作者简介
- **纯静态** — 无需后端，GitHub Pages 直接部署

## 技术栈

| 层面 | 技术 |
|------|------|
| 前端 | Astro 6 + React 19 + Tailwind CSS 4 |
| 数据生成 | Python + LLM API (并发管线) |
| 字体 | Noto Serif SC / Noto Sans SC |
| 部署 | GitHub Pages |

## 项目结构

```
├── data/
│   ├── raw/              # 原文语料（按朝代分目录）
│   ├── articles/          # AI 生成的结构化 JSON
│   └── catalog.json       # 全部 222 篇索引
├── scripts/               # 数据生成管线
│   ├── 01_prepare_raw.py  # 语料清洗
│   ├── 02a-d_generate_*.py # LLM 翻译管线
│   └── run_all_parallel.py # 并发全量生成
├── frontend/              # Astro 前端
│   └── src/
│       ├── pages/         # 首页 + 朝代页 + 文章页
│       ├── components/    # React 阅读组件
│       └── styles/        # 设计系统
└── .github/workflows/     # CI/CD
```

## 本地开发

```bash
# 前端
cd frontend
npm install
npm run dev

# 数据生成（需要 LLM API）
pip install opencc-python-reimplemented requests
python scripts/01_prepare_raw.py
python scripts/run_all_parallel.py
```

## 数据格式

每篇文章是一个 JSON 文件，结构如下：

```jsonc
{
  "title": "师说",
  "author": { "name": "韩愈", "dynasty": "tang", "bio": "..." },
  "background": "写作背景...",
  "appreciation": "文学赏析...",
  "paragraphs": [
    {
      "original": "古之学者必有师。",
      "translation": "古代求学的人一定有老师。",
      "sentences": [
        {
          "original": "古之学者必有师。",
          "translation": "古代求学的人一定有老师。",
          "words": [
            { "word": "古", "pinyin": "gǔ", "meaning": "古代", "type": "实词" },
            { "word": "之", "pinyin": "zhī", "meaning": "的", "type": "虚词" },
            { "word": "学者", "pinyin": "xué zhě", "meaning": "学习的人", "type": "实词" }
          ]
        }
      ]
    }
  ]
}
```

## 参与贡献

欢迎通过 Issue 或 PR 参与：

- 修正翻译或注释错误
- 改进 UI/UX 设计
- 新增语言翻译（英文、日文等）

## 致谢

- 原文语料来源：[wenyuange/ji](https://github.com/wenyuange/ji)
- 翻译数据由 AI 生成，仅供参考学习

## License

MIT
