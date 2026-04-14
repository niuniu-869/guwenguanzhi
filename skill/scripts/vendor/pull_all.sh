#!/usr/bin/env bash
# 拉取 skill 所需的三路 vendor 数据源
# 幂等可重跑 — 已存在则跳过，传 --force 强制重拉
#
# 用法:
#   bash skill/scripts/vendor/pull_all.sh          # 常规拉取
#   bash skill/scripts/vendor/pull_all.sh --force  # 强制重拉
#   bash skill/scripts/vendor/pull_all.sh --only daizhige  # 只拉某一源
#
# 数据源许可证:
#   daizhige       — 未声明 (公共领域派生，本地使用，不入 git)
#   AncientDoc     — CC0 (可入库可再分发)
#   NiuTrans/Cls-M — MIT (可入库可再分发)

set -euo pipefail

# 定位到 skill/ 根目录（脚本路径 = skill/scripts/vendor/pull_all.sh）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENDOR_DIR="$SKILL_ROOT/vendor"

FORCE=0
ONLY=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --force) FORCE=1; shift ;;
        --only) ONLY="$2"; shift 2 ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

mkdir -p "$VENDOR_DIR"
cd "$VENDOR_DIR"

# --------- 通用工具 ---------

log() { printf "\033[1;34m[vendor]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[warn]\033[0m %s\n" "$*" >&2; }
fail() { printf "\033[1;31m[fail]\033[0m %s\n" "$*" >&2; exit 1; }

should_pull() {
    local name="$1"
    [[ -n "$ONLY" && "$ONLY" != "$name" ]] && return 1
    return 0
}

clone_shallow() {
    local url="$1"
    local dest="$2"
    if [[ -d "$dest/.git" && "$FORCE" -eq 0 ]]; then
        log "skip (exists): $dest"
        return 0
    fi
    if [[ -d "$dest" && "$FORCE" -eq 1 ]]; then
        log "force remove: $dest"
        rm -rf "$dest"
    fi
    log "git clone $url → $dest"
    git clone --depth=1 "$url" "$dest"
}

# --------- daizhige（二十四史底本）---------

if should_pull daizhige; then
    log "=== daizhige (二十四史底本) ==="
    clone_shallow "https://github.com/garychowcmu/daizhigev20.git" "daizhige"
    if [[ -d daizhige/史藏/正史 ]]; then
        count=$(find daizhige/史藏/正史 -maxdepth 1 -name '*.txt' | wc -l)
        log "daizhige 史藏/正史 包含 $count 个 txt 文件"
    else
        warn "daizhige 中未找到 史藏/正史 目录 —— 结构可能变化"
    fi
fi

# --------- AncientDoc（字节 CC0 古籍评测）---------

if should_pull ancientdoc; then
    log "=== AncientDoc (字节 CC0) ==="
    clone_shallow "https://github.com/bytedance/AncientDoc.git" "ancientdoc-cc0"
fi

# --------- NiuTrans/Classical-Modern（MIT 文白平行）---------

if should_pull niutrans; then
    log "=== NiuTrans/Classical-Modern (MIT 文白平行 972k 句对) ==="
    clone_shallow "https://github.com/NiuTrans/Classical-Modern.git" "niutrans-parallel"
fi

# --------- 汇总 ---------

log "=== 汇总 ==="
du -sh "$VENDOR_DIR"/* 2>/dev/null || true

log "完成。vendor 根目录: $VENDOR_DIR"
log "下一步: python skill/scripts/build_corpus.py"
