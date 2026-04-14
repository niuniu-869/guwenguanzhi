# 朝代脉络导读索引

六篇导读覆盖上古至 1912 年，每篇是一张"找得到事件 / 找得到人物"的时间地图，而不是历史叙事。

## 朝代篇

| 文件 | 时段 | 覆盖书目 |
|---|---|---|
| [pre_qin.md](pre_qin.md) | 上古—前221 | shiji 本纪 1-5、世家 1-16、列传 1-26 |
| [qin_han.md](qin_han.md) | 前221—220 | shiji、hanshu、houhanshu、sanguozhi 前段 |
| [wei_jin_nbc.md](wei_jin_nbc.md) | 220—589 | sanguozhi、jinshu、songshu、nanqishu、liangshu、chenshu、weishu、beiqishu、zhoushu、nanshi、beishi |
| [sui_tang.md](sui_tang.md) | 581—907 | suishu、jiutangshu、xintangshu、jiuwudaishi（衔接） |
| [song_yuan.md](song_yuan.md) | 907—1368 | jiuwudaishi、xinwudaishi、songshi、liaoshi、jinshi、yuanshi |
| [ming_qing.md](ming_qing.md) | 1368—1912 | mingshi、qingshigao |

## 跨朝代主题导航

### 变革与改革
- 商鞅变法（前4世纪）`shiji/列传/008`
- 王莽改制（8-23）hanshu 王莽传
- 北魏孝文汉化（471-499）`weishu/帝纪/007`
- 两税法（780）`jiutangshu/本纪/012`
- 王安石熙宁变法（1069-1076）songshi 王安石传
- 张居正改革（1573-1582）`mingshi/列传/101`
- 雍正摊丁入亩（1723 起）qingshigao 世宗纪
- 戊戌变法（1898）`qingshigao/本纪/024`
- 清末新政（1901-1911）`qingshigao/本纪/024-025`

详见 advisory/insights.md 变革条目（11-16）。

### 战争与军事转折
- 巨鹿之战（前207）`shiji/本纪/007` — 士气与决心
- 长平之战（前260）`shiji/列传/013` — 决策与国力
- 漠北决战（前119）`shiji/列传/051` — 主动出击
- 赤壁之战（208）`sanguozhi/魏志/001`、吴志/002 — 联盟与地利
- 淝水之战（383）jinshu 谢安传 — 以少胜多的条件
- 澶渊之盟（1004）`songshi/本纪/006`、`liaoshi/本纪/014` — 和战算账
- 土木堡之变（1449）`mingshi/本纪/010` — 权力真空的风险
- 甲午战争（1894-1895）`qingshigao/本纪/023` — 现代化落差

### 外交与民族关系
- 张骞通西域（前138 起）`shiji/列传/063`
- 汉匈关系全貌 `shiji/列传/050`、hanshu 匈奴传
- 苏武牧羊（前100-前81）hanshu 苏武传
- 唐与突厥/吐蕃 jiutangshu 相关列传
- 宋辽金夏三百年共处 songshi、liaoshi、jinshi 并读
- 郑和下西洋（1405-1433）`mingshi` 郑和传
- 尼布楚条约（1689）`qingshigao/本纪/007`
- 马戛尔尼使团（1793）`qingshigao/本纪/015`

### 思想与文化
- 百家争鸣（前5-前3 世纪）`hanshu/志/010` 艺文志
- 独尊儒术（前134）shiji 儒林列传、hanshu 董仲舒传
- 魏晋玄学、竹林七贤 jinshu 嵇康阮籍传
- 佛教本土化 魏书 释老志、jinshu 相关传
- 宋代理学 songshi 道学传
- 阳明心学 mingshi 王守仁传
- 乾嘉考据 qingshigao 儒林传
- 晚清今文经学与维新 qingshigao 康有为、梁启超传

### 经济与财政
- 盐铁官营（前119 起，前81 盐铁会议）`shiji/书/008` 平准书、hanshu 食货志
- 均田制（485 起）weishu 食货志
- 两税法（780）jiutangshu 食货志
- 交子与商业革命（北宋）songshi 食货志
- 元代宝钞 yuanshi 食货志
- 一条鞭法（1581 全面）mingshi 食货志
- 摊丁入亩（雍正）qingshigao 食货志
- 厘金与晚清财政 qingshigao 食货志

### 权力结构演变
- 分封 → 郡县：秦统一（`shiji/本纪/006`）
- 外戚专权：西汉吕、霍、王氏（hanshu 外戚传）
- 宦官干政：东汉十常侍、唐代仇士良、明代王振、魏忠贤
- 门阀 → 寒门：南朝刘裕（`songshu/本纪/001`）
- 科举取士：隋唐定型到明清僵化（历代选举志）
- 皇权与相权：明废丞相（`mingshi/本纪/003`）→ 内阁票拟 → 清军机处

## 用法建议

1. **准备时间段的对话**：先读本朝代脉络，拿到年表和人物网
2. **准备专题咨询**：先读主题导航，跨朝代归纳现象
3. **确认单个事件**：用 `timeline.py` + `cite.py <URN>` 组合
4. **不确定年代归属**：用 `lookup.py <人物>` 查 canonical_name 和 appearances_json

## 相关文件

- `../figures/_index.md` — 人物档案索引（按朝代）
- `../advisory/insights.md` — 25 条精选咨询案例
- `../advisory/analogy-framework.md` — 类比方法论
- `../advisory/fact-grounding.md` — 引证规范
- `../advisory/uncertainty-labels.md` — 不确定性标签

