# china-classics

> 中国古典文献阅读 + 历史咨询的 Agent Skill
> **状态**: 🚧 开发中 (v0.1 skeleton, Stage 0 完成)
> **上游**: [guwenguanzhi_ai](https://github.com/niuniu-869/guwenguanzhi) 项目，v1.0 ready 后拆出独立仓库

## 定位

让任何 Agent（Claude / Codex / Gemini CLI 等）加载本 Skill 后，立即获得：

- **古文阅读**：逐句翻译 + 逐词释义 + 古今异义陷阱提示
- **历史查询**：人物/事件/典章/年号 索引 + 原典佐证
- **历史咨询**：基于古代先例的现代决策建议（带三标签不确定度）
- **反幻觉引用**：引用原文必经 FTS5 校验，禁止编造

## 安装（规划中）

### Claude Code
```bash
cd ~/.claude/skills
git clone https://github.com/niuniu-869/china-classics-skill china-classics
```

### Claude.ai (Pro/Team/Enterprise)
```bash
cd china-classics
zip -r china-classics.zip . -x "*.pyc" "__pycache__/*" "vendor/*" "data/*.sqlite"
# 上传到 Claude.ai Skills 设置页
```

### Python SDK
```bash
pip install china-classics  # v1.0 后可用
```

```python
from china_classics import lookup, search, cite, analogy

# 查人物
result = lookup("张良")

# 全文搜原典
hits = search("民为贵社稷次之", limit=5)

# 校验引用
cite_text = cite("史记/卷062/段3")

# 历史类比
cases = analogy("合伙人理念不合")
```

### MCP Server（v2 规划）
```bash
uvx china-classics --mcp
```

## 架构概览

```
L1 底本层  — daizhige 二十四史 + AncientDoc CC0 + NiuTrans
L2 元数据层 — 二十四史 ~3300 卷 summary + key_figures/events
L3 深度标注 — 古文观止 222 篇（复用阅读器数据）
```

详见 [`../docs/skill_design_v2.md`](../docs/skill_design_v2.md)。

## 开发路线

| Stage | 内容 | 进度 |
|---|---|---|
| 0 | 文档 + 骨架 | ✅ |
| 1 | L1 底本接入 (corpus.sqlite + search/cite) | 🚧 |
| 2 | L2 元数据 pilot (史记 130 卷) | ⏳ |
| 3 | L2 全量 (其余 23 部史) | ⏳ |
| 4 | references/ 核心层 (5 子目录) | ⏳ |
| 5 | scripts/ 查询工具完善 | ⏳ |
| 6 | evals/ 反幻觉测试 (330+ 条) | ⏳ |
| 7 | SKILL.md 定稿 + v1.0 发布 | ⏳ |

## 本地开发

```bash
cd skill/
# 1. 拉取底本 vendor
bash scripts/vendor/pull_all.sh

# 2. 构建 FTS5 全文检索
python scripts/build_corpus.py

# 3. 验证查询
python scripts/search.py "管仲" --limit 10
python scripts/cite.py "史记/卷062/段3"
```

## 数据来源与许可

| 源 | 用法 | License |
|---|---|---|
| [daizhige v2.0](https://github.com/garychowcmu/daizhigev20) | 二十四史底本（本地 vendor/，不入 git） | 未声明（公共领域派生） |
| [AncientDoc](https://github.com/bytedance/AncientDoc) | corpus 补充字段 | **CC0** ✅ |
| [NiuTrans/Classical-Modern](https://github.com/NiuTrans/Classical-Modern) | prompt few-shot 样本 | **MIT** ✅ |
| ctext.org | ⛔ 禁用（非商用 + 禁爬） | — |

本 skill 输出内容：
- 代码：MIT
- 数据/文档 wiki：CC BY-SA 4.0（衍生作品同协议）

## 贡献

Issue / PR 欢迎，参照根仓库 `docs/skill_design_v2.md` 的设计规范。

所有 references/ 内容必须遵守：
- 每段带 `[^N]` 引用
- 文末列权威来源（范文澜/白寿彝/剑桥中国史/原典）
- 禁止"据说/相传/大约"模糊表述

## 致谢

- [Anthropic skill-creator](https://github.com/anthropics/skills) — 范式参考
- [obra/superpowers](https://github.com/obra/superpowers) — Mandatory workflow 思想
- [AlterLab-Academic-Skills](https://github.com/AlterLab-IEU/AlterLab-Academic-Skills) — 领域专家 skill 范式
- [baojie/shiji-kb](https://github.com/baojie/shiji-kb) — 直接启发（史记知识图谱）
