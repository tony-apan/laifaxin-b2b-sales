#!/bin/bash
# AI 快速检查：规则、问题状态，以及显式请求时的登录校验。
# --token/--org 已 deprecated 且不安全：凭据会暴露在 shell/Python argv，仅保留 AI 内部兼容。
usage(){
  echo "用法: bash check_rules.sh [--credentials-stdin]"
  echo "推荐: --credentials-stdin（AI 从当前聊天框通过程序化 stdin 传入）"
  echo "Deprecated/不安全: --token TOKEN --org ORG（凭据会进入 argv，仅内部兼容）"
}
KB="$(cd "$(dirname "$0")/.." && pwd)"
TOKEN=""; ORG=""; CREDENTIALS_STDIN=0; LOGIN_RC=0
while [ $# -gt 0 ]; do
  case "$1" in
    --credentials-stdin) CREDENTIALS_STDIN=1; shift ;;
    --help|-h) usage; exit 0 ;;
    --token) [ $# -ge 2 ] || { echo "缺少 --token 参数值" >&2; exit 2; }; TOKEN="$2"; shift 2 ;;
    --org) [ $# -ge 2 ] || { echo "缺少 --org 参数值" >&2; exit 2; }; ORG="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done
echo "AI 快速检查 (KB=$KB)"
echo "[1] 规则文件"
for f in RULES.md INDEX.md specs/environment-setup.md specs/migration-handoff.md specs/operator-profile-sop.md specs/product-profile-sop.md specs/threshold-method.md specs/domain-scale-sop.md specs/sequence-config.md; do
  [ -f "$KB/$f" ] && echo "  [PASS] $f" || echo "  [FAIL] $f 缺失"
done
echo "[2] 问题登记（open/未解决）"
[ -f "$KB/db/issues.tsv" ] && awk -F'\t' '$7=="open"{print "  [WARN] " $1" "$3}' "$KB/db/issues.tsv" || echo "  [INFO] 本地问题登记不存在（未随库分发，跳过）"
echo "[3] 可续接项目"
FOUND=0
for op in "$KB"/runs/*/*/operation-record.md; do
  [ -f "$op" ] || continue
  case "$op" in */runs/_template/*) continue;; esac
  FOUND=1
  d=$(dirname "$op"); s=$(grep -m1 '^status:' "$op" | cut -d: -f2- | tr -d ' "'); p="$d/product-profile.md"
  ps="缺"; [ -f "$p" ] && ps=$(grep -m1 '^status:' "$p" | cut -d: -f2- | tr -d ' "')
  echo "  ${d#$KB/runs/} | 流程:${s:-未标} | profile:$ps"
done
[ "$FOUND" -eq 1 ] || echo "  [INFO] 未发现可续接项目（新项目才走 S0）"
echo "[4] 登录校验"
if [ "$CREDENTIALS_STDIN" -eq 1 ]; then
  if [ -n "$TOKEN" ] || [ -n "$ORG" ]; then
    echo "  [FAIL] --credentials-stdin 不能与内部兼容参数混用"; LOGIN_RC=2
  else
    python3 "$KB/tools/check_login.py" --credentials-stdin --gate-mode || LOGIN_RC=$?
  fi
elif [ -n "$TOKEN" ] || [ -n "$ORG" ]; then
  # AI 内部兼容入口；凭据会进入本进程参数，不面向用户展示。
  if [ -z "$TOKEN" ] || [ -z "$ORG" ]; then
    echo "  [FAIL] 内部兼容参数 --token/--org 必须同时提供"; LOGIN_RC=2
  else
    python3 "$KB/tools/check_login.py" --token "$TOKEN" --org "$ORG" --gate-mode || LOGIN_RC=$?
  fi
else
  echo "  [INFO] 未提供凭据，仅完成离线规则检查；未做登录校验。"
fi
echo "检查完成"
exit "$LOGIN_RC"
