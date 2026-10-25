#!/usr/bin/env bash
# 安装仓库内版本化 Git 钩子（每个 clone 跑一次）。
set -eu
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
chmod +x .githooks/pre-commit .githooks/pre-push tools/preflight.sh
git config core.hooksPath .githooks
echo "✅ 已启用提交前 / 推送前自检：core.hooksPath=.githooks"
echo "   每次 git commit 与 git push 前都会自动跑 bash tools/preflight.sh"
echo "   应急跳过：SKIP_PREFLIGHT=1 git commit ... / SKIP_PREFLIGHT=1 git push ..."
