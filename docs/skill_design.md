# 古文观之 Skill 设计文档

> **状态**: Draft v0.1
> **日期**: 2026-04-13
> **作者**: 项目维护团队

## 1. 定位

**一句话**：让任何 Agent 加载本 Skill 后，立即获得「中国古典文献阅读 + 历史知识 + 原典查询 + 反幻觉的引经据典」四位一体能力。

**不是什么**：

- ❌ 单纯的"古文查词"工具（那只是 Skill 内嵌的 scripts/）
- ❌ 在线 API 服务（Skill 是离线本地的）
- ❌ 翻译模型（不消耗 LLM 配额做古文 → 白话）

**是什么**：

- ✅ 一份 markdown 写的"领域专家入职手册" + 一组确定性查询脚本 + 一个本地原典语料库
- ✅ Claude/Codex/Gemini CLI 等任何兼容 SKILL.md 标准的 Agent 都能直接 `pip install` 后使用
- ✅ 引用必带【篇·段·句】出处，杜绝 AI 幻觉典故

---

## 2. Skill 与阅读器的关系（核心）

```
┌─────────────────────────────────────────────────────────┐
│              data/books/  (单一可信源)                   │
│       guwenguanzhi/ + shiji/ + 未来扩展二十四史            │
└─────────────────────────────────────────────────────────┘
                    │
        ┌───────────┴────────────┐
        ▼                        ▼
┌───────────────┐         ┌──────────────────┐
│  阅读器前端    │         │   Skill          │
│  (Astro 网站)  │         │   (npm/pip 包)   │
└───────────────┘         └──────────────────┘
        │                        │
   ┌────┴─────┐             ┌────┴───────┐
   │ 面向人类  │             │ 面向 Agent │
   │ - 浏览    │             │ - 引用     │
   │ - 学习    │             │ - 查询     │
   │ - 鉴赏    │             │ - 推理     │
   └──────────┘             └────────────┘
```

### 2.1 共生关系矩阵

| 维度 | 阅读器 (Web) | Skill (Agent) |
|---|---|---|
| **目标用户** | 古文学习者、爱好者 | LLM Agent / 开发者 |
| **交互方式** | 视觉浏览、点击 | 函数调用、语义检索 |
| **输出形态** | HTML+CSS 渲染 | 结构化 JSON / Markdown |
| **数据消费** | 整篇文档 | 按需查询切片 |
| **质量诉求** | 美观、易读 | 精确、可引用 |
| **依赖** | `data/books/*/documents/` | `data/books/*/documents/` + `corpus.sqlite` |
| **更新节奏** | 跟随文档新增 | 跟随文档新增 + Skill 版本号 |

### 2.2 共享的内容资产

下面的资产**两边共享一份源**，避免双重维护：

```
guwenguanzhi_ai/
├── data/books/                  ← 单一数据源
│   ├── guwenguanzhi/
│   ├── shiji/
│   └── (future) hanshu/, ...
├── frontend/                    ← 阅读器
│   └── (symlink → ../data/books/)
└── skill/                       ← Skill
    ├── data → ../data/books     ← symlink
    ├── corpus.sqlite            ← 构建产物（FTS5 索引）
    └── ...
```

### 2.3 共享的"训诂规则"

**这是关键设计决策**：本次质检暴露的 prompt 改进规则（古今异义清单、通假字识别、虚词语境化等），既要写入 LLM 翻译管线的 prompt，**也要**写入 Skill 的 `references/methodology/translation-principles.md`。

→ 数据生产期：用规则约束 LLM 输出
→ Skill 使用期：用规则约束 Agent 推理

**实现方式**：把规则集中到 `prompts/translation_rules.md`，prompt 模板和 Skill 文档**都从这一份引用**（生成时 include）。

### 2.4 阅读器是 Skill 的"展示橱窗"

- 阅读器作为可视化界面，验证 Skill 输出的每一个数据点都是真实可查的。
- 用户通过阅读器发现错误 → 反馈机制 → 修复数据 → Skill 自动跟进（同源）。
- 阅读器 README 中可加："本网站数据可通过 [guwen-history Skill] 在你的 Agent 中调用"。

---

## 3. 目录结构

```
guwen-history/                          # 即将作为独立 PyPI 包发布
├── SKILL.md                            # 入口：~150 行
├── pyproject.toml                      # PyPI 元数据
├── README.md                           # 安装/接入说明
├── LICENSE                             # MIT (code) + CC BY-SA 4.0 (data)
│
├── references/                         # 按需加载的知识库
│   ├── methodology/                    # 方法论
│   │   ├── reading-classical.md        # 古文阅读方法
│   │   ├── translation-principles.md   # 信达雅 + 古今异义陷阱
│   │   ├── annotation-guide.md         # 训诂规则（实词/虚词/通假/多音）
│   │   └── citation-format.md          # 引用规范【书·篇·段】
│   │
│   ├── history/                        # 权威来源历史脉络（每篇 3-5k 字）
│   │   ├── 00_timeline.md              # 朝代年表速查
│   │   ├── 01_pre_qin.md               # 先秦
│   │   ├── 02_han.md                   # 两汉
│   │   ├── 03_wei_jin_nan_bei.md       # 魏晋南北朝
│   │   ├── 04_sui_tang.md              # 隋唐五代
│   │   ├── 05_song.md                  # 两宋
│   │   ├── 06_yuan_ming.md             # 元明
│   │   └── key_figures.md              # 重要人物速查
│   │
│   ├── corpus/                         # 原典索引
│   │   ├── guwenguanzhi.md             # 222 篇按主题/朝代/作者归类
│   │   ├── shiji.md                    # 史记五体结构
│   │   └── query_guide.md              # 如何用 scripts/ 查
│   │
│   └── advisory/                       # 输出范式
│       ├── analogy_patterns.md         # 古今映照思维框架
│       ├── lessons_template.md         # "以史为鉴"模板
│       └── fact_grounding.md           # 反幻觉强制规则
│
├── scripts/                            # 确定性查询（Claude bash 调用）
│   ├── lookup.py                       # 字/词/人/地索引
│   ├── search.py                       # FTS5 全文检索
│   ├── get.py                          # 取整篇原文+翻译+标注
│   ├── find_by.py                      # 按主题/朝代/人物筛
│   └── compare.py                      # 同字不同语境对比
│
├── data/                               # 离线索引（构建产物）
│   ├── corpus.sqlite                   # SQLite FTS5 全文检索
│   ├── word_postings.json              # 词→出处倒排
│   └── figures.json                    # 历史人物结构化
│
└── tests/
    ├── test_lookup.py
    ├── test_search.py
    └── test_no_hallucination.py        # 反幻觉测试
```

---

## 4. history/ 内容来源策略（核心要求）

### 4.1 原则

- **绝不 LLM 生成**：history/ 全部基于权威来源人工整理。
- **每段必须可追溯**：每个事实声明后标【参 XXX p.YY】或【参 https://...】。
- **学术规范引用**：参考文献集中列于文档末尾，使用 GB/T 7714 格式。

### 4.2 权威来源清单（候选）

按可信度排序：

| 类别 | 来源 | 用途 |
|---|---|---|
| **通史** | 范文澜《中国通史》（人民出版社） | 朝代脉络主线 |
| | 白寿彝《中国通史》（上海人民出版社，多卷） | 详细事件 |
| | 翦伯赞《中国史纲要》 | 简明速查 |
| **断代史** | 杨宽《战国史》、田余庆《秦汉魏晋史探微》 | 关键时期深度 |
| | 钱穆《国史大纲》 | 思想史视角 |
| **人物** | 《史记》《汉书》本传 | 一手史料引用 |
| | 谭其骧《中国历史地图集》 | 地名考证 |
| **西方汉学** | 剑桥中国史 (The Cambridge History of China) | 国际视角 |
| | Mark Edward Lewis《剑桥中国上古史》 | 先秦补强 |
| **工具书** | 《辞海》《辞源》 | 概念定义 |
| | 朱东润《中国历代文学作品选》 | 文学背景 |
| **网络资源** | 中国哲学书电子化计划 ctext.org | 原典对照 |
| | 维基百科中文版（仅作交叉验证，**不作主源**） | 辅助 |

### 4.3 引用格式范例

```markdown
## 春秋时期（前 770 - 前 476）

周平王东迁洛邑（前 770）标志东周开始[1]。这一时期诸侯并起，
"五霸"之说初见于《孟子·告子下》[2]，后世通常指齐桓、晋文、秦穆、宋襄、楚庄[3]。

实际上"霸"的原义为"伯"，即诸侯之长，并非"霸权"[4]。

---

**参考文献**

[1] 杨宽. 西周史[M]. 上海: 上海人民出版社, 2003: 856.
[2] 《孟子·告子下》. 见: 杨伯峻. 孟子译注[M]. 北京: 中华书局, 1960: 282.
[3] 范文澜. 中国通史: 第一册[M]. 北京: 人民出版社, 1978: 159.
[4] 钱穆. 国史大纲: 上册[M]. 北京: 商务印书馆, 1996: 60.
```

### 4.4 整理工作量预估

| 朝代文档 | 目标字数 | 引用条数（最低） | 工时 |
|---|---|---|---|
| 00_timeline.md | 2k | 10 | 0.5 天 |
| 01_pre_qin.md | 5k | 30 | 2 天 |
| 02_han.md | 4k | 25 | 1.5 天 |
| 03_wei_jin_nan_bei.md | 4k | 25 | 1.5 天 |
| 04_sui_tang.md | 5k | 30 | 2 天 |
| 05_song.md | 4k | 25 | 1.5 天 |
| 06_yuan_ming.md | 3k | 20 | 1 天 |
| key_figures.md | 8k | 80 | 3 天 |

**总计约 12-13 天人工整理**。可分阶段交付：先整 timeline + 先秦/汉，验证流程，再批量铺其他朝代。

### 4.5 备选方案（如果工作量太大）

- **方案 A（推荐）**：完全人工整理，质量保证，慢。
- **方案 B**：LLM 起草 → 人工逐句核对原文 → 补全引用。**坚决不允许"LLM 生成不核对就上线"**。
- **方案 C**：直接引用现有公开教材的电子版关键章节（注意版权），作为 references/history/raw/ 单独存放。

---

## 5. SKILL.md 主体结构

仿 Anthropic 官方 [claude-api skill](https://github.com/anthropics/skills/blob/main/skills/claude-api/SKILL.md) 风格：

```markdown
---
name: guwen-history
description: 中国古典文献（先秦至明）阅读与历史咨询专家。
  TRIGGER when: 用户阅读/翻译古文、问及中国古代人物/事件/典故、
  需引用经典原文（《古文观止》《史记》等）、求基于历史的决策参考、
  学习古汉语词义。
  DO NOT TRIGGER when: 现代汉语写作、近代以后历史（清以降）、
  其他语种古典文献、佛经/医书等专门古籍。
license: MIT (code) + CC BY-SA 4.0 (data)
---

## 何时使用本 Skill
[5 条具体触发场景]

## 核心原则（不可违反）
1. 引用原文必须经 scripts/get.py 验证 — 禁止凭印象引述
2. 翻译必须主动标注古今异义陷阱（参 translation-principles.md §3）
3. "历史建议"必须区分【史实/演绎/推断】三类标签
4. 不知道时 fall back to scripts/search.py，禁止编造典故出处
5. 引用格式统一：【书·篇·段】

## 决策树
[用户场景 → 必读文件 → 工具]

## 默认行为
[输出语言、注音规范、引用标记、不确定度标签]

## 反模式
[❌ 把《三国演义》当《三国志》、❌ 古今异义混淆…]

## 工具速查
[scripts/ 下每个脚本一行示例]

## 完整文件索引
[references/ 下每个文件一行说明]
```

---

## 6. MVP 范围与节奏

| 阶段 | 内容 | 工时 | 依赖 |
|---|---|---|---|
| **P0** | 数据修复（见 pipeline_diagnosis.md） | 5-7 天 | 阻塞 |
| **P1** | SKILL.md + methodology/ 4 篇 + scripts/lookup,search,get | 2-3 天 | P0 |
| **P2** | history/ 7 篇朝代知识（权威来源整理） | 8-10 天 | 可与 P1 并行 |
| **P3** | corpus/ 索引 + key_figures.json + advisory/ | 3-4 天 | P2 |
| **P4** | 反幻觉测试集 + examples/ | 2 天 | P3 |
| **P5** | 打包 PyPI + GitHub Release + 接入文档 | 1 天 | P4 |

**总计**：约 20-25 天到 v1.0（含 P0 数据修复）。

### MVP 之后的迭代方向

1. **接入二十四史**：扩 corpus/ + history/，结构不变
2. **英文翻译**：references/ 加 i18n
3. **创作辅助**：基于检索结果生成"模仿写作"模板
4. **MCP server 形态**：把 scripts/ 包成 FastMCP，让 Cursor/Cline 等也能用

---

## 7. 接入形态

### 7.1 Claude Code

```bash
# 直接 clone 到 ~/.claude/skills/
cd ~/.claude/skills && git clone https://github.com/niuniu-869/guwen-history-skill
```

### 7.2 Claude.ai（Pro/Team/Enterprise）

```bash
# 打包成 zip 上传到 Skills 设置页
cd guwen-history && zip -r guwen-history.zip . -x "*.pyc" "__pycache__/*"
```

### 7.3 任意 Agent SDK

```python
# pip install guwen-history
from guwen_history import lookup, search, get_document

result = search("民为贵社稷次之", limit=5)
for hit in result:
    print(f"{hit.book}/{hit.title} [{hit.position}]: {hit.snippet}")
```

### 7.4 MCP 形态（v2）

```bash
# uvx 一键启动
uvx guwen-history --mcp
# 在 Claude Desktop / Cursor / Cline 配置中添加
```

---

## 8. 待拍板项

1. **history/ 来源策略**：用方案 A（纯人工）还是方案 B（LLM 起草+核对）？
2. **是否提供英文翻译**：v1 跳过，v2 加？
3. **打包名称**：`guwen-history` / `chinese-classics-skill` / 其他？
4. **License**：代码 MIT 没争议，数据用 CC BY-SA 4.0（要求衍生作品同协议）还是 CC BY 4.0（更宽松）？
5. **发布渠道**：PyPI + GitHub Release 同步？还是只 GitHub？
