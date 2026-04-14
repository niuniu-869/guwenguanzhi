# references/ 索引

> Agent 按需加载的知识库。每篇独立，互相交叉引用。

## 四大子集

### [`advisory/`](advisory/) — 历史咨询（差异化核心）
- [`analogy-framework.md`](advisory/analogy-framework.md) — 类比思维 4 步法，不能做的事清单
- [`fact-grounding.md`](advisory/fact-grounding.md) — 史实核查流程（防幻觉）
- [`uncertainty-labels.md`](advisory/uncertainty-labels.md) — **【史实】/【演绎】/【推断·建议】三标签规范**
- [`insights.md`](advisory/insights.md) — 25 条精选案例，带 URN / 模式 / 现代情境模板

### [`linguistic/`](linguistic/) — 古汉语方法论
- [`reading-classical.md`](linguistic/reading-classical.md) — 断句、省略、语序的阅读三步法
- [`translation-principles.md`](linguistic/translation-principles.md) — 信达雅；逐词→补省→调序→润色
- [`common-traps.md`](linguistic/common-traps.md) — 古今异义清单 + 多义字 + 词类活用
- [`annotation-guide.md`](linguistic/annotation-guide.md) — 四层注释 + 场景选择
- [`citation-format.md`](linguistic/citation-format.md) — 引用规范 + 常见错误

### [`classics/`](classics/) — 典籍导读
（Stage 4.2 填充：24 本典籍的"怎么读"，非原文）

### [`history/`](history/) — 朝代脉络
（Stage 4.2 填充：6 篇朝代史 + 典章制度）

### [`figures/`](figures/) — 人物档案
（Stage 4.2 填充：按朝代分文件；当前通过 `lookup.py` 查 metadata.sqlite 即时获取）

## 如何选择读哪篇（决策树）

- **用户要读/译古文** → 先看 `linguistic/reading-classical` 和 `common-traps`
- **用户要引用原文** → `linguistic/citation-format` + `scripts/cite.py`
- **用户要历史建议** → `advisory/analogy-framework` + `insights`，输出时走 `advisory/uncertainty-labels` 的三标签
- **用户问人物/地名/事件** → `scripts/lookup.py` / `scripts/timeline.py`，不直接回忆

## 硬性规范（所有文档共同）

- 每引用都能通过 `cite.py` 校验，否则删除
- 使用 URN 格式 `book_id/(sub_type|juan)/index`
- 禁用"据说/相传/大约"模糊措辞
- 历史咨询三标签：【史实】/【演绎】/【推断·建议】

## Stage 4.2 Roadmap

- `classics/` 24 本：shiji / hanshu / sanguozhi / ... / 论语 / 孟子 / 资治通鉴 / 古文观止
- `history/`：pre-qin / han / wei-jin-nbc / sui-tang / song-yuan / ming-qing
- `figures/`：按朝代合并从 `figure_cards` 的核心人物（500+ 主传人物）
