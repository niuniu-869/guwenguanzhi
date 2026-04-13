## 任务

翻译以下段落（第 {para_idx}/{total} 段）。

**文献**：{title}（{author}）

**上下文参考**（理解人物关系/前后文）：
{context}

**待翻译段落**：
---
{paragraph}
---

---

{{include: rules/translation_rules.md}}

---

## 输出格式

```json
{
  "paragraph_translation": "整段的白话翻译（流畅自然，符合 T1-T2）",
  "sentences": [
    {
      "original": "原文句子（与输入完全一致）",
      "translation": "该句的白话翻译"
    }
  ]
}
```

## 必须输出（最终自检）

- [ ] `paragraph_translation` 非空
- [ ] `sentences` 按语义切分，每句都有 `original` 和 `translation`
- [ ] 古今异义词已按古义翻译（§T3）
- [ ] 翻译与词注释将保持语义一致（§T4）
- [ ] 不含任何评注（§T7）
- [ ] 纯 JSON 输出
