# 二十四史 Skill 重新构思（v2）

> **状态**: Proposal
> **日期**: 2026-04-14
> **前置阅读**: `docs/skill_design.md`（v1）、`docs/24histories_data_sources.md`（数据调研）
> **核心变化**: 从"数据标注项目"**重定位**为"agent 领域能力项目"

---

## 0. 为什么要重新构思

v1 设计实际上是**又一个数据管线项目**——花大量篇幅讨论"前四史怎么标注"。但你的真实诉求是：

> "让 agent 调用这个 skill 之后，就能对中国历史的逻辑和古文有足够的了解，可以查询古文知识、学习历史、也能给出基于历史的建议"

这不是数据项目，是**能力项目**。数据只是手段。

## 1. GitHub 调研的四个启发

### 1.1 Anthropic 官方 `skill-creator` 的黄金法则
- **Progressive disclosure 三层**：metadata 100 tokens（始终加载）→ SKILL.md <500 行（触发时加载）→ references/ 按需加载（无限大）
- **description 是"推送式"**：不是"我能做什么"，而是"什么场景下用我"
- **解释 Why 而非硬性 MUST**：`Use this template because [reasoning]` > `ALWAYS use this template`
- **重复的工作提成脚本**：`scripts/` 装确定性查询，避免 LLM 反复"算"同一件事

### 1.2 `obra/superpowers`（34k⭐ 编程方法论）— 强制性工作流
- 14 个核心 skill 全是**方法论而非知识**（TDD、systematic-debugging、brainstorming…）
- 关键思想：**Mandatory workflow, not suggestions**
- 我们借用：把"反幻觉引用"、"古今异义检查"、"朝代时序验证"做成**强制流程**而非"建议"

### 1.3 `AlterLab-Academic-Skills`（186+ 学术研究 skill）— 领域专家范式
- 按学科细分成多个 skill（bioinformatics / cheminformatics / clinical-research…）
- 每个 skill "transform Claude into domain-specific research expert"
- 我们借用：**不要做一个大 skill**，拆成几个可独立使用的领域 skill

### 1.4 `llm-knowledge-base-template`（Karpathy 风格）— raw→wiki→query
- 工作流：raw 源（原文/讲座笔记）→ Claude 编译成 wiki → scripts/search.py 查询
- 配健康检查 + 待处理队列 + 回存机制
- 我们借用：**底本（daizhige 原文） → 结构化 wiki（references/） → FTS5 查询（scripts/）**

### 1.5 意外发现：`bytedance/AncientDoc`（**CC0 许可**！）
- 字节跳动开源的 **3000 页古籍图像 + OCR/翻译/多层 QA 标注**，覆盖战国-清
- **CC0 意味着公共领域**，可直接再分发，**甚至可商用**
- 作为**评测基准**和**few-shot 样本池**，意义堪比 NiuTrans

---

## 2. 重塑的 skill 定位

### 2.1 一句话
**`china-classics` — 让 agent 获得"中国历史脉络 + 古文阅读能力 + 原典查询 + 反幻觉引用 + 基于历史的咨询"五位一体的领域能力。**

### 2.2 四种使用场景（全部必须跑通才叫 v1.0）

| 场景 | 触发 | 关键路径 |
|---|---|---|
| **A. 学习古文** | "帮我读懂《鸿门宴》" / "解释下《兰亭集序》第二段" | references/linguistic/ + data/annotated/（优先复用阅读器数据） |
| **B. 查询历史知识** | "张良投奔刘邦前做什么？" / "贞观之治的核心政策" | scripts/lookup.py + references/history/ + references/figures/ |
| **C. 基于历史的建议** | "创业合伙人理念不合怎么办" | references/advisory/ + scripts/analogy.py（检索相似历史情境） |
| **D. 反幻觉引用** | "《论语》'民可使由之'的标点争议" | scripts/cite.py 强制走原文 FTS5 校验 |

### 2.3 不是什么（避免走回老路）
- ❌ 另一个识典古籍 / shiji-kb 式"全库数字化"
- ❌ "前四史 270 万字全量标注"的数据项目
- ❌ 只靠 LLM 生成的"历史小百科"（会幻觉）
- ❌ 纯教学应用（那是阅读器的活）

---

## 3. 目录结构（取代 v1 §3）

```
china-classics/                         # 独立仓库
├── SKILL.md                            # ≤400 行：触发、原则、决策树、输出格式
│
├── references/                         # Progressive loaded，可无限大
│   ├── _index.md                       # 总目录（Claude 优先读）
│   │
│   ├── history/                        # 历史脉络（每篇 3-5k 字，全部带引用）
│   │   ├── timeline.md                 # 朝代年表速查
│   │   ├── 01_pre_qin.md               # 夏商周春秋战国
│   │   ├── 02_qin_han.md
│   │   ├── 03_wei_jin_nan_bei.md
│   │   ├── 04_sui_tang.md
│   │   ├── 05_song_yuan.md
│   │   ├── 06_ming_qing.md
│   │   └── institutions.md             # 职官/科举/典章
│   │
│   ├── figures/                        # 人物档案
│   │   ├── _index.md                   # 按朝代分组的人名总表
│   │   ├── pre_qin.md                  # 孔子/老子/孟子/荀子/韩非...
│   │   ├── han.md                      # 刘邦/项羽/司马迁/韩信/张良/董仲舒...
│   │   └── ...
│   │
│   ├── classics/                       # 典籍导读（不是原文，是"怎么读"）
│   │   ├── shiji.md                    # 史记的五体结构、阅读门径、精选篇章
│   │   ├── lunyu.md
│   │   ├── guwenguanzhi.md             # 与本项目阅读器对接
│   │   └── _selection.md               # 初学必读 / 进阶 / 专题 三档书单
│   │
│   ├── linguistic/                     # 古汉语方法论 ★差异化核心
│   │   ├── reading-classical.md        # 阅读方法论（断句/虚词/语境）
│   │   ├── translation-principles.md   # 信达雅 + 古今异义陷阱
│   │   ├── annotation-guide.md         # 实词/虚词/通假/多音/活用
│   │   ├── common-traps.md             # 常见误读清单（"妻子" ≠ wife…）
│   │   └── citation-format.md          # 引用规范【书·篇·段·句】
│   │
│   └── advisory/                       # ★差异化核心：历史咨询范式
│       ├── analogy-framework.md        # 古今映照思维框架
│       ├── decision-patterns.md        # 历史决策模板（用人/变革/危机）
│       ├── 20-insights.md              # 20 条经验/教训的案例化清单
│       ├── fact-grounding.md           # 反幻觉铁律
│       └── uncertainty-labels.md       # 【史实】/【演绎】/【推断】/【建议】
│
├── data/                               # 数据层（可共享阅读器）
│   ├── corpus.sqlite                   # daizhige 正史 + 经典典籍全文 FTS5
│   ├── annotated/                      # 精选篇章深度标注
│   │   └── (symlink → ../../data/books/)  # 复用现有古文观止 v2 数据
│   ├── figures.json                    # 人物结构化（借鉴 shiji-kb + CBDB）
│   ├── events.json                     # 关键事件结构化（CHisIEC/CHED 启发）
│   └── postings.json                   # 词→出处倒排索引
│
├── vendor/                             # 第三方数据镜像（可删可重建）
│   ├── daizhige-zhengshi/              # git submodule 或脚本拉取
│   ├── ancientdoc-cc0/                 # 字节 CC0 基准
│   └── niutrans-parallel/              # MIT 文白对照
│
├── scripts/                            # 确定性查询（反幻觉基石）
│   ├── lookup.py                       # 人/地/职/典故/年号 索引
│   ├── search.py                       # FTS5 全文 + 短语搜索
│   ├── cite.py                         # 原文引用生成+校验【书·篇·段】
│   ├── timeline.py                     # 按年/朝代筛事件
│   ├── analogy.py                      # 历史类比：当代情境 → 古代先例
│   └── build_index.py                  # 离线构建 corpus.sqlite
│
├── evals/                              # 反幻觉测试
│   ├── test_citation.jsonl             # 100 条：引文必须精确
│   ├── test_figures.jsonl              # 100 条：人物时代/事迹不错
│   ├── test_dynasty.jsonl              # 50 条：朝代时序不错
│   ├── test_traps.jsonl                # 50 条：古今异义不混
│   └── test_advisory.jsonl             # 30 条：历史建议有据可查
│
├── pyproject.toml                      # PyPI 打包
└── README.md
```

**和 v1 的关键区别**：
- `references/advisory/` 和 `references/linguistic/` 成为**一级核心**（原 v1 埋在 methodology 里）
- `data/` 大幅简化，不再追求"全量标注"
- 新增 `evals/` 做反幻觉测试（v1 只是提一嘴）
- 新增 `vendor/` 明确分离第三方镜像，license 风险隔离

---

## 4. SKILL.md 的新写法（遵循 Anthropic 官方）

```markdown
---
name: china-classics
description: 中国古典文献与历史咨询专家。
  TRIGGER when: 用户阅读/翻译古文、问及中国古代（至清）人物事件典故、
  需引用经典原文（论语/史记/古文观止等）、寻求基于历史的决策参考、
  学习古汉语词义、创业/管理/人际决策寻找历史先例。
  DO NOT TRIGGER when: 近代以后（清末民国以降）历史、现代汉语写作、
  其他文明古典文献、佛经/医书/道藏等专门古籍。
license: MIT (code) + CC BY-SA 4.0 (wiki) + 各 vendor 原许可
---

# 中国古典文献与历史专家

## 何时使用本 Skill
[5 条具体触发场景，含示例 prompt]

## 强制工作流（Mandatory, not suggestions）
1. 凡引用原文 → 必须走 scripts/cite.py 校验，禁止凭印象
2. 凡涉及古文词义 → 查 references/linguistic/common-traps.md
3. 凡给"历史建议" → 用 references/advisory/uncertainty-labels.md 的三标签（【史实】/【演绎】/【推断】）
4. 不确定时 → scripts/search.py 全文查，禁止编造典故
5. 超出本 skill 覆盖（近代以后/非汉文化圈）→ 明确声明能力边界

## 决策树
[用户场景 → 必读 references/ → 可用 scripts/]

## 默认输出格式
[引用标记、拼音规范、不确定度标签]

## 反模式
[❌ 把《三国演义》当《三国志》、❌ 古今异义混淆、❌ 朝代错位引用…]

## 工具速查
[scripts/ 每个一行示例]

## 文件索引
[references/ 每个文件一句话说明（让 Claude 知道何时加载）]
```

关键改动：
- 加入**强制工作流**（受 superpowers 启发）
- description 明确 **TRIGGER / DO NOT TRIGGER**（Anthropic 官方推荐格式，可把触发准确率从 20% 拉到 50-90%）
- 500 行硬上限，超出全部推到 references/

---

## 5. 标注与数据策略（重写 v1 §4）

### 5.1 三种数据角色，各走各路

| 角色 | 内容 | 获取 | 许可 |
|---|---|---|---|
| **底本文本** | 二十四史 + 经/子/集部核心典籍 | daizhige + AncientDoc CC0 | CC0 可再分发 |
| **精选标注** | 阅读器 270 篇深度 JSON（古文观止 222 + 史记精选 48） | **小米 API 生成** | 我们拥有 |
| **references/ 知识** | 历史/人物/典籍导读/方法论/咨询范式 | **人工主导 + LLM 起草辅助** | CC BY-SA |

### 5.2 精选标注的"前四史 pilot"重新定义
- **不是** 415 卷全量跑 — 那是识典古籍的活
- **是** 每史挑 **12 篇代表性纪传**（共 48 篇）+ 古文观止已有的 6 篇史记相关 = **54 篇**做深度标注
- 成本：54 × 3 轮 LLM ≈ 162 次小米 API，不到 100 元
- 产出：同古文观止 v2 的 JSON 结构，直接进 `data/books/shiji/` 等
- **这 54 篇同时服务阅读器 + skill 的 `data/annotated/`**

### 5.3 references/ 的"不纯 LLM 生成"铁律
- **允许** LLM 起草 → 人工逐句核对原文 → 补全引用
- **禁止** LLM 直接生成未经核对的内容入库
- 每段历史叙述后必须有 `[^1]` 引用，文末列权威来源（范文澜/白寿彝/剑桥中国史/原典 fts 校验）
- references/ 的 health check 脚本：检查每篇是否有引用、引用数下限、是否全是"据说/相传"

### 5.4 "基于历史的建议"怎么不幻觉
这是最难的一块，方案：
1. **analogy.py 强制检索**：用户给的当代情境 → scripts/analogy.py 在 data/events.json 里找 3-5 个相似历史情境
2. **输出格式强制三段**：【史实：XX 发生了什么（带原文引用）】→【演绎：这个情境的普遍模式】→【建议：对当代的启发，明确标注"这只是类比，不是预测"】
3. **evals/test_advisory.jsonl** 30 条反幻觉测试：故意问"类比"中古已有的近现代事件，看 skill 是否拒绝

---

## 6. 与阅读器的新关系

```
阅读器（Web）                    china-classics Skill
────────────────────────         ──────────────────────
用户在浏览器读古文观止 222 篇   ←→  用户对 Claude 说"帮我读懂…"
                                    ↓
                               references/linguistic/ 加载
                                    ↓
                               data/annotated/ 读取同一份 JSON
                                    ↓
                               输出带引用的解读

共用的单一数据源：
  ├── data/books/guwenguanzhi/     (古文观止 222 篇，已 v2)
  └── data/books/shiji/            (史记精选 48 篇，待 pilot)
        ↑                               ↑
  阅读器 Astro 页面          china-classics/data/annotated/ symlink
```

两边的用户完全不同，但同一份深度标注数据两用。

---

## 7. 迭代路线图（取代 v1 §6）

| 阶段 | 目标 | 工时 | 可交付 |
|---|---|---|---|
| **P0** | SKILL.md 骨架 + references/_index.md + 3 篇方法论 | 2 天 | 空 skill 也能装 |
| **P1** | scripts/ 的 lookup + search + cite + build_index | 3 天 | 基于 daizhige 的查询能用 |
| **P2** | references/history/ 六篇朝代（LLM 起草 + 人工核对） | 8-10 天 | 场景 B 跑通 |
| **P3** | references/linguistic/ 全套 + 古文观止 v2 接入 | 3 天 | 场景 A 跑通 |
| **P4** | 史记精选 48 篇 pilot 标注 | 2 天（并发）| data/annotated 扩 |
| **P5** | references/figures/ + CBDB/shiji-kb 借鉴 | 5 天 | 人物查询闭环 |
| **P6** | references/advisory/ 20-insights + analogy.py | 5 天 | 场景 C 跑通 |
| **P7** | evals/ 全套测试 + 反幻觉验证 | 3 天 | 场景 D 有保障 |
| **P8** | PyPI + GitHub Release + 接入示例 | 1 天 | v1.0 上架 |

**总计 ~32 天到 v1.0**（比 v1 的 25 天多 7 天，但覆盖四个完整场景而非只有"古文阅读"）。

---

## 8. 决策点（等你拍板）

1. **Skill 粒度**：一个大 `china-classics`（all-in-one）还是拆成 `china-history` + `classical-chinese-reader` + `history-advisor` 三个（AlterLab 模式）？
   - 我倾向 **合一**：v1 用户心智简单，内部用 references/ 子目录区分。v2 再按需拆。
2. **references/advisory/ 的 "20 insights"由谁整理**：我基于经典案例列候选（如"信陵君窃符救赵→越级担责的代价"）你定稿？
3. **字节 AncientDoc CC0 的用法**：只做评测（放 evals/），还是也进 data/corpus.sqlite（扩大底本）？我倾向两用。
4. **pilot 史记精选 48 篇**：我给候选名单你终审，还是你直接指定？
5. **skill 仓库位置**：本仓库 `skill/` 子目录？还是开新仓库 `china-classics-skill`？建议先在本仓库 `skill/` 开发，ready 后迁出。

---

## 9. 相对 v1 的变化总结

| 维度 | v1 | v2 |
|---|---|---|
| 定位 | 数据+阅读器的 skill 版 | **agent 领域能力项目** |
| 核心 | `data/books/` | **`references/` + `scripts/`** |
| pilot | 前四史 415 卷全量 | **史记精选 48 篇 + references/ 骨架** |
| "建议"能力 | 模糊提及 | **独立一级场景，带 analogy.py** |
| 反幻觉 | 4.5 节寥寥数语 | **强制工作流 + evals/ 30+100+100+50+50 条** |
| LLM 使用 | 不准用 / 勉强用 | **起草可以，核对必须** |
| 工作量 | 25 天 | 32 天（多出来的都花在 references/ 和 evals/） |

---

## 10. 下一步

我等你对本构思拍板后，再写：
- `docs/skill_design_v2.md`（取代现有 skill_design.md）
- `docs/pilot_shiji_48_plan.md`（48 篇精选名单 + 标注计划）
- `docs/references_history_outline.md`（六篇朝代史的章节提纲 + 权威来源映射）

本文档到此为止，不动任何代码。
