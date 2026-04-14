"""二十四史 + 其他典籍的作者/朝代登记表。L2 metadata 生成时填入 prompt。"""

from __future__ import annotations

# book_id → (作者, 朝代, 别名/正式名)
BOOKS: dict[str, dict[str, str]] = {
    # 二十四史
    "shiji":         {"author": "司马迁",        "dynasty": "西汉", "name": "史记"},
    "hanshu":        {"author": "班固",          "dynasty": "东汉", "name": "汉书"},
    "houhanshu":     {"author": "范晔",          "dynasty": "南朝宋", "name": "后汉书"},
    "sanguozhi":     {"author": "陈寿",          "dynasty": "西晋", "name": "三国志"},
    "jinshu":        {"author": "房玄龄等",      "dynasty": "唐",   "name": "晋书"},
    "songshu":       {"author": "沈约",          "dynasty": "南朝梁", "name": "宋书"},
    "nanqishu":      {"author": "萧子显",        "dynasty": "南朝梁", "name": "南齐书"},
    "liangshu":      {"author": "姚思廉",        "dynasty": "唐",   "name": "梁书"},
    "chenshu":       {"author": "姚思廉",        "dynasty": "唐",   "name": "陈书"},
    "weishu":        {"author": "魏收",          "dynasty": "北齐", "name": "魏书"},
    "beiqishu":      {"author": "李百药",        "dynasty": "唐",   "name": "北齐书"},
    "zhoushu":       {"author": "令狐德棻等",    "dynasty": "唐",   "name": "周书"},
    "suishu":        {"author": "魏徵等",        "dynasty": "唐",   "name": "隋书"},
    "nanshi":        {"author": "李延寿",        "dynasty": "唐",   "name": "南史"},
    "beishi":        {"author": "李延寿",        "dynasty": "唐",   "name": "北史"},
    "jiutangshu":    {"author": "刘昫等",        "dynasty": "后晋", "name": "旧唐书"},
    "xintangshu":    {"author": "欧阳修、宋祁",  "dynasty": "北宋", "name": "新唐书"},
    "jiuwudaishi":   {"author": "薛居正等",      "dynasty": "北宋", "name": "旧五代史"},
    "xinwudaishi":   {"author": "欧阳修",        "dynasty": "北宋", "name": "新五代史"},
    "songshi":       {"author": "脱脱等",        "dynasty": "元",   "name": "宋史"},
    "liaoshi":       {"author": "脱脱等",        "dynasty": "元",   "name": "辽史"},
    "jinshi":        {"author": "脱脱等",        "dynasty": "元",   "name": "金史"},  # 金代之金史
    "yuanshi":       {"author": "宋濂等",        "dynasty": "明",   "name": "元史"},
    "mingshi":       {"author": "张廷玉等",      "dynasty": "清",   "name": "明史"},
    "qingshigao":    {"author": "赵尔巽等",      "dynasty": "民国", "name": "清史稿"},
}


def get_book_meta(book_id: str, fallback_name: str = "") -> dict[str, str]:
    """获取书目元信息；不在登记表则返回 fallback。"""
    if book_id in BOOKS:
        return BOOKS[book_id]
    return {"author": "未详", "dynasty": "未详", "name": fallback_name or book_id}
