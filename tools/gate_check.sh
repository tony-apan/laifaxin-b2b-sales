#!/bin/bash
# ★ 平台连接前闸门：产品了解/适配完成、首次调用平台前运行。未通过=禁止任何保存/模板/序列/contact-add 操作。
# 用法（二选一）:
#   bash gate_check.sh --token $'accesstoken=<TOKEN>\norgId=<ORG>' [--product <operator_key>/<product_key>]
#   bash gate_check.sh --token <TOKEN> --org <localStorage的orgId> [--product <operator_key>/<product_key>]
# token 中段是用户 UID，不是企业工作空间 orgId；本闸门禁止从 token 中段猜 org。
KB="$(cd "$(dirname "$0")/.." && pwd)"
TOKEN_GUIDE="https://www.laifa.xin/share/ai/laifaxin-ai-account-connection"
TOKEN=""; ORG=""; PRODUCT=""
while [ $# -gt 0 ]; do case "$1" in --token) TOKEN="$2"; shift 2;; --org) ORG="$2"; shift 2;; --product) PRODUCT="$2"; shift 2;; *) shift;; esac; done
# 兼容控制台一键复制的两行整段：accesstoken=... + orgId=...
case "$TOKEN" in
  *"accesstoken="*)
    PARSED_TOKEN=$(printf '%s\n' "$TOKEN" | tr -d '\r' | grep -m1 '^accesstoken=' | cut -d= -f2-)
    PARSED_ORG=$(printf '%s\n' "$TOKEN" | tr -d '\r' | grep -m1 '^orgId=' | cut -d= -f2-)
    [ -n "$PARSED_TOKEN" ] && TOKEN="$PARSED_TOKEN"
    [ -z "$ORG" ] && [ -n "$PARSED_ORG" ] && ORG="$PARSED_ORG"
    ;;
esac
PASS=0; FAIL=0
ok(){ echo "  ✅ $1"; PASS=$((PASS+1)); }
bad(){ echo "  ❌ $1"; FAIL=$((FAIL+1)); }
echo "🚦 流程闸门（Gate Check）— 必须全部通过才能开始流程"
echo "[1] 必读文档存在（唯一真源）"
for f in RULES.md INDEX.md specs/environment-setup.md specs/migration-handoff.md specs/operator-profile-sop.md specs/product-profile-sop.md specs/threshold-method.md specs/domain-scale-sop.md specs/sequence-config.md; do
  [ -f "$KB/$f" ] && ok "文档 $f" || bad "文档 $f 缺失"
done
echo "[2] token + 当前工作空间 orgId 有效（平台连接前先跑 tools/check_login.py，引导更全）"
if [ -z "$TOKEN" ]; then
  bad "还差一步：没有拿到 token"
  echo "  👉 到首次连接平台时，再请用户按教程一键双取后把两行整段发来: $TOKEN_GUIDE"
  echo "  拿到后用 --token '<两行整段>' 重跑本闸门即可"
elif [ -z "$ORG" ] || [ "$ORG" = "null" ]; then
  bad "缺少当前工作空间 orgId——不能拿 token 中段的用户 UID 代替，否则企业账号会操作错空间"
  echo "  👉 回到来发信当前工作空间，按教程一键复制 accesstoken + orgId 两行整段: $TOKEN_GUIDE"
  echo "  然后原样传给 --token；也可显式传 --org <localStorage的orgId>"
else
  curl -sSL -X POST "https://web.laifaxin.com/api/benefits/refine-data?uid=$ORG" -H "Content-Type: application/json" -H "accesstoken: $TOKEN" -d '{}' | grep -q '"success":true' && ok "token有效，当前工作空间 orgId=$ORG" || { bad "token失效/未登录（若网络正常，需重新登录后一键双取，旧 token 不要反复贴）"; echo "  📖 获取 token + orgId 教程: $TOKEN_GUIDE"; }
fi
echo "[3] 强制流程关键项（开始前自查）"
grep -q "排除中国" "$KB/RULES.md" && ok "4区排除规则已读" || bad "RULES 缺4区排除"
grep -q "selectOption:\"front\"" "$KB/specs/domain-scale-sop.md" && ok "front保存规则已读" || bad "domain-scale-sop 缺front"
grep -q "等联系人保存任务" "$KB/RULES.md" && ok "时序规则已读" || bad "RULES 缺时序规则"
grep -q "lfxFieldVeriable" "$KB/specs/sequence-config.md" && ok "模板code变量规则已读" || bad "sequence-config 缺code变量"
grep -q "搜索锚" "$KB/RULES.md" && ok "S3搜索锚规则已读(AI数据库搜索三步链)" || bad "RULES 缺S3搜索锚规则"
grep -q "签名区.*只有昵称\|签名.*只有昵称" "$KB/RULES.md" && ok "邮件签名纯昵称铁律已读" || bad "RULES 缺邮件签名纯昵称铁律"
if grep -q '`draft`' "$KB/specs/product-profile-sop.md" && grep -q '`confirmed`' "$KB/specs/product-profile-sop.md" && grep -q '`declined`' "$KB/specs/product-profile-sop.md"; then ok "产品档案状态机已读"; else bad "product-profile-sop 缺 draft/confirmed/declined 状态机"; fi
if [ -n "$PRODUCT" ]; then
  PROFILE="$KB/runs/$PRODUCT/product-profile.md"
  if [ -f "$PROFILE" ]; then
    STATUS=$(grep -m1 '^status:' "$PROFILE" | cut -d: -f2- | tr -d ' "')
    case "$STATUS" in confirmed|declined) ok "产品档案可续跑(status=$STATUS): runs/$PRODUCT/product-profile.md" ;; *) bad "产品档案未确认(status=${STATUS:-缺失})——draft 禁止进入 S2" ;; esac
  else
    bad "未找到项目产品档案: runs/$PRODUCT/product-profile.md（--product 应传 operator_key/product_key）"
  fi
fi
echo "[4] 未解决问题警示(仅提醒,不计入闸门失败,不拦你现在找客户)"
echo "  ℹ️ 下面几条是「发信激活前」的待办提醒——不影响搜索/保存/建序列; AI 会在激活(S12)前再提醒你"
# 本地数据表（不入库，缺失自动跳过）
[ -f "$KB/db/issues.tsv" ] && awk -F'\t' '$7=="open" && $2=="P0"{print "  ⚠️ 激活前待办(本地): "$3}' "$KB/db/issues.tsv" | head -5
echo "🚦 结果: 通过=$PASS 失败=$FAIL"
if [ "$FAIL" -gt 0 ]; then echo "🚫 闸门未通过 — 按上面 👉 提示处理后重跑（多为：一键双取 token+orgId / 补项目参数）"; exit 1; else echo "🟢 闸门通过 — 可以开始平台流程（继续按 RULES.md 状态机 S0-S12）"; exit 0; fi
