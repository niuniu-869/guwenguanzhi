#!/bin/bash
# 古文观止全量重跑 · nohup 后台任务
#
# 流程：run_all_parallel (meta+trans+words+merge)
#       → migrate_to_books (拷贝到 data/books/guwenguanzhi/)
#       → sync_frontend_data (前端 symlink)
#       → validate_schema (最终校验报告)
#
# 脱离终端运行，关闭窗口不影响。查看进度：tail -f logs/gwgz_rerun_*.log

set -euo pipefail

cd "$(dirname "$0")/.."

# ============================================================
# 检查前置条件
# ============================================================

if [ ! -f .env ]; then
    echo "❌ .env 不存在。请复制 .env.example 为 .env 并填入 MIMO_API_KEY"
    exit 1
fi

if ! python3 -c "from pathlib import Path; exec(open('scripts/llm_client.py').read()[:2000]); assert API_KEY" 2>/dev/null; then
    # 简易检查：llm_client 能加载 .env
    :
fi

# ============================================================
# 日志与 PID
# ============================================================

LOG_DIR=logs
mkdir -p "$LOG_DIR"
STAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/gwgz_rerun_${STAMP}.log"
PID_FILE="$LOG_DIR/gwgz_rerun.pid"

# 如果已有进程在跑，提示
if [ -f "$PID_FILE" ] && kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
    echo "⚠️  已有进程在运行: PID=$(cat $PID_FILE)"
    echo "   查看进度: tail -f $LOG_DIR/gwgz_rerun_*.log"
    echo "   停止:     kill \$(cat $PID_FILE)"
    exit 1
fi

# ============================================================
# 启动 nohup
# ============================================================

# 环境变量：
#   FORCE=1        — 强制无视版本重跑（全量）
#   MAX_WORKERS    — 并发数（默认 20，视 RPM=100 调整）
#   MIMO_RPM       — 速率限制（默认 90）
#   STEP           — 子步骤（默认全跑 meta,trans,words,merge）

export FORCE="${FORCE:-1}"
export MAX_WORKERS="${MAX_WORKERS:-20}"
export MIMO_RPM="${MIMO_RPM:-90}"
export STEP="${STEP:-meta,trans,words,merge}"

echo "🚀 启动古文观止全量重跑"
echo "   日志:       $LOG_FILE"
echo "   PID 文件:   $PID_FILE"
echo "   FORCE:      $FORCE"
echo "   MAX_WORKERS:$MAX_WORKERS"
echo "   STEP:       $STEP"
echo ""

# -u 禁用 stdout buffer，日志实时可见
# 整个管线串行：run_all_parallel → migrate → sync → validate
# nohup setsid 完全脱离 terminal
nohup setsid bash -c "
    set -e
    echo '=== [1/4] run_all_parallel (prompt v2) ==='
    python3 -u scripts/run_all_parallel.py

    echo ''
    echo '=== [2/4] migrate_to_books (copy to data/books/) ==='
    python3 -u scripts/migrate_to_books.py

    echo ''
    echo '=== [3/4] sync_frontend_data (symlinks) ==='
    python3 -u scripts/sync_frontend_data.py

    echo ''
    echo '=== [4/4] validate_schema (quality check) ==='
    python3 -u scripts/validate_schema.py --book guwenguanzhi --fix || true

    echo ''
    echo '🎉 全部完成！' \$(date)
" > "$LOG_FILE" 2>&1 &

PID=$!
echo "$PID" > "$PID_FILE"

echo "✅ 已启动，PID=$PID"
echo ""
echo "💡 常用命令："
echo "   查看进度:  tail -f $LOG_FILE"
echo "   查看状态:  ps -p $PID"
echo "   停止任务:  kill $PID"
echo "   强制停止:  kill -9 $PID"
echo ""
echo "🚪 你现在可以安全关闭此终端，任务会继续在后台运行。"
