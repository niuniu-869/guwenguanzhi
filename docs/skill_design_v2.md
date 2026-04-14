# China-Classics Skill 设计文档 v2

> **状态**: Approved v2.0
> **日期**: 2026-04-14
> **取代**: `docs/skill_design.md`（v0.1 draft，已归档意义）
> **参考**: `docs/skill_redesign_v2.md`、`docs/24histories_data_sources.md`
> **实施计划**: `/root/.claude/plans/effervescent-booping-oasis.md`

---

## 1. 定位

**一句话**：让任何 Agent 加载本 Skill 后，立即获得**中国古典文献阅读 + 历史知识 + 原典查询 + 反幻觉引用 + 基于历史的咨询建议**五位一体能力。

**形态**：`china-classics` ——一份 markdown 写的"领域专家入职手册" + 一组确定性查询脚本 + 一个本地知识库/原典语料库。Claude / Codex / Gemini CLI 等兼容 SKILL.md 标准的 Agent 直接加载即用。

### 1.1 Skill vs 阅读器：共生关系

```
┌─────────────────────────────────────────────────────────┐
│         data/books/guwenguanzhi/ (单一数据源)             │
│         + skill/vendor/ (二十四史底本)                     │
└─────────────────────────────────────────────────────────┘
                    │
        ┌───────────┴────────────┐
        ▼                        ▼
┌───────────────┐         ┌──────────────────┐
│  阅读器前端    │         │   china-classics │
│  (Astro 网站)  │         │   (PyPI + Skill) │
└───────────────┘         └──────────────────┘
   面向人类               面向 Agent
   - 浏览古文观止        - 引用原典
   - 学习赏析            - 查询历史
   - 3 模式阅读          - 咨询建议
                         - 反幻觉
```

**共享**：
- `data/books/guwenguanzhi/documents/` 222 篇深度标注 JSON（阅读器读 + skill 通过 symlink 读）
- "训诂规则" `scripts/prompts/rules/` ← → `skill/references/linguistic/`（同一份规则两侧引用）

**不共享**：
- 阅读器有 UI、分页、交互；skill 无
- Skill 有 vendor 二十四史全量底本、元数据索引、references 知识库；阅读器无

### 1.2 不是什么（避免走回 v1 数据项目老路）

- ❌ 又一个识典古籍 / shiji-kb 式"全库数字化"平台
- ❌ "前四史 270 万字全量深度标注"的数据工程
- ❌ 纯 LLM 起草的"历史小百科"（必然幻觉）
- ❌ 纯教学应用（那是阅读器的责任）

---

## 2. 三层数据架构

```
┌────────────────────────────────────────────────────┐
│ L1 底本层（全量，零成本，公共领域派生）              │
│   daizhige 史藏/正史（二十四史齐全 + 三家注）        │
│   + AncientDoc CC0 (3000 页字节开源)                │
│   + NiuTrans/Classical-Modern (MIT, 972k 句对)      │
│   → skill/data/corpus.sqlite (FTS5 全文检索)       │
└────────────────────────────────────────────────────┘
                        ↓ agent 用 search.py
┌────────────────────────────────────────────────────┐
│ L2 元数据层（全量，轻量 LLM 生成）                   │
│   二十四史 ~3300 卷，每卷一份 metadata：             │
│   {title, author, dynasty, juan,                    │
│    key_figures[], key_events[],                     │
│    summary_500字, difficulty_1_5,                   │
│    cross_refs[], aliases[]}                         │
│   → skill/data/metadata.sqlite                      │
└────────────────────────────────────────────────────┘
                        ↓ agent 用 lookup.py 决策深入哪卷
┌────────────────────────────────────────────────────┐
│ L3 深度标注层（按需，不阻塞 v1.0）                   │
│   现有：古文观止 222 篇 v2（已完成）                 │
│   未来：按用户呼叫热度渐进扩展                        │
└────────────────────────────────────────────────────┘
```

**核心设计决策**：
- L1 全量（daizhige 原文零成本）—— 保证知识库不遗漏
- L2 全量（~400 元 LLM 成本）—— 提供 agent 做"该读哪一卷"决策的索引
- L3 按需 —— 深度标注是阅读器场景，skill 不阻塞

---

## 3. 四个核心使用场景

### 场景 A — 古文阅读
**触发**：用户让 agent 读懂某篇古文
**输入示例**：`"帮我读懂《鸿门宴》"` / `"解释下《兰亭集序》第二段的意思"`
**关键路径**：`references/linguistic/reading-classical.md` + `data/annotated/guwenguanzhi/documents/{dynasty}/{slug}.json`（symlink 复用阅读器数据）+ `scripts/cite.py` 校验引用
**输出规范**：原文 → 逐段翻译 → 难词释义 → 古今异义提示 → 背景典故

### 场景 B — 历史查询
**触发**：用户问中国古代（至清）人物/事件/典故/官制
**输入示例**：`"张良投奔刘邦前做什么"` / `"贞观之治的核心政策"`
**关键路径**：`scripts/lookup.py(query)` 索引 → `references/figures/{dynasty}.md` 档案 → `scripts/search.py` 原典佐证
**输出规范**：档案化答复 + 【书·卷·段】引用 + 不确定处明确标注

### 场景 C — 基于历史的咨询
**触发**：用户面对现代决策情境求历史先例
**输入示例**：`"创业合伙人理念不合怎么办"` / `"面对组织变革阻力如何推进"`
**关键路径**：`scripts/analogy.py(situation)` → `references/advisory/20-insights.md` + `data/events.json` → 返回 3-5 个类比情境
**输出规范**：**三段式 + 三标签**
```
【史实】XX 发生了什么（带原文 URN 引用）
【演绎】这类情境的普遍模式
【推断·建议】对当代的启发；明确标注"这是类比，不是预测"
```

### 场景 D — 反幻觉引用
**触发**：涉及原文引述、标点争议、版本差异
**输入示例**：`"《论语》'民可使由之'的标点争议"` / `"诸葛亮《出师表》原文第三句"`
**关键路径**：强制调 `scripts/cite.py(urn)` 走 FTS5 校验 → 不存在则明确拒答，禁止编造
**输出规范**：原文逐字转引 + URN + 若有版本差异列表

---

## 4. 目录结构

```
skill/                                   # 本仓库 skill/ 子目录开发
├── SKILL.md                             # ≤400 行：触发、强制工作流、决策树
├── README.md                            # 3 种接入方式
├── pyproject.toml                       # PyPI 元数据
├── LICENSE                              # MIT (code) + CC BY-SA 4.0 (wiki)
│
├── references/                          # Progressive disclosure 按需加载
│   ├── _index.md                        # 总目录（Claude 优先读）
│   │
│   ├── history/                         # 朝代脉络（每篇 3-5k 字带引用）
│   │   ├── timeline.md                  # 朝代年表速查
│   │   ├── 01_pre_qin.md                # 夏商周春秋战国
│   │   ├── 02_qin_han.md
│   │   ├── 03_wei_jin_nan_bei.md
│   │   ├── 04_sui_tang.md
│   │   ├── 05_song_yuan.md
│   │   ├── 06_ming_qing.md
│   │   └── institutions.md              # 职官/科举/典章
│   │
│   ├── figures/                         # 人物档案
│   │   ├── _index.md                    # 按朝代分组的人名总表
│   │   ├── pre_qin.md                   # 孔子/老子/孟子/荀子/韩非...
│   │   ├── han.md                       # 刘邦/项羽/司马迁/韩信/张良/董仲舒...
│   │   ├── tang.md
│   │   └── ...
│   │
│   ├── classics/                        # 典籍导读（非原文，是"怎么读"）
│   │   ├── _index.md                    # 24 部经典导读索引
│   │   ├── shiji.md                     # 史记五体结构、阅读门径、精选卷目
│   │   ├── lunyu.md
│   │   ├── guwenguanzhi.md              # 与本项目阅读器接口
│   │   └── _selection.md                # 初学必读 / 进阶 / 专题 三档书单
│   │
│   ├── linguistic/                      # ★差异化：古汉语方法论
│   │   ├── reading-classical.md         # 阅读方法论（断句/虚词/语境）
│   │   ├── translation-principles.md    # 信达雅 + 古今异义陷阱
│   │   ├── annotation-guide.md          # 实词/虚词/通假/多音/活用
│   │   ├── common-traps.md              # 常见误读清单（"妻子" "走" "涕"…）
│   │   └── citation-format.md           # 引用规范【书·卷·段·句】
│   │
│   └── advisory/                        # ★差异化：历史咨询范式
│       ├── analogy-framework.md         # 古今映照思维框架
│       ├── decision-patterns.md         # 历史决策模板（用人/变革/危机）
│       ├── 20-insights.md               # 20 条经典案例（用户定稿）
│       ├── fact-grounding.md            # 反幻觉铁律
│       └── uncertainty-labels.md        # 【史实】/【演绎】/【推断·建议】
│
├── data/                                # 数据层
│   ├── corpus.sqlite                    # L1 FTS5 全文检索（构建产物）
│   ├── metadata.sqlite                  # L2 元数据索引（构建产物）
│   ├── annotated/                       # L3 symlink → ../../data/books/
│   ├── figures.json                     # 人物结构化
│   ├── events.json                      # 关键事件结构化
│   └── postings.json                    # 词→出处倒排
│
├── vendor/                              # .gitignore 忽略，按需拉
│   ├── daizhige/                        # git clone depth=1
│   ├── ancientdoc-cc0/                  # CC0 下载
│   └── niutrans-parallel/               # MIT git clone
│
├── scripts/                             # 确定性查询（反幻觉基石）
│   ├── build_corpus.py                  # 构建 corpus.sqlite
│   ├── build_metadata_index.py          # 合并 metadata/*.json → metadata.sqlite
│   ├── search.py                        # FTS5 全文搜索
│   ├── cite.py                          # 原文引用生成+校验
│   ├── lookup.py                        # 人/地/职/年号索引
│   ├── timeline.py                      # 按年/朝代筛事件
│   ├── analogy.py                       # 历史类比（咨询场景）
│   ├── metadata/
│   │   ├── generate.py                  # L2 元数据生成（复用 scripts/llm_client）
│   │   └── prompts/                     # system.md + user.md + VERSION
│   └── vendor/
│       └── pull_all.sh                  # 拉三个 vendor 源
│
└── evals/                               # 反幻觉测试
    ├── test_citation.jsonl              # 100 条
    ├── test_figures.jsonl               # 100 条
    ├── test_dynasty.jsonl               # 50 条
    ├── test_traps.jsonl                 # 50 条
    ├── test_advisory.jsonl              # 30 条
    └── run_evals.py
```

---

## 5. SKILL.md 写法（遵循 Anthropic 官方）

### 5.1 YAML Frontmatter

```yaml
---
name: china-classics
description: 中国古典文献与历史咨询专家。
  TRIGGER when: 用户阅读/翻译古文、问及中国古代（至清末）人物事件典故、
  需引用经典原文（论语/史记/古文观止等）、寻求基于历史的决策参考、
  学习古汉语词义、创业/管理/人际决策寻找历史先例。
  DO NOT TRIGGER when: 近代以后（清末民国以降）历史、现代汉语写作、
  其他文明古典文献（希腊/罗马/印度）、佛经/医书/道藏等专门古籍。
license: MIT (code) + CC BY-SA 4.0 (wiki)
---
```

**description 原则**（Anthropic 官方：从 20% 触发率→ 50-90%）：
- **TRIGGER when** / **DO NOT TRIGGER when** 明确边界
- 列举用户常用短语（"帮我读懂" "解释下" "历史上有没有类似")
- 包含反面场景（"不触发"清单比"触发"清单更重要）

### 5.2 主体结构（≤400 行）

```markdown
# 中国古典文献与历史专家

## 何时使用
[5 条具体场景 + 各配 1 条示例 prompt]

## 强制工作流（Mandatory, not suggestions）★
1. 凡引用原文 → 必须走 scripts/cite.py 校验，禁止凭印象
2. 凡解释古文词义 → 先查 references/linguistic/common-traps.md
3. 凡给"历史建议" → 用 references/advisory/uncertainty-labels.md 的三标签
4. 不确定时 → scripts/search.py 全文查，禁止编造典故
5. 超出覆盖（近代以后/非汉文化）→ 明确声明能力边界

## 决策树
[四场景 → 必读 references/ + 可用 scripts/]

## 默认输出格式
- 引用：【书·卷·段·句】格式
- 不确定度：【史实】/【演绎】/【推断·建议】三标签
- 拼音：汉语拼音方案，多音字标注
- 繁简：输出简体，引用可保留繁体原形

## 反模式（❌ 绝对禁止）
- ❌ 把《三国演义》当《三国志》引用
- ❌ 古今异义混淆（"妻子" "走" "涕" "汤"）
- ❌ 朝代错位引用（孔子说春秋时事用秦汉以后官职）
- ❌ 编造年号、谥号、官名、地名
- ❌ 对未查证的"相传/据说"典故直接输出

## 工具速查
[scripts/ 每个一行示例命令]

## 文件索引
[references/ 每个文件一句话说明]
```

### 5.3 关键创新：强制工作流

借鉴 `obra/superpowers`（34k⭐）的 "Mandatory workflow, not suggestions" 思想，把反幻觉从"建议"升级为"强制流程"。Agent 被本 skill 触发后，五条硬规则始终生效。

---

## 6. 核心原则（不可违反）

1. **引用必经校验**：`cite.py` 走 FTS5 发现原文，禁止凭印象引述
2. **翻译必标陷阱**：古今异义词必须按 `common-traps.md` 主动提示
3. **建议必分标签**：历史咨询输出必须三段式 + 三标签
4. **不知 fall back**：`search.py` 查，查无 → 明确拒答
5. **引用格式统一**：【书·卷·段·句】，如`【史记·卷062·廉颇蔺相如列传·段3】`
6. **边界声明**：超出覆盖范围必须明确 skill 能力边界，不硬接

---

## 7. 实施路线图

按 `/root/.claude/plans/effervescent-booping-oasis.md` 分 Stage 0-7 推进：

| Stage | 内容 | 工时 | LLM 成本 |
|---|---|---|---|
| 0 | 文档定稿 + skill/ 骨架 | 1-2 天 | 0 |
| 1 | L1 底本接入（vendor + corpus.sqlite + search/cite） | 2-3 天 | 0 |
| 2 | L2 元数据 pilot（史记 130 卷） | 2 天 | ~20 元 |
| 3 | L2 全量生成（其余 23 部史） | 1-2 天并发 | ~400 元 |
| 4 | references/ 核心层（5 子目录） | 10 天（与 3 并行） | ~50 元 |
| 5 | scripts/ 查询工具完善 | 4 天 | 0 |
| 6 | evals/ 反幻觉测试 | 3 天 | 0 |
| 7 | SKILL.md 定稿 + v1.0 发布 | 2 天 | 0 |
| **合计** | — | **25-30 天** | **~470 元** |

---

## 8. License 与红线

| 源 | 用法 | License 处理 |
|---|---|---|
| daizhige | `vendor/` 本地使用，**不入 git** | 未声明，按"学术使用 + 公共领域派生" |
| AncientDoc | 可入 corpus 且再分发 | **CC0** ✅ |
| NiuTrans | prompt few-shot 样本池 | **MIT** ✅ |
| CHisIEC/CHED | **不复用**（未声明许可） | 跳过 |
| ctext.org | **绝对禁用**（非商用+禁爬） | 🚫 |
| 小米 API 生成物 | skill 数据资产 | 按小米 TOS（需复核） |
| 本 skill 输出 wiki | CC BY-SA 4.0 | 衍生作品同协议 |

---

## 9. 相对 v1 的核心变化

| 维度 | v1 (2026-04-13) | v2 (2026-04-14) |
|---|---|---|
| 定位 | 数据+阅读器的 skill 版 | **agent 领域能力项目** |
| 数据核心 | `data/books/` 深度标注 | **`references/` + `scripts/`** |
| 数据策略 | 前四史 415 卷全量深度标注 | 三层架构：L1 全量底本 + L2 全量元数据 + L3 按需深度 |
| "建议"能力 | 模糊提及 | **独立一级场景，带 analogy.py** |
| 反幻觉 | §4.5 寥寥数语 | **强制工作流 + evals/ 330+ 条测试** |
| 场景数 | 一个（古文阅读） | 四个（阅读/查询/咨询/反幻觉） |
| LLM 使用 | 不允许或勉强用 | **起草允许，核对必须** |
| 工作量 | 25 天 | 25-30 天（多出来的全花在 advisory/ 和 evals/） |

---

## 10. 待拍板项

1. **Skill 发布时机**：先在本仓库 `skill/` 稳定开发到 v1.0，再用 `git filter-repo` 拆独立仓库（已定）
2. **打包名称**：`china-classics` ≠ `guwen-history`（原 v1 名，有史学偏向，v2 更中立）
3. **v2 License**：代码 MIT + 数据 CC BY-SA 4.0（保留衍生作品同协议）
4. **首发渠道**：PyPI + GitHub Release + Claude Code skill marketplace

---

## 11. 参考来源

- [`docs/skill_redesign_v2.md`](skill_redesign_v2.md) — 构思调研（GitHub skill 生态 + 重定位论证）
- [`docs/24histories_data_sources.md`](24histories_data_sources.md) — 二十四史数据源调研（daizhige / AncientDoc / NiuTrans / ctext 许可证矩阵）
- [Anthropic skill-creator 官方范式](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)
- [`obra/superpowers`](https://github.com/obra/superpowers) — Mandatory workflow 思想
- [`AlterLab-Academic-Skills`](https://github.com/AlterLab-IEU/AlterLab-Academic-Skills) — 领域专家 skill 范式
- [`baojie/shiji-kb`](https://github.com/baojie/shiji-kb) — 直接对标项目（史记知识图谱）
