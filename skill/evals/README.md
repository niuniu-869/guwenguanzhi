# skill evals —— 反幻觉测试集

> 330 条评测用例，覆盖 5 个维度。用于验证 skill 工具层不产生/不放行幻觉。

## 维度

| 类别 | 条数 | 正/负例 | 评测方式 |
|---|---|---|---|
| citation | 100 | 50 真 + 50 伪 | `cite.py --verify` 对伪例必拒 |
| figures | 100 | 70 真 + 30 伪 | `lookup.py` 对伪名必返空 |
| dynasty | 50 | 50 条 | 两人 lifespan 是否交叉（反时序幻觉） |
| advisory | 30 | 20 真 + 10 现代词 | `analogy.py` strict 对现代专有词必 0 |
| traps | 50 | 50 古今异义 | prompts only，需 agent 或人工判分 |

## 基线（2026-04-14）

```
citation    92%  (92/100)
figures     100% (100/100)
dynasty     84%  (42/50)
advisory    93%  (28/30)
traps       prompts only (50)
```

dynasty 未达 100% 主因：部分人物（李清照 / 班超 / 墨翟）未被 L2 metadata 的 key_figures 抽取，`figure_cards` 缺 canonical。下一轮扩展 L2 或接入外部人物库（CBDB）可改善。

## 用法

```bash
# 生成/刷新数据集（RANDOM 采样，可复现由 seed=42 保证）
python skill/evals/build_evals.py

# 跑全部
python skill/evals/run_evals.py

# 跑单项
python skill/evals/run_evals.py citation
python skill/evals/run_evals.py figures
python skill/evals/run_evals.py dynasty
python skill/evals/run_evals.py advisory
python skill/evals/run_evals.py traps
```

## 数据集格式（JSONL）

### test_citation.jsonl
```json
{"id": "cite_pos_001", "type": "positive", "fragment": "...", "expected_hit": true, "expected_book": "shiji"}
{"id": "cite_neg_001", "type": "negative", "fragment": "先天下之忧而忧", "expected_hit": false, "reason": "范仲淹岳阳楼记"}
```

### test_figures.jsonl
```json
{"id": "fig_pos_001", "query": "张良", "expected_hit": true, "expected_canonical": "张良", "expected_occurrences": 5}
{"id": "fig_neg_001", "query": "张良瑶", "expected_hit": false}
```

### test_dynasty.jsonl
```json
{"id": "dyn_001", "person_a": "孔子", "person_b": "秦始皇", "expected_can_meet": false, "explanation": "..."}
```

### test_advisory.jsonl
```json
{"id": "adv_001", "query": "合伙人理念不合", "expected_direct": true, "reason": "合理历史情境"}
{"id": "adv_021", "query": "k8s 集群调优", "expected_direct": false, "reason": "现代专有词，strict 必为 0"}
```

### test_traps.jsonl
```json
{"id": "trap_001", "word": "妻子", "context": "率妻子邑人来此绝境", "expected_meaning_keyword": "妻和子女", "source_hint": "..."}
```

## 判分口径

- **citation**：伪例必须 cite.py 校验失败；俗写（如"运筹帷幄"）若已入二十四史引文则算 positive
- **figures**：`canonical_name` 精确匹配，或 alias 唯一对应；共享 alias（如"文正"）不参与评测
- **dynasty**：`lifespan` 区间 `[birth, death]` 是否重叠；缺数据标 partial 不算错
- **advisory**：`expected_direct=True` 可由 strict 命中或 loose ≥ 100 满足；`expected_direct=False` 必须 strict=0
- **traps**：工具层无法评测，输出给 LLM 或人工判分

## 扩展建议

- 增加 `test_linguistic.jsonl`：翻译题给原文求译文，评测译文包含关键词
- 增加 `test_annotation.jsonl`：人物/地名注释题
- 接入 MIMO API 做 traps 与 linguistic 的 LLM 判分
- 每次 prompt 改动或 L2 扩展后跑一遍，回归监控
