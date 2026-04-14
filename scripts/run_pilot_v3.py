#!/usr/bin/env python3
"""
v3 Pilot Runner
- 复用 run_all_parallel.py 的 gen_meta / gen_trans / gen_words / merge 函数
- 只跑固定的 8 篇代表性文章，便于人工抽检 prompt 质量
- 始终 FORCE 重跑（无视已有版本缓存）

覆盖类型：
  - 多人物 · 多古今异义 · 多通假：郑伯克段于鄢 · 烛之武退秦师
  - 虚构人物+地名：桃花源记
  - 议论文（无具体人物）：师说
  - 山水抒情（characters 应为 []）：岳阳楼记 · 醉翁亭记
  - 赋体（作者+客）：前赤壁赋
  - 奏疏（历史人物）：前出师表
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ["FORCE"] = "1"  # pilot 必须重跑

import run_all_parallel as p  # noqa: E402  import 后才触发 FORCE 生效

BASE_DIR = Path(__file__).parent.parent
CATALOG_FILE = BASE_DIR / "data" / "catalog.json"

PILOT_IDS = [
    "001_郑伯克段于鄢",
    "017_烛之武退秦师",
    "103_前出师表",
    "108_桃花源记",
    "124_师说",
    "158_岳阳楼记",
    "171_醉翁亭记",
    "192_前赤壁赋",
]


def load_pilot_articles():
    catalog = json.loads(CATALOG_FILE.read_text("utf-8"))
    selected = []
    ids = set(PILOT_IDS)
    for dyn in catalog["dynasties"]:
        for author in dyn["authors"]:
            for art in author["articles"]:
                if art["id"] in ids:
                    selected.append((art, dyn["id"]))
    return selected


def run_step(fn, articles, step_name):
    print(f"\n{'=' * 60}\n🚀 {step_name}  ({len(articles)} 篇, MAX_WORKERS={p.MAX_WORKERS})\n{'=' * 60}", flush=True)
    t0 = time.time()
    done = skip = fail = 0
    with ThreadPoolExecutor(max_workers=p.MAX_WORKERS) as pool:
        futures = {pool.submit(fn, a, d): (a, d) for a, d in articles}
        for future in as_completed(futures):
            try:
                msg = future.result()
                if "⏭" in msg:
                    skip += 1
                elif "✅" in msg:
                    done += 1
                else:
                    fail += 1
                print(f"  {msg}", flush=True)
            except Exception as e:
                fail += 1
                a, d = futures[future]
                print(f"  ❌ {a['title']}: {e}", flush=True)
    elapsed = time.time() - t0
    print(f"📊 {step_name}: 完成{done} 跳过{skip} 失败{fail} 耗时{elapsed:.0f}s", flush=True)
    return done, skip, fail


def main():
    print(f"🔥 Pilot v3  prompt_version={p.PROMPT_VERSION}", flush=True)
    articles = load_pilot_articles()
    print(f"   选中 {len(articles)} 篇:", flush=True)
    for a, d in articles:
        print(f"   - [{d}] {a['title']} ({a['author']})")

    t0 = time.time()
    run_step(p.gen_meta, articles, "Step 2a: 元数据+人物卡")
    run_step(p.gen_trans, articles, "Step 2b: 逐段翻译")
    run_step(p.gen_words, articles, "Step 2c: 逐词注释（含 highlight）")
    run_step(p.merge, articles, "Step 2d: 合并")
    print(f"\n✅ Pilot 完成，总耗时 {(time.time() - t0) / 60:.1f} 分钟", flush=True)

    for a, d in articles:
        out = BASE_DIR / "data/articles" / d / f"{a['id']}.json"
        if out.exists():
            size = out.stat().st_size
            print(f"  ✓ {a['title']}: {size:,} bytes  →  {out.relative_to(BASE_DIR)}")
        else:
            print(f"  ✗ {a['title']}: 未生成")


if __name__ == "__main__":
    main()
