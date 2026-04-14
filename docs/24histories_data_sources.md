# 二十四史 Skill 数据源与竞品调研

> **状态**: Draft v0.1
> **日期**: 2026-04-14
> **目的**: 在动手实现前四史 pilot 之前，广泛摸清市面上已有数据、已有做法、许可证边界

---

## 一、市场格局全景

### 1.1 公益 / 商业平台（直接面向读者）

| 平台 | 团队 | 覆盖 | AI 能力 | 形态 | 与我们的关系 |
|---|---|---|---|---|---|
| **识典古籍** shidianguji.com | 字节 × 北大 | 百衲本二十四史完整 + 四部丛刊 + 四库；2900+ 部 | OCR 96-97%、自动标点、NER、**RAG 古籍助手**、实体关系图 | Web/App，完全免费 | 底层数字化的天花板，难以竞争 |
| **读典籍** dudianji.com | 商业 | 47 部含前四史 | 文白对照、交互注释、古汉语字典 | iOS/Android/Web | 阅读体验类竞品 |
| **中华书局古联 / 籍合网** | 国家队 | "国家古籍数字化资源总平台"（测试中） | 大模型辨残补缺 + OCR | Web | 权威但封闭 |
| **国学大师** guoxuedashi.net | 老牌站 | 二十四史全译检索 | 非 AI | Web | 传统资源站 |

### 1.2 学术模型（可作为标注引擎）

| 模型 | 团队 | 训练语料 | 能力 | 可用性 |
|---|---|---|---|---|
| **荀子 XunziALLM** | 南农王东波（+中华书局） | 四库全书 + 200 亿字古籍 | POS/NER/分词/文白翻译；Qwen 兼容 | ModelScope 开源权重 |
| **通古 TongGu** | 华南理工 | 百川 2-7B + 24 亿字古文 | RAG + 句读 + 文白翻译 + 检索问答 | HF |
| **AI 太炎 2.0** | 北师大 | 国家语委项目 | 古文综合 | 未见公开 |

### 1.3 直接对标的 AI 阅读器项目 ⚠️

- **shiji-kb** ([baojie/shiji-kb](https://github.com/baojie/shiji-kb)) — 这是离我们最近的项目：
  - 一个人用 AI 把《史记》57 万字做成**可交互知识图谱**
  - 23 类实体语法高亮（19 名词 + 4 动词）
  - **17,571 个实体条目**，595 个别名归并，644 语义消歧
  - Purple Numbers 段落引用体系
  - 已做出 20+ 条跨章节洞察（"征服—治理反转"、"边缘优势"等）
  - 静态 html 站：https://baojie.github.io/shiji-kb/
  - **警示**：他做的是"学术型知识图谱 + 跨章节洞察"；我们做的是"逐词释义 + 白话翻译 + 赏析导读"，路径差异明显但**用户注意力是稀缺品**，不能忽视

---

## 二、开源数据源（按类型分）

### 2.1 原文底本

| 源 | 内容 | 获取 | LICENSE | 商用 | 推荐度 |
|---|---|---|---|---|---|
| **daizhige v2.0** ([garychowcmu/daizhigev20](https://github.com/garychowcmu/daizhigev20)) | 史藏/正史 48 个 txt，**二十四史齐全** + 集解/索隐/正义三家注 | `git clone` | ⚠️ 未声明 | 灰色 | ⭐⭐⭐⭐ 主源 |
| **ctext.org** | 二十四史全文，带 API | `pip install ctext` | ❌ **明确非商用** + **禁止自动化下载**（违者封禁） | 不可 | ⭐⭐ 仅交叉校验 |
| **wenku/shiji** ([GitHub](https://github.com/wenku/shiji)) | 史记单部 | clone | 未声明 | 灰色 | ⭐⭐ |
| **识典古籍前端** | 百衲本 + AI 标点 | 需爬 | 宣称"免费开放"，条款不明 | 灰色 | ⭐⭐（风险） |

**结论**：daizhige 作为主底本够用（48 文件含完整二十四史），**ctext 只做少量交叉校验**，避免踩其非商用+禁爬线。

### 2.2 文白平行语料（给 prompt 做 few-shot）

| 源 | 规模 | 覆盖 | LICENSE | 推荐度 |
|---|---|---|---|---|
| **NiuTrans/Classical-Modern** | 327 部古文 + 97 部带译 + **972,467 句对** | 句子级对齐，含前四史部分章节 | ✅ **MIT** | ⭐⭐⭐⭐⭐ |
| **Cathy-wang132/文白对照** | 17,087 条带解析 | 未声明来源 | 非商用 | ⭐⭐⭐ |
| **JiangYanting/Pre-modern_Chinese_corpus** | 近代汉语综合 | 数字人文 | 未声明 | ⭐⭐ |

**结论**：NiuTrans 是最关键发现 — MIT 许可 + 接近百万句对 + 含前四史片段，可作为 prompt few-shot 样本池或校对参考。

### 2.3 标注种子语料（NER/事件/POS）

| 源 | 覆盖 | 格式 | LICENSE | 用途 |
|---|---|---|---|---|
| **CHisIEC** | 13 部二十四史 / 22 卷；14,194 实体 + 8,609 关系 | CoNLL + JSON | 未声明 | NER few-shot |
| **CHED** | 本纪+列传 8,122 句事件 | 专用 schema | 未声明 | 事件抽取参考 |
| **南农 POS 语料**（Nature 2026） | 二十四史+现代译文双语 POS | 见 [vino5211/Sequence-Labeling-for-POS-tag](https://github.com/vino5211/Sequence-Labeling-for-POS-tag)（待核实） | 论文未明 | 词性 few-shot |

**结论**：都是"未声明许可证"的学术语料。作为 prompt 示例/校对基准可用，**不直接再分发**。

### 2.4 知识图谱 / 人物词典

| 源 | 内容 | 可复用性 |
|---|---|---|
| **shiji-kb** | 17k+ 实体表、别名归并表、语义消歧 | 如开源元数据可直接借用（省大量人工） |
| **CBDB 哈佛中国历代人物传记数据库** | 50 万+ 历史人物结构化 | CC BY-NC-SA，需引用 |

---

## 三、许可证红线清单

| 行为 | 风险 |
|---|---|
| 整体再分发 daizhige txt | ⚠️ 灰色（原作者未明，但内容多为公共领域文本搬运） |
| 任何形式调用/抓取 ctext | ❌ 违反其 TOS（商用 + 自动化） |
| 再分发 CHisIEC/CHED 原始标注 | ⚠️ 未声明，建议仅作 prompt few-shot 不入库 |
| 用 NiuTrans/Classical-Modern 生成派生语料 | ✅ MIT 允许 |
| 用小米 API 生成的派生数据 | ✅ 按小米 TOS（需核实），我们拥有输出 |
| 对接识典古籍公开 API | ⚠️ 官方声明"标准化数据接口支持学术/开发者 API 接入"，**但未见公开文档**，需邮件申请 |

**强烈建议**：整个 skill 的数据层按"底本合法派生 + LLM 生成标注"定位，避开直接再分发第三方标注数据。

---

## 四、类似做法对比矩阵

| 维度 | 我们（古文观之） | 识典古籍 | shiji-kb | 读典籍 |
|---|---|---|---|---|
| **数据广度** | 精选（古文观止 222 + 前四史 pilot） | 全库（2900+ 部） | 史记单部 | 47 部 |
| **标注深度** | 作者/背景/赏析/段落翻译/**逐词释义+拼音+词性** | 标点+NER | 23 类实体 + 跨章洞察 | 文白对照+字典 |
| **交互形态** | 三模式阅读器（原文/对照/逐词） | 平铺列表 | 静态 html + 图谱 | App 化阅读器 |
| **AI 含量** | LLM 生成结构化 JSON | OCR+NER+RAG 问答 | LLM 抽实体+归并 | NLP 生成文白 |
| **受众** | 古文学习者/爱好者 | 学者/研究 | 数字人文爱好者 | 普通读者/学生 |
| **商业模式** | 开源 + 未来 skill | 公益免费 | 个人项目 | 商业 App |

**我们的差异化落点**（三选一或叠加）：
1. **"逐词释义 + 拼音 + 赏析"的深度**是别人都没做的（识典只有 NER，shiji-kb 无白话翻译）
2. **Skill 形态**让 Agent 能反幻觉引用（别人都只有 UI）
3. **精选策展**（前四史挑 50-80 篇经典篇章做深，而非全量 500+ 卷都做）

---

## 五、前四史 pilot 规模评估

### 5.1 字数与卷数

| 史书 | 卷数 | 约字数 | 核心篇章估算 |
|---|---|---|---|
| 史记 | 130 | 52 万 | 本纪 12 + 世家 30 + 关键列传 30 ≈ 72 篇 |
| 汉书 | 100 | 80 万 | 本纪 12 + 关键传/志 ≈ 40 篇 |
| 后汉书 | 120 | 90 万 | 本纪 10 + 关键列传 ≈ 30 篇 |
| 三国志 | 65 | 37 万 | 关键人物纪传 ≈ 30 篇 |
| **合计** | **415** | **~260 万字** | **~170 篇精选** |

### 5.2 两种 pilot 策略

**策略 A — 全量标注（类古文观止全 222 篇做法）**
- 工作量：415 卷 × 平均 3 轮 LLM 调用 ≈ 1200+ 次调用
- 成本：按古文观止 v2 小米 API 单篇 ~0.5 元估算，约 600-1000 元
- 周期：全并发 1-2 天（按 `MAX_WORKERS=20`）
- 风险：后汉书有整卷超 2 万字，LLM 上下文超限需切段

**策略 B — 精选策展（推荐 pilot）**
- 挑 170 篇最有阅读价值的纪传（类似"史学观止"）
- 工作量 ~170 篇 × 3 轮 ≈ 500 次调用，成本 200-300 元，周期半天
- **每篇都做深**：完整的逐词释义 + 拼音 + 词性 + 赏析 + 历史背景
- **差异化最强**：别人做不到这个深度

### 5.3 prompt 改造点

现有 `scripts/prompts/meta/user_shiji.md` 已有模板基础，但需针对二十四史特性补：
- **人物关系标注**（列传特有）
- **地名古今对照**（大量郡县名需还原）
- **官职解释**（秦汉魏官制差异大）
- **纪年换算**（年号 → 公元）
- **三家注整合**（集解/索隐/正义可并入注释字段）

---

## 六、关键决策点（给你拍板）

1. **pilot 策略选 A 全量还是 B 精选？** → 建议 B，花小钱验证差异化
2. **底本是 daizhige 单源还是 daizhige + 识典官方邮件申请 API？** → 先用 daizhige，邮件申请并行走（可能数周才回）
3. **三家注是否纳入？** → 建议纳入史记/汉书，做成"注释"字段（阅读器里可选显示）
4. **精选篇章谁来挑？** → 建议我基于权威选目（如中华书局《史记选》《三国志选》）给出 170 篇候选名单再 review
5. **skill 形态先做哪类查询？** → 阅读器复用优先？还是反幻觉引用优先？

---

## 七、对现有 skill_design.md 的修订建议

现有 `docs/skill_design.md` 写于下线史记管线之前，需要三处增补：

1. **§3 目录结构** — 增加 `vendor/daizhige/` 作为底本镜像（symlink）；`data/books/{shiji,hanshu,houhanshu,sanguozhi}/`
2. **§4 history/ 来源** — 权威教材 + **NiuTrans 平行语料** + **CBDB 人物数据库**，分层标注清楚
3. **§8 待拍板项** — 补充本调研带出来的红线：非商用许可的数据只作 prompt 输入不入库

建议保留 `skill_design.md` 作为"目标蓝图"，新增本文档作为"数据来源依据"，再写 `docs/pilot_sishi_plan.md` 作为"前四史 pilot 执行计划"（等你拍板上述决策点后起草）。

---

## 八、参考来源

- [识典古籍平台介绍](https://caijing.chinadaily.com.cn/a/202403/21/WS65fbff12a3109f7860dd66d1.html)
- [shiji-kb 知识图谱项目](https://github.com/baojie/shiji-kb)
- [daizhige v2.0](https://github.com/garychowcmu/daizhigev20)
- [NiuTrans/Classical-Modern 平行语料（MIT）](https://github.com/NiuTrans/Classical-Modern)
- [CHisIEC 二十四史信息抽取语料](https://github.com/tangxuemei1995/CHisIEC)
- [CHED 跨史书事件数据集](https://github.com/lcclab-blcu/CHED)
- [XunziALLM 荀子大模型](https://github.com/Xunzi-LLM-of-Chinese-classics/XunziALLM)
- [Cathy-wang132 文白对照数据集](https://github.com/Cathy-wang132/Dataset-for-translating-classical-Chinese-into-modern-Chinese-and-vice-versa)
- [Chinese Text Project API（非商用）](https://ctext.org/tools/api)
- [二十四史古今 POS 语料 - Nature Heritage Science 2026](https://www.nature.com/articles/s40494-026-02309-w)
- [识典古籍上线智能助手 - 中国日报](https://caijing.chinadaily.com.cn/a/202403/21/WS65fbff12a3109f7860dd66d1.html)
