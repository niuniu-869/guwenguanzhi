# 数据管线巡检报告

> **执行日期**: 2026-04-13
> **执行者**: 主对话 Claude（亲自巡检，非 subagent）
> **范围**: scripts/ 全部生成脚本 + LLM 客户端 + schema 校验
> **目的**: 定位质检报告所列严重问题的代码根因

---

## 巡检结论速览

抽检报告列出的 8 类严重问题，**全部能在管线代码中找到根因**。绝大多数不是 LLM 模型能力问题，而是**管线设计缺陷**。

| 质检发现 | 根因位置 | 类别 |
|---|---|---|
| `type` 字段 48 种失控 | `02c`/`run_shiji.py` prompt 无强约束、无代码校验 | 缺校验 |
| 297 空 words 句 | `02c:103-107`、`run_shiji.py:218-222` 静默吞异常 | 错误处理 |
| 虚词 81.8% 空泛 | prompt 仅说"具体含义"无 few-shot、无反例 | prompt 弱 |
| 通假/多音/古今异义漏 | prompt 完全未提及 | prompt 缺失 |
| 古文观止/史记 schema 不一致 | 两套独立 prompt（type 6 vs 9 种） | 架构分裂 |
| 长句被合并为单词条 | prompt 缺"最小词组单元"约束 | prompt 弱 |
| `gen_meta` 长卷不完整 | `run_shiji.py:136` 强制截断 8000 字 | 设计缺陷 |
| 同字两套读音 | 缺跨段一致性校验 | 缺校验 |

---

## ⚠️ 同时发现的高危安全问题

### 🚨 API_KEY 明文硬编码并已 commit 到公开仓库

`scripts/llm_client.py:17`：

```python
API_KEY = "sk-c4906zis2rmob8pz4jwz0osfzwjofibknn88teohttcckvzm"
```

**这把 key 已存在于 git 历史**（commit `1a3d563` 等多个提交），即使现在改成环境变量，**git log 里仍可被任何人读到**。

**强烈建议立即采取行动**：

1. **吊销并替换 mimo API key**（去 https://platform.xiaomimimo.com 后台）
2. 改用环境变量：`API_KEY = os.environ["MIMO_API_KEY"]`
3. 加 `.env.example` 占位
4. 长期：用 `git filter-repo` 从历史中清除（涉及 force push，需评估）

> 我不会未经允许擅自动这一项 — 但这是当前仓库**最严重的暴露**，建议优先级高于一切其他工作。

---

## 详细根因分析（按严重度排序）

### 1. Schema 完全无代码层强制 — `type` 失控的直接原因

**症状**：抽检报告统计 48 种 `type`，prompt 写的 6 种枚举形同虚设。

**实测验证**：

```
type 种数: 48
  实词 261417, 虚词 100547, 人名 42294, 地名 23291,
  官职 6909, 典故 3403, 成语 2421, 器物 2231, 年号 770,
  词组 97, 名词 54, 专名 31, 代词 18, 实词短语 17,
  动词 16, 动词短语 15, 爵位 11, 短语 6, 专有名词 6,
  句子 6, 容貌 5, 物品 5, 服饰 4, 饮料 4, ...（共 48 种）
```

**根因**：

- `02c_generate_words.py:38`：prompt 只说"type: 分类，从以下选择：实词、虚词、人名、地名、官职、典故、书名"，**LLM 把它当软建议**。
- `04_quality_check.py:84-101` 的 `compute_score` **不校验 type**，只看覆盖率和空。
- `02d_merge.py` 合并阶段也不校验。
- 结果：错误数据一路 pass 到最终 JSON。

**修复方向**：

1. prompt 加硬约束："**严格只能取 6 种之一**，违反将被丢弃重做"
2. 加 `scripts/validate_schema.py`：JSON Schema 校验 + 自动重做违规项
3. `04_quality_check.py` 增加 type 维度统计 + 阈值告警

### 2. 静默失败吞异常 — 297 空 words 句的根因

**位置**：

```python
# scripts/02c_generate_words.py:102-108
try:
    result = call_llm_json(SYSTEM_PROMPT, prompt)
    merged.extend(result.get("sentences", []))
except Exception as e:
    for s in batch:
        merged.append({"original": s["original"], "words": [], "error": str(e)})
```

```python
# scripts/shiji/run_shiji.py:218-222
try:
    r = call_llm_json(WORDS_SYSTEM, prompt)
    return r.get("sentences", [])
except Exception as e:
    return [{"original": s["original"], "words": [], "error": str(e)} for s in batch]
```

**根因链**：

1. `BATCH_SIZE = 2`（古文观止）/ `5`（史记）—— 一批多句一起发
2. JSON 解析失败时（长句、嵌套引号、生僻字常触发），整批所有句子被标空
3. 没有"逐句 fallback 重试"机制
4. 没有"成功率统计" — 你不知道有多少批失败
5. `error` 字段被写入 JSON 但无人监控

**实测**：297 / 39528 = 0.75%，均匀分布在 126 个文件，正是"批中一句失败 → 全批空"的特征。

**修复方向**：

1. 异常时 fall back 到逐句重试（BATCH_SIZE=1）
2. 增加重试上限和退避
3. `04_quality_check.py` 把"`error` 字段存在的句子"列为强警告
4. 增加 Sentry/日志聚合（可选）

### 3. Prompt 设计缺失训诂关键规则

**当前 prompt（02c）**：

```
1. 按词组拆分（不是逐字）...
2. 虚词单独标注
3. 每个词提供 word/pinyin/meaning(在本句中的具体含义)/type
4. 注意多音字和通假字的正确标注
5. 拼接后必须等于原文
```

**问题**：

- "在本句中的具体含义" 是空洞要求，没有反例。LLM 仍输出"代词""助词"。
- "注意多音字和通假字" 是孤立提示，**没有具体清单、没有 few-shot 示例**。
- 完全没提"古今异义"。
- 完全没提"固定结构"（若…之何/何…之有）。
- 没有"自检"步骤。
- 温度 0.3 + 无 `response_format: json_object`，JSON 错率高。

**修复方向**：参 `quality_audit_2026-04-13.md` §Prompt 改进建议 6 条，全部进入 prompt v2。

### 4. 古文观止与史记 prompt 完全分离 — 架构问题

**现状**：

- `02c_generate_words.py` 维护一套 prompt（type 6 种）
- `scripts/shiji/run_shiji.py` 维护另一套 prompt（type 9 种，多了"年号|成语|器物"）
- `scripts/05_fix_and_rerun.py` 又有第三套精简版（meaning 限 10 字内）
- `scripts/shiji/fix_errors.py` 引用 `run_shiji.py` 的 prompt

**后果**：

- 跨书数据 schema 不统一（前端按 6 种渲染，史记数据自带 3 种额外类型）
- prompt 改进必须改 N 处，必然漂移
- 难以增加新书

**修复方向**：

1. 抽出 `scripts/prompts/` 目录，集中维护：
   ```
   scripts/prompts/
     ├── meta.md
     ├── translation.md
     ├── words.md           ← 单一源
     └── translation_rules.md   ← Skill 也引用这份
   ```
2. 所有脚本从这里 read template
3. 后续可与 Skill 的 `references/methodology/` 共享

### 5. 缓存机制粗暴 — prompt 改进后无法增量重跑

**位置**：所有脚本均有 `if output_file.exists(): return`。

**问题**：prompt v2 上线后，想用新 prompt 重跑某些文件，**必须手动删除 N 个旧文件**。质检脚本也无法自动触发重跑。

**修复方向**：

1. 在 output JSON 中嵌入 `prompt_version` 字段
2. 启动时对比当前 prompt hash，不一致则自动重跑
3. 或者增加 `--force` 参数支持目录级强制

### 6. JSON 解析过度容错 — 可能掩盖错误

**位置**：`scripts/llm_client.py:121-139`：

```python
# 尝试修复截断的 JSON（逐步补全闭合符号）
for suffix in ['"]}]}', '"}]}]}', ...]:
    try:
        return json.loads(fragment + suffix)
    except: continue
```

**问题**：截断的 JSON 强行补全，可能产生**部分有效 + 部分丢失**的数据，比直接报错更糟。

**修复方向**：

1. 直接报错并触发重试（用更高的 max_tokens）
2. 启用 `response_format: json_object`（如 mimo 兼容）
3. 加 `expected_keys` 校验，结构不全则重试

### 7. `gen_meta` 长卷强制截断 8000 字

**位置**：`scripts/shiji/run_shiji.py:136`：

```python
text = "\n".join(paras)
if len(text) > 8000:
    text = text[:8000] + "\n...(后略)"
```

**后果**：项羽本纪、平准书等长卷只看到前 8k 字就生成 background/appreciation，**后半部分人物事件完全缺席**。

**修复方向**：

1. 改为分段总结后再汇总（map-reduce）
2. 或对长卷分卷生成（按"太史公曰"自然切分）
3. 或把上下文压缩交给 LLM（"先总结再生成"两步）

### 8. 质检器 `04_quality_check.py` 漏检关键维度

**当前评分维度**：

```python
score = 100
if not has_background: -10
if not has_appreciation: -10
if not has_author_bio: -5
if empty_translations / sentences > 0: -30 * ratio
if empty_words / sentences > 0: -30 * ratio
if coverage_issues / annotated > 0: -15 * ratio
```

**漏检**：

- type 字段是否在 6 种枚举内 ❌
- 虚词 meaning 是否空泛 ❌
- 多音字一致性（同字不同段读音是否一致）❌
- 通假字是否标注 ❌
- 词组合并/拆分异常（如整句作单词条）❌
- 翻译是否漂亮但与词注释自相矛盾 ❌

**结果**：`avg_score: 95+` 完全无法反映抽检发现的真实质量（实际 60-65%）。

**修复方向**：

1. 增加 `validate_schema.py`（type 枚举 + 字段完整性）
2. 增加 `validate_consistency.py`（多音字一致性、词数异常检测）
3. 增加 `validate_semantics.py`（虚词空泛检测、关键古今异义白名单匹配）
4. 三层校验合并到 `04_quality_check.py`，重新评分

### 9. 词组合并失控 — `shiji/007.json` "亡其两骑" 问题

**位置**：`scripts/shiji/run_shiji.py:84`：

```
1. 词组切分：「郑武公」「伍子胥」「太史公曰」「燕雀安知鸿鹄之志哉」是一个词或成语，不要拆
```

**问题**：示范"燕雀安知鸿鹄之志哉"=**8字一个词条**——LLM 学到这种长合并，于是把"亡其两骑"也合成一个词。

**修复方向**：示例改为"项籍 / 陈胜 / 不忍 / 太史公曰"等 2-4 字典型词组，**避免给出超过 4 字的整句示例**。

### 10. RPM 限流是单进程内存 — 多脚本并跑会超限

**位置**：`scripts/llm_client.py:21`：

```python
_last_call_times: list[float] = []
```

模块级变量，**只在单 Python 进程内生效**。如果用户同时跑 `02b` 和 `02c`，或者用 `run_all_parallel.py` 多进程，限流完全失效，可能触发 429。

**修复方向**：

1. 改用 SQLite/文件锁实现跨进程限流
2. 或在外层（`run_all_parallel.py`）统一调度

---

## 修复优先级矩阵

| 优先级 | 任务 | 影响 | 工时 |
|---|---|---|---|
| **P0 紧急** | 处理 API_KEY 暴露（吊销+换 key） | 安全 | 0.5h |
| **P1 高** | 抽出 `scripts/prompts/` 集中目录 | 后续修复基础 | 1h |
| **P1 高** | prompt v2（6 条改进 + few-shot + 反例） | 解决 70% 问题 | 4-6h |
| **P1 高** | `validate_schema.py` 强制 type 枚举 | 防止数据再次漂移 | 2h |
| **P2 中** | 静默失败 → 逐句 fallback 重试 | 修复 297 空句 | 2h |
| **P2 中** | 增量重跑机制（prompt_version） | 后续可持续修复 | 2h |
| **P2 中** | 长卷 meta map-reduce | 史记长卷质量 | 3h |
| **P3 低** | 跨进程限流 | 暂未触发 | 4h |
| **P3 低** | 质检器全维度重写 | 长期 CI | 6h |

**总计**：P0+P1+P2 约 14-18 小时，可在 2-3 天内完成。

---

## 推荐执行顺序

```
┌─────────────────────────────────────────┐
│ Day 0 (今晚): API_KEY 处理 (你来执行)     │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│ Day 1 上午: scripts/prompts/ 集中化       │
│ Day 1 下午: prompt v2 + 6 篇 A/B 测试    │
│ Day 1 晚:   validate_schema.py 上线       │
└─────────────────────────────────────────┘
           ↓ A/B 通过
┌─────────────────────────────────────────┐
│ Day 2: 修复静默失败 + 增量重跑机制         │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│ Day 3: 定向重跑 297 空句（最快收益）       │
│ Day 3-5: 重跑先秦类 + 史记长篇            │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│ Day 6+: 质检器升级 + 长卷 meta 修复       │
└─────────────────────────────────────────┘
```

---

## 巡检结论

**坏消息**：抽检报告暴露的问题大部分是**架构性的**，不是 LLM 能力差，而是管线对输出根本没有约束。

**好消息**：所有问题都在代码可控范围内，**P0+P1+P2 两三天能修复 80% 的问题**。

**关键洞见**：**Skill 的反幻觉规则和 Prompt 的训诂约束应该是同一份内容**。如果按 §5 抽出 `scripts/prompts/translation_rules.md`，这份内容可以同时供给：

- LLM 翻译管线（生成期约束）
- Skill 的 `references/methodology/`（消费期约束）
- 阅读器的"标注规范"说明页（教育期解释）

**这是数据 → 工具 → 知识三位一体的最强协同点**。
