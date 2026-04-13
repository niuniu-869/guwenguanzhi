#!/bin/bash
# Watchdog：
# 1. 等当前 words 修复进程（PID=$1）结束
# 2. 检查 error 句数；若 > 200，再跑一轮 fix words，最多 3 次
# 3. 最终强制 re-merge 所有卷
# 4. 统计并写入报告

set -u
WATCHED_PID="${1:-}"
LOG="/tmp/shiji_watchdog.log"
cd /niuniu869_dev/guwenguanzhi_ai

{
  echo "=== Watchdog 启动 $(date) ==="
  echo "监控 PID: $WATCHED_PID"

  # 1. 等前置进程结束
  if [ -n "$WATCHED_PID" ]; then
    while kill -0 "$WATCHED_PID" 2>/dev/null; do
      sleep 30
    done
    echo "[$(date)] 前置进程 $WATCHED_PID 已结束"
  fi

  # 2. 循环修复直到 error 足够少或尝试次数用尽
  for ROUND in 1 2 3; do
    # 统计当前 error 数
    ERR=$(python3 -c "
import json
from pathlib import Path
n = 0
for f in sorted(Path('data/books/shiji/output').glob('shiji_[0-9][0-9][0-9]_words.json')):
    for p in json.load(open(f)):
        for s in p.get('sentences', []):
            if s.get('error') or not s.get('words'):
                n += 1
print(n)
")
    echo "[$(date)] 第 $ROUND 轮前：words error = $ERR"
    if [ "$ERR" -lt 200 ]; then
      echo "[$(date)] error 低于阈值，停止修复"
      break
    fi
    echo "[$(date)] 启动第 $ROUND 轮 words 修复..."
    MIMO_RPM=50 MAX_WORKERS=10 INNER_WORKERS=10 STEP=words \
      python3 scripts/shiji/fix_errors.py >> /tmp/shiji_fix_words.log 2>&1
    echo "[$(date)] 第 $ROUND 轮完成"
  done

  # 3. 强制 re-merge 所有卷（无论之前是否 merged）
  echo "[$(date)] 开始强制 re-merge..."
  python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, 'scripts/shiji')
sys.path.insert(0, 'scripts')
from run_shiji import merge, load_catalog
cat = load_catalog()
ok = 0
for j in cat['juan']:
    r = merge(j)
    if '✅' in r:
        ok += 1
print(f'✅ merged {ok}/{len(cat[\"juan\"])}')
"

  # 4. 最终统计报告
  echo "[$(date)] === 最终报告 ==="
  python3 -c "
import json
from pathlib import Path
final_empty = total_p = total_s = total_s_err = 0
for f in sorted(Path('data/books/shiji/output').glob('shiji_[0-9][0-9][0-9].json')):
    d = json.load(open(f))
    for p in d['paragraphs']:
        total_p += 1
        if not p.get('translation') or not p.get('sentences'):
            final_empty += 1
        for s in p.get('sentences', []):
            total_s += 1
            if not s.get('words'):
                total_s_err += 1
print(f'卷数: 130')
print(f'段落: {total_p}')
print(f'空段: {final_empty} ({final_empty*100/total_p:.2f}%)')
print(f'句子: {total_s}')
print(f'无词条的句子: {total_s_err} ({total_s_err*100/max(total_s,1):.2f}%)')
"
  echo "[$(date)] === Watchdog 结束 ==="
} >> "$LOG" 2>&1
