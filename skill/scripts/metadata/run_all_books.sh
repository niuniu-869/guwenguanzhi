#!/bin/bash
# 跑 24 史全量 L2 metadata。史记已完成（Stage 2），跳过。
# MAX_WORKERS=30 MIMO_RPM=200 满 TPM。

set -e
cd "$(dirname "$0")/../../.."

export MAX_WORKERS="${MAX_WORKERS:-30}"
export MIMO_RPM="${MIMO_RPM:-200}"

BOOKS=(
  hanshu houhanshu sanguozhi jinshu songshu nanqishu liangshu chenshu
  weishu beiqishu zhoushu suishu nanshi beishi jiutangshu xintangshu
  jiuwudaishi xinwudaishi songshi liaoshi jinshi yuanshi mingshi qingshigao
)

echo "==========================================================="
echo "🔥 跑 ${#BOOKS[@]} 本书 L2 metadata @ MAX_WORKERS=$MAX_WORKERS MIMO_RPM=$MIMO_RPM"
echo "==========================================================="

for book in "${BOOKS[@]}"; do
  echo ""
  echo "### $book ###"
  python3 skill/scripts/metadata/generate.py --book "$book" 2>&1 | tail -5 || echo "⚠️ $book 出错，继续下一本"
done

echo ""
echo "==========================================================="
echo "📊 24 史全量 metadata 统计"
echo "==========================================================="
find skill/data/metadata -name "*.json" | wc -l
