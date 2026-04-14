#!/usr/bin/env python3
"""构建 L1 底本层全文检索库 skill/data/corpus.sqlite

来源：
  - skill/vendor/daizhige/史藏/正史/*.txt   (二十四史底本，主源)
  - skill/vendor/ancientdoc-cc0/             (CC0 字节古籍，v2 集成)

产出：SQLite FTS5 全文索引，每行一段原文，URN = <book_id>/<juan:03d>/<seg:03d>

用法：
    python skill/scripts/build_corpus.py           # 增量（已入库书目跳过）
    python skill/scripts/build_corpus.py --rebuild # 清表重建
    python skill/scripts/build_corpus.py --book shiji  # 只构建指定书目
    python skill/scripts/build_corpus.py --inspect 史记.txt  # 检查单文件解析

使用 trigram 分词器，对中文短语查询友好（SQLite 3.34+）。
原文繁简统一为简体（opencc t2s）。
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# 第三方
try:
    from opencc import OpenCC
except ImportError:
    print("[fatal] 缺少 opencc-python-reimplemented，请 pip install", file=sys.stderr)
    sys.exit(1)

# 复用 _corpus 的 bigram 工具
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _corpus import to_bigrams  # noqa: E402

# --------- 路径 ---------

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
VENDOR_DIR = SKILL_ROOT / "vendor"
DATA_DIR = SKILL_ROOT / "data"
CORPUS_DB = DATA_DIR / "corpus.sqlite"

DAIZHIGE_ZHENGSHI = VENDOR_DIR / "daizhige" / "史藏" / "正史"

# --------- 书目映射 ---------
# daizhige 文件名（繁体）→ 我们的 book_id（英文蛇形）
# 以二十四史优先；三家注 / 史评 / 补注单独识别
BOOK_ID_MAP: dict[str, str] = {
    # 二十四史
    "史記": "shiji",
    "史记": "shiji",
    "漢書": "hanshu",
    "汉书": "hanshu",
    "後漢書": "houhanshu",
    "后汉书": "houhanshu",
    "三國志": "sanguozhi",
    "三国志": "sanguozhi",
    "晉書": "jinshu",
    "晋书": "jinshu",
    "宋書": "songshu",  # 沈约
    "宋书": "songshu",
    "南齊書": "nanqishu",
    "南齐书": "nanqishu",
    "梁書": "liangshu",
    "梁书": "liangshu",
    "陳書": "chenshu",
    "陈书": "chenshu",
    "魏書": "weishu",
    "魏书": "weishu",
    "北齊書": "beiqishu",
    "北齐书": "beiqishu",
    "周書": "zhoushu",
    "周书": "zhoushu",
    "隋書": "suishu",
    "隋书": "suishu",
    "南史": "nanshi",
    "北史": "beishi",
    "舊唐書": "jiutangshu",
    "旧唐书": "jiutangshu",
    "新唐書": "xintangshu",
    "新唐书": "xintangshu",
    "舊五代史": "jiuwudaishi",
    "旧五代史": "jiuwudaishi",
    "新五代史": "xinwudaishi",
    "新五代史": "xinwudaishi",
    "宋史": "songshi",
    "遼史": "liaoshi",
    "辽史": "liaoshi",
    "金史": "jinshi",
    "元史": "yuanshi",
    "明史": "mingshi",
    # 虽非严格二十四史，但常见附带
    "清史稿": "qingshigao",
    # 三家注（合入对应正史作为 commentary）
    "史記正義": "shiji_zhengyi",
    "史记正义": "shiji_zhengyi",
    "史記索隱": "shiji_suoyin",
    "史记索隐": "shiji_suoyin",
    "史記集解": "shiji_jijie",
    "史记集解": "shiji_jijie",
}

# --------- 正则：分卷 ---------
# daizhige 原文卷标识有两类常见格式：
#   A. 行首"卷X"或"◎卷X"：史记、汉书、元史等小书常见
#      例： "卷一 五帝本纪第一"
#   B. 紧跟书名的"<书名>卷X 体裁词"：宋史、明史、清史稿等大书常见
#      例： "宋史卷四百七十一　　列传第二百三十"  (无换行，贴上一卷末)
# 用 OR 模式同时匹配。命中后用 group(1) or group(2) 取卷号。
JUAN_PATTERN = re.compile(
    r"(?:"
    # Pattern A
    r"(?:^|\n)\s*(?:◎|◆|★)?\s*(?:第)?卷\s*"
    r"([一二三四五六七八九十百千零〇○0-9]+)"
    r"\s*[^\n]{0,30}(?=\n)"
    r"|"
    # Pattern B：紧跟书名（1-4 汉字）的卷号 + 体裁词
    r"[\u4e00-\u9fff]{1,4}卷\s*"
    r"([一二三四五六七八九十百千零〇○0-9]+)"
    r"\s*[\u3000 ]+"
    r"(?:本紀|列傳|世家|志|表|本纪|列传|記|记|傳)"
    r")"
)

# --------- 正则：体裁分卷（Pattern C）---------
# OpenCC t2s 后已统一简体。匹配"<体裁>[第]<序号>"作为体裁内分卷标识。
# 史记的"书"如《天官书》《封禅书》；汉书以后改"志"如《五行志》。
# Pattern C 仅用于"卷X"标识缺失的大书（宋史/明史/清史稿/旧唐书/新唐书等）的兜底分卷。
# "第"可选：清史稿写"本纪一"、周书写"帝纪第一"；统一兼容。
# 要求前有换行/段首锚定，避免正文嵌入的"本书卷二十六 / 阅卷三日"等误命中。
# 两个子模式 OR：(a) 带"第"（shiji/hanshu 等严谨）；(b) 行首 + 无"第"（清史稿等）
SUBTYPE_PATTERN = re.compile(
    r"(?:"
    r"(本纪|列传|世家|志|表|书|帝纪)第([一二三四五六七八九十百千零〇○0-9]+)"
    r"|"
    r"(?:^|\n)[\s\u3000]*"
    r"(本纪|列传|世家|志|表|帝纪)"
    r"([一二三四五六七八九十百千零〇○0-9]+)"
    r"(?=[\s\u3000]|$)"
    r")"
)
# Pattern D：三国志专属的"魏志卷X/蜀志卷X/吴志卷X"
ZHI_VOLUME_PATTERN = re.compile(
    r"(?:^|\n)\s*(魏志|蜀志|吴志|蜀书|吴书|魏书)卷\s*"
    r"([一二三四五六七八九十百千零〇○0-9]+)"
    r"(?:\s+[^\n]{0,30})?(?=\n)"
)
# 已识别的体裁集合，用于从 juan_name 反推 sub_type
SUBTYPES = ("本纪", "列传", "世家", "志", "表", "书", "帝纪")

# --------- 中文数字转阿拉伯 ---------
_CN_NUM = {
    "零": 0, "〇": 0, "○": 0,
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9,
    "十": 10, "百": 100, "千": 1000,
}

def cn_to_int(s: str) -> int | None:
    """把中文数字或阿拉伯数字字符串转成 int。失败返回 None。"""
    s = s.strip()
    if not s:
        return None
    # 纯阿拉伯数字
    if s.isdigit():
        return int(s)
    # 中文
    total = 0
    current = 0
    i = 0
    while i < len(s):
        c = s[i]
        if c not in _CN_NUM:
            return None
        v = _CN_NUM[c]
        if v == 10:
            current = max(current, 1) * 10
            total += current
            current = 0
        elif v == 100:
            current = max(current, 1) * 100
            total += current
            current = 0
        elif v == 1000:
            current = max(current, 1) * 1000
            total += current
            current = 0
        else:
            current = current * 10 + v if current else v
        i += 1
    return total + current

# --------- 数据结构 ---------

@dataclass
class Segment:
    book_id: str
    book_name: str
    juan: int
    juan_name: str
    segment: int
    text: str
    sub_type: str | None = None      # 本纪/列传/世家/志/表/书；可空
    sub_index: int | None = None     # 该体裁内的序号；可空

    @property
    def urn(self) -> str:
        return f"{self.book_id}/{self.juan:03d}/{self.segment:03d}"

    @property
    def semantic_urn(self) -> str | None:
        """语义化 URN，如 shiji/世家/030/001。仅当 sub_type/sub_index 都有时返回。"""
        if self.sub_type and self.sub_index is not None:
            return f"{self.book_id}/{self.sub_type}/{self.sub_index:03d}/{self.segment:03d}"
        return None

    @property
    def char_count(self) -> int:
        return len(self.text)

# --------- 解析 ---------

_cc = OpenCC("t2s")

def normalize_text(text: str) -> str:
    """繁→简，去零宽字符，归一化空白。"""
    text = _cc.convert(text)
    text = text.replace("\u3000", " ").replace("\ufeff", "")
    return text

# juan_name 反推 pattern：允许"本纪/列传"后夹 1 字（上/中/下）再跟第N
# 例 "宋本纪上第一" → ("本纪", 1), "齐本纪下第五" → ("本纪", 5)
_NAME_SUBTYPE_PATTERN = re.compile(
    r"(本纪|列传|世家|志|表|书|帝纪)(?:[上中下])?第([一二三四五六七八九十百千零〇○0-9]+)"
)


def _parse_subtype_from_name(name: str) -> tuple[str | None, int | None]:
    """从 juan_name 反推 (sub_type, sub_index)。

    Examples:
        "五帝本纪第一"      → ("本纪", 1)
        "管晏列传第二"      → ("列传", 2)
        "宋本纪上第一"      → ("本纪", 1)
        "列传第二百三十"    → ("列传", 230)
    """
    m = _NAME_SUBTYPE_PATTERN.search(name)
    if m:
        return m.group(1), cn_to_int(m.group(2))
    # 兜底：SUBTYPE_PATTERN (两个分支，全书范围的模式)
    m = SUBTYPE_PATTERN.search(name)
    if not m:
        return None, None
    sub_type = m.group(1) or m.group(3)
    idx_str = m.group(2) or m.group(4)
    return sub_type, cn_to_int(idx_str)


def split_book_to_juans(
    text: str, book_id: str, book_name: str
) -> list[tuple[int, str, str, str | None, int | None]]:
    """把一本书的全文切分为 (juan_num, juan_name, juan_body, sub_type, sub_index) 列表。

    优先级：
      1. JUAN_PATTERN（卷X）匹配 ≥ 5 处 → 主分卷器。每卷尝试从 juan_name 反推 sub_type/sub_index。
      2. 否则 SUBTYPE_PATTERN（本纪第N/列传第N/...）兜底分卷（适用宋史/明史/清史稿等大书）。
      3. Pattern D "魏志卷X/蜀志卷X"三国志专属。
      4. 都没有 → 单"卷 0"通体（极少见，仅小补注/非正史）。
    """
    juan_matches = list(JUAN_PATTERN.finditer(text))
    sub_matches = list(SUBTYPE_PATTERN.finditer(text))
    zhi_matches = list(ZHI_VOLUME_PATTERN.finditer(text))

    juan_n = len(juan_matches)
    sub_n = len(sub_matches)
    zhi_n = len(zhi_matches)

    # 决策矩阵：
    # 1) SUBTYPE 显著占优（≥ 2.5×JUAN 且自身 ≥ 10）→ 用 SUBTYPE（如宋史 19×）
    # 2) JUAN 命中 ≥ 5 → 试 JUAN 切分；若产出卷数 < SUBTYPE/4 且 SUBTYPE 足够多，切回 SUBTYPE
    #    （应对旧唐书/晋书：JUAN_PATTERN 误命中目录，cn_to_int 后过滤剩 1 卷；
    #     旧五代史：目录 150 卷后正文卷已失效，_split_by_juan 会过滤空 body 只剩 1 卷）
    # 3) JUAN 不达标 但 SUBTYPE ≥ 10 → 用 SUBTYPE
    # 4) 三国志专属 Pattern D：若 Pattern D ≥ 10，优先用
    # 5) 都不达标 → 通体不分卷
    if sub_n >= 10 and sub_n >= juan_n * 2.5:
        return _split_by_subtype(text, sub_matches)
    if juan_n >= 5:
        result = _split_by_juan(text, juan_matches)
        if len(result) < max(sub_n // 4, 5) and sub_n >= 10:
            return _split_by_subtype(text, sub_matches)
        if len(result) < 5 and zhi_n >= 10:
            return _split_by_zhi(text, zhi_matches)
        return result
    if sub_n >= 10:
        return _split_by_subtype(text, sub_matches)
    if zhi_n >= 10:
        return _split_by_zhi(text, zhi_matches)

    return [(0, f"{book_name}（通体）", text.strip(), None, None)]


def _split_by_zhi(
    text: str, matches: list[re.Match], min_body_chars: int = 100
) -> list[tuple[int, str, str, str | None, int | None]]:
    """Pattern D 分卷：三国志"魏志卷X / 蜀志卷X / 吴志卷X"。

    juan_num 全书累加；sub_type 取"魏志/蜀志/吴志"；sub_index 为该志内序号。
    body 太短（目录项）跳过。
    """
    juans: list[tuple[int, str, str, str | None, int | None]] = []
    counter = 0
    for i, m in enumerate(matches):
        zhi = m.group(1)
        idx = cn_to_int(m.group(2))
        if idx is None:
            continue
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        if len(body) < min_body_chars:
            continue
        tail = text[body_start : body_start + 30].split("\n", 1)[0].strip()
        juan_name = f"{zhi}卷{m.group(2)}{(' ' + tail) if tail else ''}".strip()
        counter += 1
        juans.append((counter, juan_name, body, zhi, idx))
    return juans


def _split_by_juan(
    text: str, matches: list[re.Match], min_body_chars: int = 100
) -> list[tuple[int, str, str, str | None, int | None]]:
    """按 JUAN_PATTERN 分卷，并尝试从卷名反推 sub_type/sub_index。

    body 短于 min_body_chars 的视作目录项跳过（旧五代史前半是 150 行目录）。
    """
    juans: list[tuple[int, str, str, str | None, int | None]] = []
    for i, m in enumerate(matches):
        juan_num_str = m.group(1) or m.group(2)
        juan_num = cn_to_int(juan_num_str)
        if juan_num is None:
            continue
        header_start = m.start()
        # juan_name 取「完整行」而非仅 match 区间（Pattern B 只到体裁词，漏"第N"）
        line_end_idx = text.find("\n", m.end())
        if line_end_idx == -1:
            line_end_idx = min(m.end() + 60, len(text))
        header_line = text[header_start:line_end_idx].strip()
        # body 仍然从 match 末尾 或 行末（取更远的）开始，避免重复把 juan_name 计入 body
        body_start = max(m.end(), line_end_idx)
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        juan_name = re.sub(
            r"^\s*[\u4e00-\u9fff]{0,4}\s*(?:◎|◆|★)?\s*(?:第)?卷\s*[一二三四五六七八九十百千零〇○0-9]+\s*",
            "",
            header_line,
        ).strip()
        if not juan_name:
            juan_name = f"卷{juan_num}"
        sub_type, sub_index = _parse_subtype_from_name(juan_name)
        body = text[body_start:body_end].strip()
        if len(body) < min_body_chars:
            continue
        juans.append((juan_num, juan_name, body, sub_type, sub_index))
    return juans


def _split_by_subtype(
    text: str, matches: list[re.Match], min_body_chars: int = 100
) -> list[tuple[int, str, str, str | None, int | None]]:
    """SUBTYPE 兜底分卷：每个 "本纪第N/列传第N/..." 标识起一个新卷。

    juan_num 用全书 running counter（1, 2, 3, ...）。
    juan_name 取标识 + 后续 30 字（直到换行或下个标识）。
    body 短于 min_body_chars 的视作目录项，跳过。
    """
    juans: list[tuple[int, str, str, str | None, int | None]] = []
    counter = 0
    for i, m in enumerate(matches):
        sub_type = m.group(1) or m.group(3)
        idx_str = m.group(2) or m.group(4)
        sub_index = cn_to_int(idx_str)
        if sub_index is None:
            continue
        header_start = m.start()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        # 跳过过短的 body（多为目录项 "本纪第一本纪第二..."）
        if len(body) < min_body_chars:
            continue
        # 卷名 = 标识 + 紧跟的 30 字（卷小标题，至换行止）
        tail = text[body_start : body_start + 30]
        tail = tail.split("\n", 1)[0].strip()
        sep = "第" if m.group(1) else ""
        juan_name = f"{sub_type}{sep}{idx_str}{(' ' + tail) if tail else ''}".strip()
        counter += 1
        juans.append((counter, juan_name, body, sub_type, sub_index))
    return juans

def split_juan_to_segments(body: str, max_chars: int = 500) -> list[str]:
    """把一卷的 body 切分为段落列表。

    首选：双换行分段。
    二选：单换行 + 段落 > max_chars 时按中文句号切。
    """
    raw = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    segments: list[str] = []
    for p in raw:
        p = re.sub(r"\s+", "", p)  # 段内去所有空白（古文本无空格）
        if len(p) <= max_chars:
            segments.append(p)
        else:
            # 按句号 + 问号 + 叹号切
            sentences = re.split(r"(?<=[。？！])", p)
            buf = ""
            for s in sentences:
                if len(buf) + len(s) > max_chars and buf:
                    segments.append(buf)
                    buf = s
                else:
                    buf += s
            if buf:
                segments.append(buf)
    return segments

def parse_file(path: Path) -> Iterator[Segment]:
    """解析单个 daizhige txt 文件 → 段落流。"""
    stem = path.stem  # e.g. "史記"
    book_id = BOOK_ID_MAP.get(stem)
    if not book_id:
        # 未识别的书目生成保守 slug
        book_id = f"unknown_{stem}"

    raw = path.read_text(encoding="utf-8", errors="ignore")
    text = normalize_text(raw)

    juans = split_book_to_juans(text, book_id, stem)
    for juan_num, juan_name, body, sub_type, sub_index in juans:
        segments = split_juan_to_segments(body)
        for i, seg_text in enumerate(segments, 1):
            yield Segment(
                book_id=book_id,
                book_name=stem,
                juan=juan_num,
                juan_name=juan_name,
                segment=i,
                text=seg_text,
                sub_type=sub_type,
                sub_index=sub_index,
            )

# --------- SQLite 构建 ---------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id TEXT NOT NULL,
    book_name TEXT NOT NULL,
    juan INTEGER NOT NULL,
    juan_name TEXT NOT NULL,
    segment INTEGER NOT NULL,
    text TEXT NOT NULL,
    text_ngram TEXT NOT NULL,  -- bigram 空格串，供 FTS 索引
    sub_type TEXT,             -- 本纪/列传/世家/志/表/书；可空
    sub_index INTEGER,         -- 体裁内序号；可空
    char_count INTEGER NOT NULL,
    urn TEXT NOT NULL UNIQUE
);

-- FTS5 用 unicode61 按空格切，索引 text_ngram 即可用中文短语查询
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    text_ngram,
    book_name UNINDEXED,
    juan_name UNINDEXED,
    urn UNINDEXED,
    content='documents',
    content_rowid='id',
    tokenize="unicode61 remove_diacritics 0"
);

CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, text_ngram, book_name, juan_name, urn)
    VALUES (new.id, new.text_ngram, new.book_name, new.juan_name, new.urn);
END;

CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, text_ngram, book_name, juan_name, urn)
    VALUES ('delete', old.id, old.text_ngram, old.book_name, old.juan_name, old.urn);
END;

CREATE INDEX IF NOT EXISTS idx_book_juan ON documents(book_id, juan, segment);
CREATE INDEX IF NOT EXISTS idx_book_subtype ON documents(book_id, sub_type, sub_index);
"""

def init_db(rebuild: bool = False) -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if rebuild and CORPUS_DB.exists():
        print(f"[rebuild] 删除旧库 {CORPUS_DB}")
        CORPUS_DB.unlink()
    conn = sqlite3.connect(CORPUS_DB)
    conn.executescript(SCHEMA_SQL)
    return conn

def ingest_segments(conn: sqlite3.Connection, segments: list[Segment]) -> int:
    """批量插入段落。已存在的 urn 跳过。返回新增条数。"""
    cur = conn.cursor()
    inserted = 0
    for seg in segments:
        try:
            cur.execute(
                "INSERT INTO documents(book_id, book_name, juan, juan_name, segment, "
                "text, text_ngram, sub_type, sub_index, char_count, urn) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (seg.book_id, seg.book_name, seg.juan, seg.juan_name,
                 seg.segment, seg.text, to_bigrams(seg.text),
                 seg.sub_type, seg.sub_index, seg.char_count, seg.urn),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            # urn 已存在，跳过
            pass
    conn.commit()
    return inserted

# --------- 主流程 ---------

def build(
    book_filter: str | None = None,
    rebuild: bool = False,
) -> None:
    if not DAIZHIGE_ZHENGSHI.exists():
        print(f"[fatal] 找不到 {DAIZHIGE_ZHENGSHI}")
        print("  请先运行：bash skill/scripts/vendor/pull_all.sh")
        sys.exit(1)

    conn = init_db(rebuild=rebuild)

    txt_files = sorted(DAIZHIGE_ZHENGSHI.glob("*.txt"))
    if not txt_files:
        print(f"[fatal] {DAIZHIGE_ZHENGSHI} 下未找到 txt 文件")
        sys.exit(1)

    print(f"[scan] {DAIZHIGE_ZHENGSHI} 找到 {len(txt_files)} 个文件")

    total_segments = 0
    total_books = 0
    for path in txt_files:
        stem = path.stem
        book_id = BOOK_ID_MAP.get(stem, f"unknown_{stem}")

        if book_filter and book_id != book_filter:
            continue

        # 检查是否已入库（除非 rebuild）
        if not rebuild:
            cur = conn.execute(
                "SELECT COUNT(*) FROM documents WHERE book_id = ?", (book_id,)
            )
            existing = cur.fetchone()[0]
            if existing > 0:
                print(f"[skip] {stem} ({book_id}) 已入库 {existing} 段")
                continue

        segments = list(parse_file(path))
        if not segments:
            print(f"[warn] {stem} 无可提取段落")
            continue

        inserted = ingest_segments(conn, segments)
        total_segments += inserted
        total_books += 1
        # 统计：这本书有几卷
        juans = {s.juan for s in segments}
        print(f"[ingest] {stem} ({book_id}): {inserted} 段 / {len(juans)} 卷")

    conn.close()

    print(f"\n[done] 新入 {total_books} 本书，共 {total_segments} 段")
    print(f"[db] {CORPUS_DB} (体积 {CORPUS_DB.stat().st_size / 1024 / 1024:.1f} MB)")

def inspect(filename: str) -> None:
    """不入库，只解析一个文件打印前几卷摘要 — 用于调试 daizhige 格式。"""
    path = DAIZHIGE_ZHENGSHI / filename
    if not path.exists():
        # 也可能是绝对路径
        p = Path(filename)
        if p.exists():
            path = p
        else:
            print(f"[fatal] 找不到文件 {filename}")
            sys.exit(1)

    print(f"[inspect] {path}")
    print(f"[size] {path.stat().st_size / 1024:.1f} KB")

    raw = path.read_text(encoding="utf-8", errors="ignore")
    print(f"[chars] 原始字符数 {len(raw)}")
    print(f"[preview] 前 200 字：\n{raw[:200]}\n...")

    text = normalize_text(raw)
    stem = path.stem
    book_id = BOOK_ID_MAP.get(stem, f"unknown_{stem}")

    juans = split_book_to_juans(text, book_id, stem)
    print(f"\n[juans] 切分出 {len(juans)} 卷")
    for i, (num, name, body, sub_type, sub_index) in enumerate(juans[:5]):
        st = f" [{sub_type}#{sub_index}]" if sub_type else ""
        print(f"  卷{num}{st} 《{name}》: {len(body)} 字，首段：{body[:80]}...")
    if len(juans) > 5:
        print(f"  ...（共 {len(juans)} 卷，仅示前 5）")
    # 体裁覆盖统计
    typed = sum(1 for j in juans if j[3])
    print(f"\n[subtypes] 有体裁标注的卷: {typed}/{len(juans)}")

    if juans:
        segs = split_juan_to_segments(juans[0][2])
        print(f"\n[segments] 首卷切分出 {len(segs)} 段")
        for i, s in enumerate(segs[:3]):
            print(f"  段{i+1} ({len(s)} 字): {s[:60]}...")

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rebuild", action="store_true", help="清表重建")
    parser.add_argument("--book", type=str, help="只构建指定 book_id")
    parser.add_argument("--inspect", type=str, help="不入库，仅解析示例")
    args = parser.parse_args()

    if args.inspect:
        inspect(args.inspect)
    else:
        build(book_filter=args.book, rebuild=args.rebuild)

if __name__ == "__main__":
    main()
