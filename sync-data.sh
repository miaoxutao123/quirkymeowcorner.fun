#!/usr/bin/env bash
# 把 ledger 生成的产出数据同步到本站仓库。
#
# 为什么要有这一步：站点是独立仓库（根目录就是 blog/），而产出数据由
# 上级的 ledger/ 目录跑脚本生成。两者不在同一仓库里，云端构建只能看到
# 本站仓库的内容——所以数据必须落一份快照进来。
#
# ledger 目录不存在时（比如在 CI 里、或者只 clone 了本站仓库），
# 不报错、原样保留已有快照。这样云端构建和别人的 clone 都不会挂。
set -euo pipefail
cd "$(dirname "$0")"

SRC="$(cd .. 2>/dev/null && pwd)/ledger/data"
DST="data"

mkdir -p "$DST"

if [ ! -f "$SRC/days.json" ] || [ ! -f "$SRC/summary.json" ]; then
  echo "  跳过数据同步：找不到 $SRC/days.json（保留仓库里已有的快照）"
  exit 0
fi

copied=0
for f in days.json summary.json; do
  if [ ! -f "$DST/$f" ] || ! cmp -s "$SRC/$f" "$DST/$f"; then
    cp "$SRC/$f" "$DST/$f"
    copied=$((copied + 1))
    echo "  已更新 $DST/$f"
  fi
done

if [ "$copied" -eq 0 ]; then
  echo "  产出数据已是最新"
else
  echo "  同步了 $copied 个文件"
fi

# 同步完必须脱敏：ledger 里的 conv_samples 是对话原文，可能夹着当时贴进去的
# API Key。这些数据要进公开仓库，不清理就是公开泄漏。
python sanitize_data.py
