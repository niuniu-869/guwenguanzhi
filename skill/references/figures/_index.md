# 人物档案索引

按朝代归档 figure_cards 中出现较多的人物，每份档案含：别名、生卒、主要出处 URN、角色标签。完整查询用 `lookup.py <名字>`。

## 分档

| 文件 | 时段 | 对应史书 |
|---|---|---|
| [pre_qin.md](pre_qin.md) | 上古—前221 | shiji 世家 1-16、列传 1-26 |
| [qin_han.md](qin_han.md) | 前221—220 | shiji、hanshu、houhanshu、sanguozhi 前段 |
| [wei_jin_nbc.md](wei_jin_nbc.md) | 220—589 | sanguozhi、jinshu、南朝五史、北朝四史、南北史 |
| [sui_tang.md](sui_tang.md) | 581—907 | suishu、jiutangshu、xintangshu、五代二史 |
| [song_yuan.md](song_yuan.md) | 907—1368 | songshi、liaoshi、jinshi、yuanshi |
| [ming_qing.md](ming_qing.md) | 1368—1912 | mingshi、qingshigao |

## 使用建议

1. **查人物找卷**：按朝代篇进入，Ctrl-F 搜名字，看 URN
2. **查别名归一**：用 `lookup.py <别名>`，返回 canonical_name
3. **查出现频次**：figure_cards 里 `occurrences` 高的优先关注
4. **查跨朝代长线影响**：如孔子、汉武帝在十多本史书被引，须按 appearances_json 追踪

## canonical_name 约定

- 帝王用庙号或"某帝"（如唐太宗、汉武帝、宋神宗、乾隆帝）
- 臣子用习惯单名（如张良、魏征、王安石、张居正）
- 个别用字号（如诸葛亮、司马迁）
- 别名见 aliases_json（如刘邦包括"汉高祖/沛公/刘季"）

## 选择原则

每档列入人物标准：
1. `figure_cards.occurrences ≥ 5`（朝代主要人物）或
2. 在对应朝代导读的时间轴/分期中已被点名，即使 occurrences 较低
3. 女性人物即便频次低也单列（信息密度价值）

完整人物表 12175 条见 `data/metadata.sqlite` 的 `figure_cards` 表。
