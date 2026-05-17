#!/usr/bin/env python3
"""
古文观止配图生成 —— 端到端调用 Image2（gpt-image-2，经 token-recyclebin 代理）。

四类配图：
  - 朝代封面 6 张   -> assets/dynasty/<dynasty>.webp
  - 文章题图 222 张 -> assets/hero/<dynasty>/<docId>.webp
  - 作者画像 61 张  -> assets/author/<authorId>.webp
  - 逐段插画 ~1220 -> assets/para/<dynasty>/<docId>/<i>.webp

前三类走 generations（文生图），把文章全文 / 朝代 / 作者生平直接喂 Image2；
逐段插画走 edits（图生图）——以本篇题图作参考图、本段原文入 prompt，靠参考图
把画风锁死。故 para 依赖 hero 先生成好。prompt 反复强调「画面不得出现文字」。

环境变量：
  IMAGE_API_KEY / IMAGE_API_URL / IMAGE_EDIT_URL / IMAGE_MODEL   图像 API 凭证（.env）
  IMG_MAX_WORKERS   并发数（默认 8）
  IMG_FORCE         任意非空 = 无视版本全量重跑
  IMG_SCOPE         dynasty,hero,author,para 任选子集（默认前三类；para 单独跑）
  IMG_LIMIT         每类最多生成 N 张（调试用，0=不限）

每张图状态写入 assets/manifest.json，含 IMAGE_VERSION；prompt/版本变更后
重跑只补差异（与管线 _prompt_version 机制同构）。改 prompt 必须 bump
下面的 IMAGE_VERSION。
"""

import base64
import io
import json
import os
import sys
import time
import uuid
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image

# ---- 复用 llm_client 的 .env 加载器，凭证统一从 .env 读 ----
sys.path.insert(0, str(Path(__file__).parent))
import llm_client  # noqa: E402  （import 时已执行 _load_dotenv）

import urllib.request
import urllib.error
import ssl

# ============================================================
# 配置
# ============================================================

IMAGE_VERSION = "v1"  # 改 prompt 必须 bump，否则旧图被判为「当前版本」跳过

BASE_DIR = Path(__file__).resolve().parent.parent
BOOK_DIR = BASE_DIR / "data" / "books" / "guwenguanzhi"
DOC_DIR = BOOK_DIR / "documents"
ASSET_DIR = BOOK_DIR / "assets"
MANIFEST_FILE = ASSET_DIR / "manifest.json"

API_KEY = os.environ.get("IMAGE_API_KEY", "")
API_URL = os.environ.get("IMAGE_API_URL", "https://image.token-recyclebin.com/v1/images/generations")
EDIT_URL = os.environ.get("IMAGE_EDIT_URL", "https://image.token-recyclebin.com/v1/images/edits")
API_MODEL = os.environ.get("IMAGE_MODEL", "gpt-image-2")

MAX_WORKERS = int(os.environ.get("IMG_MAX_WORKERS", "8"))
FORCE = bool(os.environ.get("IMG_FORCE", ""))
SCOPE = set(os.environ.get("IMG_SCOPE", "dynasty,hero,author").split(","))
LIMIT = int(os.environ.get("IMG_LIMIT", "0"))

API_TIMEOUT = 600          # 图像生成慢，单次最长 10 分钟
RETRY_TIMES = 2            # 失败重试次数（429/网络）
WEBP_QUALITY = 82
HERO_MAX_EDGE = 1280       # 题图 / 朝代封面 WebP 最长边
AUTHOR_MAX_EDGE = 1024     # 作者画像 WebP 最长边
PARA_MAX_EDGE = 768        # 逐段插画 WebP 最长边（页面内约 384px 显示，2x 足够）

DYNASTY_DESC = {
    "pre_qin": "先秦（春秋战国，诸子百家争鸣、钟鼎竹简、列国纵横的时代）",
    "han": "两汉（大一统气象，宫阙巍峨、辞赋纵横、史笔恢宏）",
    "wei_jin": "魏晋南北朝（玄学清谈、山水林泉、名士风流的时代）",
    "tang": "唐代（盛世气象，山河壮丽、诗意昂扬、襟怀开阔）",
    "song": "宋代（文人雅趣，庭院园林、理趣含蓄、笔墨清雅）",
    "ming": "明代（市井繁华与文人园林并存的时代）",
}
DYNASTY_SHORT = {
    "pre_qin": "先秦", "han": "汉", "wei_jin": "魏晋", "tang": "唐",
    "song": "宋", "ming": "明",
}

# ============================================================
# Prompt 模板：全站共用风格锁定 + 强制无文字
# ============================================================

STYLE = (
    "宋代院体绢本淡彩工笔画风格，以赭石、花青、淡墨为主的矿物颜料，"
    "色调清雅克制、绝不鲜艳浓烈，绢底呈微黄做旧质感，构图疏朗、留白考究，"
    "平远透视，气韵含蓄典雅。"
)
NO_TEXT = (
    "【最重要的硬性约束】整幅画面中绝对不能出现任何文字、汉字、书法字迹、"
    "诗句、标题、印章、落款、签名或文字边框——画面必须是纯粹的图像，"
    "一个字都不要画。"
)


def build_dynasty_prompt(dynasty: str) -> str:
    desc = DYNASTY_DESC.get(dynasty, dynasty)
    return (
        f"请创作一幅代表中国「{desc}」的横幅题图。{STYLE}"
        f"画面应表现这一历史时期的山河气象、人文风貌与时代精神，"
        f"意境开阔而含蓄。{NO_TEXT}"
    )


def build_hero_prompt(doc: dict) -> str:
    dyn = DYNASTY_SHORT.get(doc.get("dynasty", ""), "古")
    title = doc.get("title", "")
    author = (doc.get("author") or {}).get("name", "佚名")
    fulltext = "\n".join(p.get("original", "") for p in doc.get("paragraphs", []))
    return (
        f"请根据下面这篇中国{dyn}代古文的内容与意境，创作一幅横幅题图。{STYLE}"
        f"画面要贴合文章的题材、场景与情感基调（叙事、写景、议论或抒情），"
        f"以含蓄写意的手法呈现其核心意境，不要直白图解。{NO_TEXT}\n\n"
        f"文章标题：《{title}》\n作者：{author}（{dyn}代）\n"
        f"全文如下：\n{fulltext}"
    )


def build_hero_prompt_safe(doc: dict) -> str:
    """降级题图 prompt：不含全文，仅靠标题/作者/朝代——
    用于原全文触发内容护栏（如含暴力情节的传记）时兜底。"""
    dyn = DYNASTY_SHORT.get(doc.get("dynasty", ""), "古")
    title = doc.get("title", "")
    author = (doc.get("author") or {}).get("name", "佚名")
    return (
        f"请为中国{dyn}代古文《{title}》（作者{author}）创作一幅题图。{STYLE}"
        f"以含蓄写意的山水、庭院或人文场景表现古典气韵，意境清远。{NO_TEXT}"
    )


def build_author_prompt(author: dict) -> str:
    dyn = DYNASTY_SHORT.get(author.get("dynasty", ""), "古")
    name = author.get("name", "")
    bio = author.get("bio", "")
    return (
        f"请为中国{dyn}代文人「{name}」绘制一幅雅致的半身肖像。{STYLE}"
        f"人物着该时代的服饰，神态气质契合其身份与生平襟怀；这是一幅用于"
        f"页面辨识的装饰性文人像，重在气韵典雅，不必追求容貌的史实考证。"
        f"{NO_TEXT}\n\n人物生平：{bio}"
    )


def build_author_prompt_safe(author: dict) -> str:
    """降级作者画像 prompt：不含生平 bio，仅靠姓名/朝代——
    用于 bio 触发内容护栏（如含自尽、早逝等情节）时兜底。"""
    dyn = DYNASTY_SHORT.get(author.get("dynasty", ""), "古")
    name = author.get("name", "")
    return (
        f"请为中国{dyn}代文人「{name}」绘制一幅雅致的半身肖像。{STYLE}"
        f"人物着{dyn}代文人服饰，神态气质典雅从容；这是一幅用于页面辨识"
        f"的装饰性文人像，重在气韵，不必追求容貌的史实考证。{NO_TEXT}"
    )


def build_para_prompt(doc: dict, idx: int, total: int, para: dict) -> str:
    """逐段插画 prompt：题图作参考图，本段原文入 prompt。"""
    dyn = DYNASTY_SHORT.get(doc.get("dynasty", ""), "古")
    title = doc.get("title", "")
    text = para.get("original", "")
    return (
        f"参考图是中国{dyn}代古文《{title}》的题图。请严格保持与参考图完全一致的"
        f"宋代院体淡彩工笔画风、色调、笔法与绢本质感，为本篇第 {idx + 1}/{total} 段"
        f"内容绘制一幅情节插画，画面具体表现这一段所写的场景、人物与动作，"
        f"意境含蓄写意。{NO_TEXT}\n\n本段原文：{text}"
    )


def build_para_prompt_safe(doc: dict) -> str:
    """降级逐段插画 prompt：不含本段原文，仅靠题图参考图与篇名——
    用于本段原文触发内容护栏时兜底。"""
    dyn = DYNASTY_SHORT.get(doc.get("dynasty", ""), "古")
    title = doc.get("title", "")
    return (
        f"参考图是中国{dyn}代古文《{title}》的题图。请严格保持与参考图一致的"
        f"宋代院体淡彩工笔画风与色调，绘制一幅含蓄写意的情节插画，"
        f"以山水、庭院或人文场景表现古典气韵。{NO_TEXT}"
    )


# ============================================================
# 图像 API 调用
# ============================================================

_ssl_ctx = ssl.create_default_context()


def _build_multipart(boundary: str, fields: list) -> bytes:
    """拼 multipart/form-data body。fields: (name, filename|None, bytes)，
    filename 非空视作文件字段（图片走 image/webp）。"""
    out: list[bytes] = []
    for name, filename, value in fields:
        out.append(("--" + boundary).encode())
        if filename:
            out.append(
                ('Content-Disposition: form-data; name="%s"; filename="%s"'
                 % (name, filename)).encode())
            out.append(b"Content-Type: image/webp")
        else:
            out.append(('Content-Disposition: form-data; name="%s"' % name).encode())
        out.append(b"")
        out.append(value)
    out.append(("--" + boundary + "--").encode())
    out.append(b"")
    return b"\r\n".join(out)


def _image_request(url: str, data: bytes, headers: dict) -> bytes:
    """POST 图像请求，带 429/5xx 退避重试，返回图片字节。失败抛 RuntimeError。"""
    last_err = None
    for attempt in range(RETRY_TIMES + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, context=_ssl_ctx, timeout=API_TIMEOUT) as resp:
                raw = resp.read()
            j = json.loads(raw.decode("utf-8"))
            item = (j.get("data") or [{}])[0]
            b64 = item.get("b64_json")
            if b64:
                return base64.b64decode(b64)
            img_url = item.get("url")
            if img_url:
                with urllib.request.urlopen(img_url, context=_ssl_ctx, timeout=API_TIMEOUT) as ir:
                    return ir.read()
            raise RuntimeError("返回无 b64_json / url")
        except urllib.error.HTTPError as e:
            detail = e.read()[:300].decode("utf-8", "ignore")
            last_err = f"HTTP {e.code}: {detail}"
            if e.code not in (429, 500, 502, 503, 504):
                break
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
        if attempt < RETRY_TIMES:
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(last_err or "未知错误")


def call_image_api(prompt: str, size: str) -> bytes:
    """调用 Image2 generations 接口（纯文生图），返回图片字节。"""
    body = json.dumps({
        "model": API_MODEL, "prompt": prompt, "n": 1, "size": size,
    }).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + API_KEY,
        "Content-Type": "application/json",
    }
    return _image_request(API_URL, body, headers)


def call_image_edit_api(prompt: str, size: str, ref_bytes: bytes) -> bytes:
    """调用 Image2 edits 接口（图生图），ref_bytes 作参考图，返回图片字节。"""
    boundary = "----gwgz-" + uuid.uuid4().hex
    body = _build_multipart(boundary, [
        ("model", None, API_MODEL.encode("utf-8")),
        ("prompt", None, prompt.encode("utf-8")),
        ("size", None, size.encode("utf-8")),
        ("n", None, b"1"),
        ("image", "ref.webp", ref_bytes),
    ])
    headers = {
        "Authorization": "Bearer " + API_KEY,
        "Content-Type": "multipart/form-data; boundary=" + boundary,
    }
    return _image_request(EDIT_URL, body, headers)


def png_to_webp(png_bytes: bytes, out_path: Path, max_edge: int) -> int:
    """PNG -> 等比缩放 -> WebP，返回写入字节数。"""
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    w, h = img.size
    scale = min(1.0, max_edge / max(w, h))
    if scale < 1.0:
        img = img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "WEBP", quality=WEBP_QUALITY, method=6)
    return out_path.stat().st_size


# ============================================================
# 任务收集
# ============================================================

def collect_tasks() -> list[dict]:
    """扫描数据，产出待生成任务列表。每个任务：
    {kind, rel(相对 assets 的 webp 路径), prompt, size, max_edge}"""
    tasks: list[dict] = []

    if "dynasty" in SCOPE:
        for dyn in DYNASTY_DESC:
            tasks.append({
                "kind": "dynasty",
                "rel": f"dynasty/{dyn}.webp",
                "prompt": build_dynasty_prompt(dyn),
                "size": "1536x1024",
                "max_edge": HERO_MAX_EDGE,
            })

    doc_files = sorted(DOC_DIR.glob("**/*.json"))
    authors: dict[str, dict] = {}
    for f in doc_files:
        doc = json.loads(f.read_text("utf-8"))
        dyn = doc.get("dynasty", "unknown")
        if "hero" in SCOPE:
            tasks.append({
                "kind": "hero",
                "rel": f"hero/{dyn}/{doc['id']}.webp",
                "prompt": build_hero_prompt(doc),
                "prompt_fallback": build_hero_prompt_safe(doc),
                "size": "1536x1024",
                "max_edge": HERO_MAX_EDGE,
            })
        if "para" in SCOPE:
            # 逐段插画：以本篇题图为参考图，本段原文入 prompt
            hero_rel = f"hero/{dyn}/{doc['id']}.webp"
            paras = doc.get("paragraphs", [])
            for i, para in enumerate(paras):
                if not (para.get("original") or "").strip():
                    continue
                tasks.append({
                    "kind": "para",
                    "rel": f"para/{dyn}/{doc['id']}/{i}.webp",
                    "prompt": build_para_prompt(doc, i, len(paras), para),
                    "prompt_fallback": build_para_prompt_safe(doc),
                    "ref_rel": hero_rel,
                    "size": "1024x1024",
                    "max_edge": PARA_MAX_EDGE,
                })
        author = doc.get("author") or {}
        aid = author.get("id")
        if aid and aid not in authors and author.get("bio"):
            authors[aid] = author

    if "author" in SCOPE:
        for aid, author in sorted(authors.items()):
            tasks.append({
                "kind": "author",
                "rel": f"author/{aid}.webp",
                "prompt": build_author_prompt(author),
                "prompt_fallback": build_author_prompt_safe(author),
                "size": "1024x1536",
                "max_edge": AUTHOR_MAX_EDGE,
            })

    return tasks


# ============================================================
# Manifest
# ============================================================

def load_manifest() -> dict:
    if MANIFEST_FILE.exists():
        return json.loads(MANIFEST_FILE.read_text("utf-8"))
    return {"image_version": IMAGE_VERSION, "items": {}}


_manifest_lock = threading.Lock()


def save_manifest(manifest: dict) -> None:
    with _manifest_lock:
        ASSET_DIR.mkdir(parents=True, exist_ok=True)
        manifest["image_version"] = IMAGE_VERSION
        MANIFEST_FILE.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")


def needs_generation(task: dict, manifest: dict) -> bool:
    if FORCE:
        return True
    rec = manifest["items"].get(task["rel"])
    if not rec or not rec.get("ok"):
        return True
    if rec.get("version") != IMAGE_VERSION:
        return True
    return not (ASSET_DIR / task["rel"]).exists()


# ============================================================
# 主流程
# ============================================================

def _is_guardrail_error(err: str) -> bool:
    """内容护栏拦截：换 prompt 才有救，重试原 prompt 无意义。"""
    low = err.lower()
    return "guardrail" in low or "image_generation_text_response" in low


def _generate(task: dict, use_fallback: bool = False) -> bytes:
    """按任务类型调对应接口。para 走 edits（题图作参考图），其余走 generations。"""
    prompt = task["prompt_fallback"] if use_fallback else task["prompt"]
    if task["kind"] == "para":
        ref_path = ASSET_DIR / task["ref_rel"]
        if not ref_path.exists():
            raise RuntimeError("参考题图缺失：" + task["ref_rel"])
        return call_image_edit_api(prompt, task["size"], ref_path.read_bytes())
    return call_image_api(prompt, task["size"])


def run_one(task: dict, manifest: dict) -> tuple[str, bool, str]:
    rel = task["rel"]
    note = ""
    try:
        try:
            png = _generate(task, use_fallback=False)
        except RuntimeError as e:
            # 原 prompt 触发内容护栏 → 用降级 prompt 兜底重试一次
            if _is_guardrail_error(str(e)) and task.get("prompt_fallback"):
                png = _generate(task, use_fallback=True)
                note = "（降级 prompt）"
            else:
                raise
        nbytes = png_to_webp(png, ASSET_DIR / rel, task["max_edge"])
        rec = {
            "version": IMAGE_VERSION, "ok": True, "kind": task["kind"],
            "size": task["size"], "bytes": nbytes, "ts": int(time.time()),
        }
        if note:
            rec["note"] = note.strip("（）")
        with _manifest_lock:
            manifest["items"][rel] = rec
        return rel, True, f"{nbytes // 1024}KB {note}".strip()
    except Exception as e:  # noqa: BLE001
        with _manifest_lock:
            manifest["items"][rel] = {
                "version": IMAGE_VERSION, "ok": False, "kind": task["kind"],
                "error": str(e)[:300], "ts": int(time.time()),
            }
        return rel, False, str(e)[:200]


def main() -> int:
    if not API_KEY:
        print("[FATAL] IMAGE_API_KEY 未配置在 .env 中")
        return 1

    manifest = load_manifest()
    all_tasks = collect_tasks()

    # 按类型保留前 LIMIT 个（调试）
    if LIMIT > 0:
        kept: dict[str, int] = {}
        limited = []
        for t in all_tasks:
            c = kept.get(t["kind"], 0)
            if c < LIMIT:
                limited.append(t)
                kept[t["kind"]] = c + 1
        all_tasks = limited

    pending = [t for t in all_tasks if needs_generation(t, manifest)]
    skipped = len(all_tasks) - len(pending)
    by_kind: dict[str, int] = {}
    for t in pending:
        by_kind[t["kind"]] = by_kind.get(t["kind"], 0) + 1

    print(f"配图任务：共 {len(all_tasks)} 个，待生成 {len(pending)} 个"
          f"（已跳过 {skipped} 个）")
    print(f"  按类型：{by_kind}")
    print(f"  并发 {MAX_WORKERS}，IMAGE_VERSION={IMAGE_VERSION}")
    if not pending:
        print("无待生成任务，结束。")
        return 0

    done = ok = fail = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(run_one, t, manifest): t for t in pending}
        for fut in as_completed(futures):
            rel, success, msg = fut.result()
            done += 1
            if success:
                ok += 1
                tag = "OK  "
            else:
                fail += 1
                tag = "FAIL"
            print(f"[{done}/{len(pending)}] {tag} {rel}  {msg}", flush=True)
            if done % 10 == 0:
                save_manifest(manifest)

    save_manifest(manifest)
    dt = time.time() - t0
    print(f"\n完成：成功 {ok}，失败 {fail}，耗时 {dt / 60:.1f} 分钟")
    print(f"manifest -> {MANIFEST_FILE}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
