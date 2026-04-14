#!/usr/bin/env python3
"""evals 数据集生成器。

从 corpus.sqlite 和 metadata.sqlite 采样真实案例，组合手工伪例 → 5 个 JSONL。

输出：
  skill/evals/test_citation.jsonl     100 条（50 真 + 50 伪）
  skill/evals/test_figures.jsonl      100 条（70 真 + 30 伪）
  skill/evals/test_dynasty.jsonl       50 条（时序推理）
  skill/evals/test_traps.jsonl         50 条（古今异义）
  skill/evals/test_advisory.jsonl      30 条（现代情境）
"""

from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path

random.seed(42)  # 可复现
EVAL_DIR = Path(__file__).resolve().parent
SKILL_ROOT = EVAL_DIR.parent
CORPUS = SKILL_ROOT / "data" / "corpus.sqlite"
META = SKILL_ROOT / "data" / "metadata.sqlite"


def write_jsonl(path: Path, items: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"✅ 写入 {path.name}: {len(items)} 条")


# ----------------- citation 100 条 -----------------

# 伪例集：以下都是"非二十四史原文"——近代诗词、杜撰、成语。
# 注意：诸子原文（论语/孟子）可能在二十四史传文中被引用，故不列入伪例。
FAKE_CITATIONS = [
    "不忘初心方得始终",
    "人生若只如初见",
    "海内存知己天涯若比邻",
    "落霞与孤鹜齐飞",
    "路漫漫其修远兮吾将上下而求索",
    "安能摧眉折腰事权贵使我不得开心颜",
    "山重水复疑无路柳暗花明又一村",
    "君不见黄河之水天上来奔流到海不复回",
    "一万年太久只争朝夕",
    "独立寒秋湘江北去",
    "大江东去浪淘尽千古风流人物",
    "山不在高有仙则名",
    "时光如水岁月如歌",
    "人心齐泰山移",
    "先天下之忧而忧后天下之乐而乐",  # 范仲淹岳阳楼记
    "读书破万卷下笔如有神",  # 杜甫
    "会当凌绝顶一览众山小",  # 杜甫
    "粉身碎骨浑不怕要留清白在人间",  # 于谦
    "明月几时有把酒问青天",  # 苏轼
    "但愿人长久千里共婵娟",  # 苏轼
    "不以物喜不以己悲",  # 范仲淹
    "静以修身俭以养德",  # 诸葛亮诫子书（非史）
    "千磨万击还坚劲任尔东西南北风",  # 郑板桥
    "采菊东篱下悠然见南山",  # 陶渊明
    "长风破浪会有时直挂云帆济沧海",  # 李白
    "天生我材必有用千金散尽还复来",  # 李白
    "两岸猿声啼不住轻舟已过万重山",  # 李白
    "春蚕到死丝方尽蜡炬成灰泪始干",  # 李商隐
    "无可奈何花落去似曾相识燕归来",  # 晏殊
    "为天地立心为生民立命为往圣继绝学为万世开太平",  # 张载
    "横眉冷对千夫指俯首甘为孺子牛",  # 鲁迅
    "问世间情为何物直教生死相许",  # 元好问
    "醉卧沙场君莫笑古来征战几人回",  # 王翰
    "宁可枝头抱香死何曾吹落北风中",  # 郑思肖
    "苟利国家生死以岂因祸福避趋之",  # 林则徐
    "粪土当年万户侯",  # 毛泽东
    "数风流人物还看今朝",  # 毛泽东
    "雄关漫道真如铁而今迈步从头越",  # 毛泽东
    "孔子曰吾有三宝",  # 伪托（"三宝"是老子）
    "诸葛亮云鞠躬尽瘁死而后已",  # 后出师表用"尽力"
    "范仲淹言天下兴亡匹夫有责",  # 伪托（顾炎武）
    "苏轼云天下兴亡匹夫有责",  # 伪托
    "庄子曰逍遥于天地之间心意自得",  # 拼凑
    "老子曰道可道非常道名可名非常名道法自然无为而无不为",  # 拼凑老子两段
    "只要功夫深铁杵磨成针",  # 谚语，非二十四史
    "三天打鱼两天晒网",  # 现代俗语
    "人法地地法天天法道道法自然",  # 老子
    "宇宙浩瀚人生如梦当及时行乐",  # 纯杜撰
    "风雨之夜最宜饮酒读书品茶",  # 纯杜撰
    "少年不识愁滋味爱上层楼",  # 辛弃疾
    "三更灯火五更鸡正是男儿读书时",  # 颜真卿《劝学》
    "黑发不知勤学早白首方悔读书迟",  # 颜真卿《劝学》
    "两情若是久长时又岂在朝朝暮暮",  # 秦观《鹊桥仙》
]


def build_citation(conn_corpus: sqlite3.Connection) -> list[dict]:
    items: list[dict] = []
    # 50 正例：从 corpus 采样有意义长度的段落片段
    rows = conn_corpus.execute(
        "SELECT book_id, book_name, juan, segment, sub_type, sub_index, text "
        "FROM documents WHERE LENGTH(text) > 60 AND LENGTH(text) < 400 "
        "ORDER BY RANDOM() LIMIT 300"
    ).fetchall()
    positives = 0
    seen_keys = set()
    for r in rows:
        if positives >= 50:
            break
        text = r["text"]
        # 取中间片段 15-25 字
        if len(text) < 30:
            continue
        start = random.randint(0, max(0, len(text) - 25))
        frag = text[start:start + random.randint(15, 22)]
        # 过滤含书名号/括号/标点过多的片段
        if any(c in frag for c in "《》【】〔〕（）()[]"):
            continue
        if sum(1 for c in frag if c in "，。；：、？！") > 2:
            continue
        key = frag[:8]
        if key in seen_keys:
            continue
        seen_keys.add(key)
        positives += 1
        items.append({
            "id": f"cite_pos_{positives:03d}",
            "type": "positive",
            "prompt": f"校验：'{frag}' 出自哪里？",
            "fragment": frag,
            "expected_hit": True,
            "expected_book": r["book_id"],
        })

    # 50 伪例
    for i, fake in enumerate(FAKE_CITATIONS[:50], 1):
        items.append({
            "id": f"cite_neg_{i:03d}",
            "type": "negative",
            "prompt": f"校验：'{fake}' 出自哪里？",
            "fragment": fake,
            "expected_hit": False,
            "reason": "非二十四史原文 / 俗写 / 伪托",
        })
    return items


# ----------------- figures 100 条 -----------------

FAKE_FIGURES = [
    "张良瑶", "李世明", "岳武穆康", "司马光辉", "韩信卿",
    "诸葛明亮", "曹孟操", "刘玄德备", "孙仲谋权", "周公瑾瑜",
    "杜少陵甫", "李青莲白", "范文正淹", "王安右石", "朱熹理",
    "王阳心明", "顾亭炎武", "黄宗羲之", "梁启任超", "康有伟为",
    "孔丘子", "孟子轲", "老聃子", "庄子周", "墨翟子",
    "秦始皇政", "汉武彻帝", "唐太民宗", "宋真赵恒", "明太璋祖",
]


def build_figures(conn_meta: sqlite3.Connection) -> list[dict]:
    items: list[dict] = []
    # 预先统计：哪些 alias 对应 >1 个 canonical_name（共享别名不可用）
    all_rows = conn_meta.execute(
        "SELECT canonical_name, aliases_json FROM figure_cards"
    ).fetchall()
    alias_counts: dict[str, int] = {}
    for r in all_rows:
        for a in json.loads(r["aliases_json"] or "[]"):
            alias_counts[a] = alias_counts.get(a, 0) + 1
    # 70 正例：从 figure_cards 采样 occurrences ≥3 的
    rows = conn_meta.execute(
        "SELECT canonical_name, aliases_json, lifespan, occurrences, appearances_json "
        "FROM figure_cards WHERE occurrences >= 3 ORDER BY RANDOM() LIMIT 120"
    ).fetchall()
    count = 0
    for r in rows:
        if count >= 70:
            break
        aliases = json.loads(r["aliases_json"] or "[]")
        apps = json.loads(r["appearances_json"] or "[]")
        # 过滤：alias 长度 ≥ 2，且未被多个 canonical 共享
        unique_aliases = [
            a for a in aliases
            if len(a) >= 2 and alias_counts.get(a, 0) == 1
        ]
        query_candidates = [r["canonical_name"]] + unique_aliases
        query_name = random.choice(query_candidates)
        count += 1
        items.append({
            "id": f"fig_pos_{count:03d}",
            "type": "positive",
            "prompt": f"查人物：{query_name}",
            "query": query_name,
            "expected_hit": True,
            "expected_canonical": r["canonical_name"],
            "expected_occurrences": r["occurrences"],
            "expected_books": sorted({a.get("book") for a in apps if a.get("book")}),
        })
    # 30 伪例
    for i, fake in enumerate(FAKE_FIGURES[:30], 1):
        items.append({
            "id": f"fig_neg_{i:03d}",
            "type": "negative",
            "prompt": f"查人物：{fake}",
            "query": fake,
            "expected_hit": False,
            "reason": "虚构或错别字人名",
        })
    return items


# ----------------- dynasty 50 条（时序） -----------------

# 格式：(personA, personB, can_meet, 解释)
# lifespan 都能从 figure_cards 查，这里硬编码便于审校
DYNASTY_CASES = [
    ("孔子", "秦始皇", False, "孔子卒前479，秦始皇生前259，相隔 220 年"),
    ("刘邦", "司马迁", False, "刘邦卒前195 早于司马迁生前145"),
    ("诸葛亮", "司马懿", True,  "均为三国时期"),
    ("李白", "杜甫", True, "同为盛唐诗人，曾相见"),
    ("王安石", "苏轼", True, "同为北宋中期"),
    ("岳飞", "秦桧", True, "同为南宋初期"),
    ("曹操", "李世民", False, "曹操卒220，李世民生599"),
    ("项羽", "刘邦", True, "楚汉之争同代"),
    ("班固", "司马光", False, "班固东汉，司马光北宋，相隔近千年"),
    ("孔子", "孟子", False, "孔子卒前479，孟子生前372"),
    ("韩愈", "柳宗元", True, "同为中唐古文运动"),
    ("欧阳修", "王安石", True, "同为北宋中期"),
    ("朱熹", "陆九渊", True, "南宋同期理学家"),
    ("王阳明", "朱熹", False, "朱熹卒1200，王阳明生1472"),
    ("张良", "诸葛亮", False, "张良汉初，诸葛亮三国，隔400年"),
    ("秦始皇", "汉武帝", False, "秦始皇卒前210，汉武帝生前156"),
    ("汉武帝", "霍去病", True, "君臣同代"),
    ("唐玄宗", "杨贵妃", True, "君臣/君妃同代"),
    ("安禄山", "李白", True, "安史之乱时李白在世"),
    ("成吉思汗", "忽必烈", True, "祖孙"),
    ("朱元璋", "朱棣", True, "父子"),
    ("玄烨", "雍正", True, "父子"),
    ("戚继光", "张居正", True, "明中期同代"),
    ("李世民", "武则天", True, "武则天为李世民才人，后为李治皇后"),
    ("王莽", "刘歆", True, "王莽与刘歆（光武族兄）同代"),
    ("项羽", "韩信", True, "楚汉之争同代"),
    ("范仲淹", "司马光", True, "北宋同期"),
    ("曾国藩", "左宗棠", True, "晚清同代"),
    ("孙武", "孔子", True, "春秋末同代"),
    ("墨翟", "孔丘", False, "墨子生前468，孔子卒前479（略有异说；figure_cards 可能缺）"),
    ("屈原", "秦始皇", False, "屈原卒前278 早于秦始皇生前259"),
    ("蔺相如", "廉颇", True, "战国赵将同代"),
    ("韩非", "李斯", True, "同为荀子弟子"),
    ("司马懿", "曹操", True, "司马懿在曹操幕府"),
    ("关羽", "张飞", True, "三国同代"),
    ("郭嘉", "诸葛亮", True, "郭嘉生170卒207，诸葛亮生181，活期部分交叠"),
    ("王安石", "岳飞", False, "王安石卒1086，岳飞生1103"),
    ("欧阳修", "朱熹", False, "欧阳修卒1072，朱熹生1130"),
    ("霍去病", "霍光", True, "异母兄弟"),
    ("贾谊", "司马相如", True, "西汉同代"),
    ("班超", "班固", True, "兄弟"),
    ("韩信", "萧何", True, "同为汉初功臣"),
    ("陆游", "辛弃疾", True, "同为南宋中期"),
    ("李清照", "辛弃疾", True, "南宋同代"),
    ("郑成功", "康熙", True, "郑成功卒1662，康熙继位1661"),
    ("张居正", "戚继光", True, "同为明万历初年"),
    ("海瑞", "张居正", True, "同为明中晚期"),
    ("孔子", "老子", True, "据传孔子曾问礼于老子"),
    ("郦食其", "刘邦", True, "楚汉同代"),
    ("董仲舒", "司马迁", True, "同为汉武帝朝"),
]


def build_dynasty() -> list[dict]:
    items: list[dict] = []
    for i, (a, b, can_meet, explain) in enumerate(DYNASTY_CASES[:50], 1):
        items.append({
            "id": f"dyn_{i:03d}",
            "prompt": f"{a} 和 {b} 有可能见过面吗？",
            "person_a": a,
            "person_b": b,
            "expected_can_meet": can_meet,
            "explanation": explain,
        })
    return items


# ----------------- traps 50 条（古今异义） -----------------

TRAPS = [
    ("妻子", "妻子邑人", "妻和子女（不是配偶）", "率妻子邑人来此绝境"),
    ("走", "夸父与日逐走", "跑（不是走路）", "夸父与日逐走"),
    ("涕", "临表涕零", "眼泪（不是鼻涕）", "临表涕零"),
    ("去", "西蜀之去南海", "距离（不是前往）", "西蜀之去南海"),
    ("行李", "行李之往来", "外交使节（不是旅行物品）", "行李之往来共其乏困"),
    ("交通", "阡陌交通", "交错相通（不是运输）", "阡陌交通"),
    ("绝境", "来此绝境", "与世隔绝之地（不是困境）", "来此绝境"),
    ("鲜美", "芳草鲜美", "鲜艳美丽（不是味美）", "芳草鲜美"),
    ("牺牲", "牺牲玉帛", "祭祀牲畜（不是捐躯）", "牺牲玉帛弗敢加也"),
    ("烈士", "烈士暮年", "有节操的人（不是战争牺牲者）", "烈士暮年壮心不已"),
    ("卑鄙", "先帝不以臣卑鄙", "身份低微（不是道德败坏）", "先帝不以臣卑鄙"),
    ("可以", "忠之属也可以一战", "可以凭借（不是可能）", "忠之属也可以一战"),
    ("地方", "地方百里", "土地方圆（不是区域）", "地方百里而可以王"),
    ("感激", "由是感激", "感慨激奋（不是感谢）", "由是感激遂许先帝以驱驰"),
    ("然后", "然后知生于忧患", "这样以后（不是接着）", "然后知生于忧患而死于安乐也"),
    ("其实", "叶徒相似其实味不同", "它的果实（不是实际上）", "叶徒相似其实味不同"),
    ("形容", "形容枯槁", "形体容貌（不是描述）", "形容枯槁"),
    ("指示", "请指示王", "指出给看（不是命令）", "璧有瑕请指示王"),
    ("以为", "以为桂林象郡", "把...当作（不是认为）", "以为桂林象郡"),
    ("殷勤", "致殷勤之意", "诚恳恳切（不是热情招待）", "致殷勤之意"),
    ("慷慨", "慷慨悲歌", "感慨悲叹（不是大方）", "慷慨悲歌"),
    ("博学", "博学而笃志", "广泛学习（不是学问渊博）", "博学而笃志"),
    ("假", "以是人多以书假余", "借（不是虚假）", "以是人多以书假余"),
    ("中国", "复会诸侯于东都", "中原（不是国家名）", "中国而振四夷"),
    ("风流", "数风流人物", "有才华（古义为『风度』）", "数风流人物"),
    ("丈夫", "生丈夫二壶酒一犬", "成年男子（不是配偶）", "生丈夫二壶酒一犬"),
    ("独立", "赵军独立", "独自站立（不是不依附）", "赵军独立"),
    ("交代", "冬夏交代", "交替（不是吩咐）", "冬夏交代"),
    ("往往", "山水之间往往有焉", "到处/常常（不是单纯『经常』）", "山水之间往往有焉"),
    ("师", "吾从而师之", "以...为师（意动）", "吾从而师之"),
    ("军", "沛公军霸上", "驻军（名词作动词）", "沛公军霸上"),
    ("活", "项伯杀人臣活之", "使...活（使动）", "项伯杀人臣活之"),
    ("死", "等死死国可乎", "为...而死（为动）", "等死死国可乎"),
    ("坚", "将军身披坚执锐", "坚硬的铠甲（形作名）", "将军身披坚执锐"),
    ("斗折", "斗折蛇行", "像北斗那样（名词作状语）", "斗折蛇行"),
    ("见", "信而见疑", "被（被动句标志）", "信而见疑"),
    ("于", "不拘于时", "被（被动句标志）", "不拘于时"),
    ("何陋之有", "何陋之有", "宾语前置（有何陋）", "何陋之有"),
    ("不余欺也", "古之人不余欺也", "宾语前置（不欺余）", "古之人不余欺也"),
    ("唯...是...", "唯利是图", "宾语前置（唯图利）", "唯利是图"),
    ("何操", "大王来何操", "宾语前置（操何）", "大王来何操"),
    ("尔", "毋吾以也", "用我（宾语前置）", "毋吾以也"),
    ("布衣", "臣本布衣", "平民（身份代称）", "臣本布衣躬耕于南阳"),
    ("黔首", "黔首", "百姓（秦称）", "更名民曰黔首"),
    ("股", "股肱", "大腿（不是屁股）", "股肱之臣"),
    ("嫁", "嫁祸", "转移（不是婚嫁）", "嫁祸于人"),
    ("揭", "揭竿为旗", "高举（不是揭开）", "斩木为兵揭竿为旗"),
    ("股栗", "不寒而栗", "颤抖（古今同义，但易误）", "不寒而栗"),
    ("购", "购求", "悬赏（不是购买）", "重币购求之"),
    ("再", "一鼓作气再而衰", "第二次（不是『又』）", "一鼓作气再而衰三而竭"),
]


def build_traps() -> list[dict]:
    items: list[dict] = []
    for i, (word, context, correct_meaning, source) in enumerate(TRAPS[:50], 1):
        items.append({
            "id": f"trap_{i:03d}",
            "prompt": f"古文『{context}』中 '{word}' 的古义是什么？",
            "word": word,
            "context": context,
            "expected_meaning_keyword": correct_meaning,
            "source_hint": source,
        })
    return items


# ----------------- advisory 30 条（现代情境） -----------------

ADVISORY = [
    # 合理情境（expected_direct=True 代表应有 strict 命中或 loose ≥30）
    ("合伙人理念不合", True),
    ("空降 CEO 如何建立权威", True),
    ("创业初期如何用人", True),
    ("接班人选择", True),
    ("变法改革的阻力管理", True),
    ("功高震主的自保", True),
    ("新官上任如何烧好三把火", True),
    ("团队核心成员叛变", True),
    ("权力交接", True),
    ("君臣信任建立", True),
    ("如何进谏", True),
    ("异见管理", True),
    ("用人之疑", True),
    ("危机公关", True),
    ("决策失误后的止损", True),
    ("跨文化管理", True),
    ("外交谈判", True),
    ("军事与政治的平衡", True),
    ("技术革新的阻力", True),
    ("任期末的安排", True),
    # 明显无直接对应（strict 必须为 0；agent 应标【推断·建议】）
    ("k8s 集群调优", False),
    ("React 组件的最佳实践", False),
    ("DeFi 流动性挖矿", False),
    ("prompt engineering", False),
    ("短视频运营策略", False),
    ("跨境电商 SaaS 选品", False),
    ("A/B 测试方法论", False),
    ("云原生架构设计", False),
    ("TikTok 算法推荐", False),
    ("美容护肤的成分学", False),
]


def build_advisory() -> list[dict]:
    """advisory 评测：召回能力 + strict 与 loose 分离。
    - expected_direct=True：query 应能通过 strict(严格) 命中，或 loose 明显大量命中
    - expected_direct=False：query 中含现代专有名词，strict 必须为 0（验证不会杜撰先例）
    """
    items: list[dict] = []
    for i, (query, expected) in enumerate(ADVISORY[:30], 1):
        items.append({
            "id": f"adv_{i:03d}",
            "prompt": query,
            "query": query,
            "expected_direct": expected,
            "reason": "合理历史情境" if expected else "现代专有词，strict 必为 0",
        })
    return items


def main() -> None:
    if not CORPUS.exists() or not META.exists():
        raise SystemExit("需要先构建 corpus.sqlite 和 metadata.sqlite")

    conn_corpus = sqlite3.connect(CORPUS)
    conn_corpus.row_factory = sqlite3.Row
    conn_meta = sqlite3.connect(META)
    conn_meta.row_factory = sqlite3.Row

    try:
        write_jsonl(EVAL_DIR / "test_citation.jsonl", build_citation(conn_corpus))
        write_jsonl(EVAL_DIR / "test_figures.jsonl", build_figures(conn_meta))
        write_jsonl(EVAL_DIR / "test_dynasty.jsonl", build_dynasty())
        write_jsonl(EVAL_DIR / "test_traps.jsonl", build_traps())
        write_jsonl(EVAL_DIR / "test_advisory.jsonl", build_advisory())
    finally:
        conn_corpus.close()
        conn_meta.close()


if __name__ == "__main__":
    main()
