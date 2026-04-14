#!/usr/bin/env python3
"""定向重跑 5 篇 words+merge，unbuffered 输出"""
import os, sys, json, time
os.environ['FORCE'] = '1'
sys.path.insert(0, 'scripts')
from pathlib import Path

TARGETS = ['061_颜斶说秦王', '059_范雎说秦王', '048_吴子使札来聘',
           '063_赵威后问齐使', '028_季札观周乐']

# 清掉 _words.json
for t in TARGETS:
    for f in Path('data/articles').rglob(f'{t}_words.json'):
        f.unlink()
        print(f"[cleanup] 删 {f}", flush=True)

import run_all_parallel as p

c = json.load(open('data/catalog.json'))
arts = []
for d in c['dynasties']:
    for a in d['authors']:
        for art in a['articles']:
            if art['id'] in TARGETS:
                arts.append((art, d['id']))

for idx, (art, did) in enumerate(arts, 1):
    t0 = time.time()
    print(f"\n[{idx}/{len(arts)}] {art['title']} - gen_words...", flush=True)
    r1 = p.gen_words(art, did)
    print(f"  → {r1}  ({time.time()-t0:.0f}s)", flush=True)
    t1 = time.time()
    r2 = p.merge(art, did)
    print(f"  → {r2}  ({time.time()-t1:.0f}s)", flush=True)
