## 任务

对以下句子进行**逐词注释**。

**文献**：{title}（{author}）
**段落上下文**：
{paragraph}

**待注释句子**：
{sentences_block}

---

{{include: rules/word_annotation_rules.md}}

---

## 输出格式（必须严格遵守）

```json
{
  "sentences": [
    {
      "original": "原文句子（与输入完全一致）",
      "words": [
        {
          "word": "词组原文",
          "pinyin": "拼音（多音节空格分隔，如 'zhèng wǔ gōng'）",
          "meaning": "具体释义（遵循 R3-R11 各项要求）",
          "type": "实词|虚词|人名|地名|官职|典故（六选一）",
          "highlight": "ancient_today|loan|polyphone|rare|fixed（五选一，或省略/null）"
        }
      ]
    }
  ]
}
```

## 必须输出（最终自检）

- [ ] `sentences` 数组长度等于输入句子数
- [ ] 每个 `words` 数组**非空**，逐词覆盖原文
- [ ] `type` 全部在 6 种枚举内
- [ ] 多音字、通假字、古今异义、罕用义、固定结构 按 §R4-R7、§R11 格式标注并设 `highlight`
- [ ] `highlight` 只出现 5 种合法值或省略（见 §R13）
- [ ] 纯 JSON 输出，无 markdown 代码块
