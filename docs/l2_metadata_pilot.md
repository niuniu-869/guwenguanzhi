# L2 元数据 Pilot：史记 130 卷执行方案

> **状态**: Proposal（待 Stage 1 完成后进入执行）
> **日期**: 2026-04-14
> **上下文**: `docs/skill_design_v2.md` §2 三层架构的 L2 层
> **实施阶段**: Stage 2（pilot） → Stage 3（全量扩 23 部史）

---

## 1. 为什么先做史记 pilot

- **规模适中**：130 卷，~52 万字，单次 LLM 调用可处理一整卷（小米 API 上下文窗口充足）
- **风险可控**：成本 ~20 元，pilot 失败不伤筋动骨
- **最复杂**：本纪/世家/列传/书/表五体俱全，能验证 prompt 在各种结构下的泛化
- **对后续最有参考价值**：23 部后续史书的结构大多是"本纪 + 列传 + 志"的子集，pilot 过了后面降维打击

---

## 2. 输入数据

**底本来源**：`skill/vendor/daizhige/史藏/正史/史记*.txt`

**预期文件形态**（由 Stage 1 build_corpus 确认，以下为假设）：
- 可能情况 A：`史记.txt` 单文件，内部以"卷 N ..."分隔
- 可能情况 B：`史记_001.txt` ~ `史记_130.txt` 每卷一文件
- **build_corpus.py 需先摸清并切分**，产出统一的 `skill/vendor/daizhige/_split/shiji/{001..130}.txt`

**切分策略**：
- 正则匹配 `卷(\w+)` 或 `史記卷(\w+)`，中文数字 → 阿拉伯数字
- 切分后每卷一个 UTF-8 txt，首行保留卷名（如 `卷六 秦始皇本紀`）
- 校验：总卷数 = 130 ± 0 作为 pilot 启动前置条件

---

## 3. 元数据 Schema

每卷产出一份 `skill/data/metadata/shiji/{juan}.json`：

```jsonc
{
  "_prompt_version": "metadata-v1-2026-04-14",
  "book_id": "shiji",
  "book_name": "史记",
  "juan": 6,                               // 卷号，1-130
  "juan_name": "秦始皇本纪",                // 卷原名
  "juan_type": "本纪",                      // 本纪/世家/列传/书/表
  "author": "司马迁",
  "dynasty_covered": ["秦"],                // 本卷所涉朝代
  "time_range": {                          // 本卷时间跨度
    "start_year": -259,                    // 公元前 259
    "end_year": -210,
    "label": "秦庄襄王至始皇崩"
  },
  "key_figures": [                         // 核心人物（3-10）
    { "name": "嬴政", "aliases": ["秦始皇", "赵政"], "role": "主角" },
    { "name": "李斯", "aliases": [], "role": "重要" },
    { "name": "吕不韦", "aliases": [], "role": "重要" }
  ],
  "key_events": [                          // 核心事件（3-8）
    { "name": "嬴政即位", "year": -246 },
    { "name": "统一六国", "year_range": [-230, -221] },
    { "name": "焚书坑儒", "year": -213 },
    { "name": "始皇东巡", "year": -219 }
  ],
  "key_places": ["咸阳", "琅邪", "会稽"],
  "summary": "…（400-600 字白话概述，交代卷的结构、人物命运、关键转折、历史意义）…",
  "difficulty": 3,                         // 1-5，阅读难度
  "cross_refs": [                          // 本卷与其他典籍的互见
    { "book_id": "shiji", "juan": 87, "note": "李斯单独列传" },
    { "book_id": "guwenguanzhi", "slug": "093_过秦论上", "note": "贾谊追溯秦亡" }
  ],
  "tags": ["统一", "中央集权", "法家", "帝王术"],
  "source_char_count": 8420,               // 原文字数（字符，不含标点）
  "generation_metadata": {
    "model": "mimo-xxx",
    "input_tokens": 12000,
    "output_tokens": 800,
    "duration_ms": 8500
  }
}
```

**字段设计原则**：
- **可检索**：人物/事件/地名/tags 都走 `metadata.sqlite` 的 FTS5 索引
- **cross_refs** 是 agent "触类旁通"的关键 —— 问秦亡能跳到《过秦论》
- **difficulty** 帮 agent 为用户选读（初学者 skip 难度 5 的《天官书》这种）
- **time_range** 支持 `timeline.py` 的按年筛

---

## 4. Prompt 设计

### 4.1 文件结构（仿 `scripts/prompts/meta/`）

```
skill/scripts/metadata/prompts/
├── VERSION                      # "metadata-v1-2026-04-14"
├── system.md                    # 角色扮演 + 输出规范
├── user_history.md              # 正史（二十四史）用，带 {juan_name}/{juan_type}
├── user_classics.md             # 经子集用（预留 Stage 3+）
└── rules/
    ├── time_conversion.md       # 公元前/后、干支、年号换算
    └── figure_disambiguation.md # 一名多人/一人多名消歧
```

### 4.2 system.md 骨架

```markdown
你是一位精通中国古典文献的目录学专家，任务是为古籍单卷生成结构化元数据。

# 输出要求

- 严格 JSON 格式，字段与用户消息中的 schema 对齐
- 所有人物、事件、时间必须来自本卷原文，**禁止编造**
- 遇到原文未明确的时间/人物，用 `null` 或在 cross_refs 注释"需查他卷"
- summary 400-600 字，白话文，不套话，说清"这卷讲了什么"

# 核心纪律

1. 不引外部知识补充情节（比如《史记》说李斯上谏，别补《汉书·李斯传》细节）
2. 不做价值判断（"暴君""昏庸"），只转述
3. 时间换算公元前/后，干支纪年换算为公元年时标注"（约）"
4. 一名多人时按原文语境消歧，不确定则列出可能性
```

### 4.3 user_history.md 骨架

```markdown
请为以下古籍单卷生成元数据：

- 书名：{book_name}
- 卷号：{juan}
- 卷名：{juan_name}
- 文体类型：{juan_type}（本纪/世家/列传/书/表）

原文：
---
{juan_text}
---

输出 JSON，字段如下（严格对齐）：
{schema_json}
```

**注入 `{juan_text}` 时的截断策略**：
- 单卷 > 8000 字：先截到 8000，末尾注明"（本卷原文后半省略，仅基于前 8000 字生成元数据）"
- 单卷 > 20000 字（如《天官书》《封禅书》）：分两段各生成一份，人工合并

---

## 5. 执行参数

### 5.1 并发配置

```bash
# pilot
cd /niuniu869_dev/guwenguanzhi_ai
export MIMO_API_KEY=xxx  # 从 .env 读
export MAX_WORKERS=10    # pilot 保守，全量再升 20
export MIMO_RPM=60       # pilot 保守，全量升 90
export FORCE=0           # 只跑缺失/版本不匹配

python skill/scripts/metadata/generate.py \
    --book shiji \
    --juan-range 1-130 \
    --out skill/data/metadata/shiji/
```

### 5.2 复用现有管线

- `skill/scripts/metadata/generate.py` 直接 `from scripts.llm_client import call_llm_json`
- 并发模式仿 `scripts/run_all_parallel.py`（ThreadPoolExecutor + RPM manager）
- 失败重试：429 走 30/45/60s 退避（沿用 llm_client 默认），超过 6 次记录失败列表，pilot 结束后统一查看

### 5.3 成本估算

| 项 | 数量 | 单价 | 小计 |
|---|---|---|---|
| 输入 tokens | 130 卷 × 平均 6000 tokens | ~0.0001 元/千 tok | ~8 元 |
| 输出 tokens | 130 卷 × 平均 800 tokens | ~0.0003 元/千 tok | ~3 元 |
| 重试/失败补跑 | 预留 20% | — | ~3 元 |
| **pilot 总计** | | | **~15-20 元** |

**全量 24 部扩展时**（Stage 3）：130 × 25 ≈ 3250 次调用，预算 300-500 元。

---

## 6. 验收标准（必须全达标才进 Stage 3）

### 6.1 定量

- [ ] 130 个 JSON 文件全部产出，零失败
- [ ] 每个文件通过 `validate_schema.py`（schema 对齐、字段类型、必填项）
- [ ] 整批平均 API 延迟 < 10s
- [ ] 无 429 退避风暴（单次退避 > 60s 的记录 < 5%）
- [ ] 总成本 < 25 元（超过说明 prompt 冗余，需精简）

### 6.2 定性（人工抽检 10 卷）

从以下组合中随机抽 10 卷人工 review：
- 本纪 3 卷（高祖 / 秦始皇 / 孝文）
- 世家 3 卷（陈涉 / 孔子 / 留侯）
- 列传 2 卷（廉颇蔺相如 / 刺客）
- 书 1 卷（平准书）
- 表 1 卷（六国年表）

**每卷评分维度**（5 分制）：
- summary 准确度（没胡编 + 说清要点）
- key_figures 无错漏
- key_events 时间/名称无错
- cross_refs 合理（跳转有意义）
- difficulty 评级合理

**通过线**：平均分 ≥ 4.0，无单项 < 3.0

### 6.3 风险卡点

- **若 summary 大量套话或幻觉** → 回到 `system.md` 加"反套话清单"迭代
- **若 cross_refs 经常指向不存在的卷** → 加 post-validation：跑完后用 `search.py` 校验每条 cross_ref
- **若 difficulty 评级集中** → 说明 prompt 没给清标尺，加 rubric 示例
- **若 key_figures 一名多人混淆** → 加 `figure_disambiguation.md` rules

---

## 7. 产出交付清单

pilot 完成后向用户报告：

1. `skill/data/metadata/shiji/*.json` 130 份
2. `skill/data/metadata/shiji/_failures.jsonl`（若有，空也要有）
3. `docs/l2_pilot_report.md`：
   - 抽检 10 卷评分明细
   - 实际成本 / 时长 / 失败率
   - prompt 迭代日志（如果 pilot 中修改过 prompt）
   - "是否可进 Stage 3"的明确结论
4. 若结论是 NO：具体问题清单 + 建议修改方案

---

## 8. 与阅读器 + 旧管线的关系

- **不影响阅读器**：L2 元数据是 skill 独立资产，阅读器不读
- **不触碰旧管线**：`scripts/llm_client.py` 只 import 不修改
- **不产生冗余**：古文观止已有的深度标注（L3）不重新生成元数据（古文观止 222 篇走独立 meta.md prompt）

---

## 9. 后续扩展（Stage 3 预告）

本 pilot 通过后，直接用相同脚本扩展至：

| 书目 | 卷数 | 预估耗时（MAX_WORKERS=20） | 成本 |
|---|---|---|---|
| 汉书 | 100 | 1 小时 | ~15 元 |
| 后汉书 | 120 | 1.2 小时 | ~18 元 |
| 三国志 | 65 | 0.7 小时 | ~10 元 |
| 晋书~清史稿 | ~2885 | 30 小时（并发）| ~400 元 |
| **全量** | **~3300** | **~35 小时** | **~450 元** |

Stage 3 启动需要用户独立签发（pilot 通过 + 预算确认）。
