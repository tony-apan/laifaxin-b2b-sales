#!/bin/bash
# 平台连接前闸门。推荐由 AI 用 --credentials-stdin 程序化传入凭据。
# --token/--org 已 deprecated 且不安全：凭据会暴露在 shell/Python argv，仅保留 AI 内部兼容。
usage(){
  echo "用法: bash gate_check.sh --credentials-stdin [--product operator/product]"
  echo "推荐: --credentials-stdin（AI 从当前聊天框通过程序化 stdin 传入）"
  echo "Deprecated/不安全: --token TOKEN --org ORG（凭据会进入 argv，仅内部兼容）"
}
KB="$(cd "$(dirname "$0")/.." && pwd)"
TOKEN_GUIDE="https://www.laifa.xin/share/ai/laifaxin-ai-account-connection"
TOKEN=""; ORG=""; PRODUCT=""; CREDENTIALS_STDIN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --credentials-stdin) CREDENTIALS_STDIN=1; shift ;;
    --help|-h) usage; exit 0 ;;
    --token) [ $# -ge 2 ] || { echo "缺少 --token 参数值" >&2; exit 2; }; TOKEN="$2"; shift 2 ;;
    --org) [ $# -ge 2 ] || { echo "缺少 --org 参数值" >&2; exit 2; }; ORG="$2"; shift 2 ;;
    --product) [ $# -ge 2 ] || { echo "缺少 --product 参数值" >&2; exit 2; }; PRODUCT="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done
PASS=0; FAIL=0
ok(){ echo "  [PASS] $1"; PASS=$((PASS+1)); }
bad(){ echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
echo "流程闸门（Gate Check）：必须全部通过才能开始流程"
echo "[1] 必读文档存在（唯一真源）"
for f in RULES.md INDEX.md specs/environment-setup.md specs/migration-handoff.md specs/operator-profile-sop.md specs/product-profile-sop.md specs/threshold-method.md specs/domain-scale-sop.md specs/sequence-config.md; do
  [ -f "$KB/$f" ] && ok "文档 $f" || bad "文档 $f 缺失"
done
echo "[2] 登录凭据与当前工作空间有效"
if [ "$CREDENTIALS_STDIN" -eq 1 ]; then
  if [ -n "$TOKEN" ] || [ -n "$ORG" ]; then
    bad "--credentials-stdin 不能与内部兼容参数混用"
  elif python3 "$KB/tools/check_login.py" --credentials-stdin --gate-mode; then
    ok "登录校验通过"
  else
    LOGIN_RC=$?
    bad "登录校验未通过（check_login rc=$LOGIN_RC）"
  fi
elif [ -n "$TOKEN" ] || [ -n "$ORG" ]; then
  # AI 内部兼容入口；凭据会进入本进程参数，不面向用户展示。
  if [ -z "$TOKEN" ] || [ -z "$ORG" ]; then
    bad "内部兼容参数 --token/--org 必须同时提供"
  elif python3 "$KB/tools/check_login.py" --token "$TOKEN" --org "$ORG" --gate-mode; then
    ok "登录校验通过"
  else
    LOGIN_RC=$?
    bad "登录校验未通过（check_login rc=$LOGIN_RC）"
  fi
else
  bad "还差登录校验：请把 accesstoken 与 orgId 两行整段直接粘贴到聊天框，由 AI 通过 stdin 重跑"
  echo "  教程: $TOKEN_GUIDE"
fi
echo "[3] 强制流程关键项（开始前自查）"
grep -q "排除中国" "$KB/RULES.md" && ok "4区排除规则已读" || bad "RULES 缺4区排除"
grep -q 'selectOption:"front"' "$KB/specs/domain-scale-sop.md" && ok "front保存规则已读" || bad "domain-scale-sop 缺front"
grep -q "等联系人保存任务" "$KB/RULES.md" && ok "时序规则已读" || bad "RULES 缺时序规则"
grep -q "lfxFieldVeriable" "$KB/specs/sequence-config.md" && ok "模板code变量规则已读" || bad "sequence-config 缺code变量"
grep -q "搜索锚" "$KB/RULES.md" && ok "S3搜索锚规则已读" || bad "RULES 缺S3搜索锚规则"
grep -q "签名区.*只有昵称\|签名.*只有昵称" "$KB/RULES.md" && ok "邮件签名纯昵称铁律已读" || bad "RULES 缺邮件签名纯昵称铁律"
if grep -q '`draft`' "$KB/specs/product-profile-sop.md" && grep -q '`confirmed`' "$KB/specs/product-profile-sop.md" && grep -q '`declined`' "$KB/specs/product-profile-sop.md"; then ok "产品档案状态机已读"; else bad "product-profile-sop 缺状态机"; fi
if [ -n "$PRODUCT" ]; then
  PROFILE="$KB/runs/$PRODUCT/product-profile.md"
  if [ -f "$PROFILE" ]; then
    STATUS=$(grep -m1 '^status:' "$PROFILE" | cut -d: -f2- | tr -d ' "')
    case "$STATUS" in confirmed|declined) ok "产品档案可续跑(status=$STATUS)" ;; *) bad "产品档案未确认(status=${STATUS:-缺失})" ;; esac
  else
    bad "未找到项目产品档案: runs/$PRODUCT/product-profile.md"
  fi
fi
echo "[4] 未解决问题警示（仅提醒）"
[ -f "$KB/db/issues.tsv" ] && awk -F'\t' '$7=="open" && $2=="P0"{print "  [WARN] 激活前待办(本地): "$3}' "$KB/db/issues.tsv" | head -5
echo "结果: 通过=$PASS 失败=$FAIL"
[ "$FAIL" -eq 0 ]
