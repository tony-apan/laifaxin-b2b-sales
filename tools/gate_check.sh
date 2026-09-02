#!/bin/bash
# ★ 流程闸门（Gate）：流程开始前强制运行。未通过=禁止任何保存/模板/序列/contact-add 操作。
# 用法: bash gate_check.sh --token <TOKEN> [--org <orgId>] [--product 金属粉末]
#   ★第一步建议先跑: python3 tools/check_login.py --token <TOKEN>（登录检查+无token引导教程）
#   --org 可省略：token=web.laifaxin.com&<orgId>&<hash>，自动提取中段（官方:accesstoken已含账号信息）
KB="$(cd "$(dirname "$0")/.." && pwd)"
TOKEN_GUIDE="https://www.laifa.xin/share/ai/laifaxin-ai-account-connection"
TOKEN=""; ORG=""; PRODUCT=""
while [ $# -gt 0 ]; do case "$1" in --token) TOKEN="$2"; shift 2;; --org) ORG="$2"; shift 2;; --product) PRODUCT="$2"; shift 2;; *) shift;; esac; done
# org 自动从 token 提取
if [ -z "$ORG" ] && [ -n "$TOKEN" ]; then
  AUTO_ORG=$(printf '%s' "$TOKEN" | awk -F'&' 'NF>=3{print $2}')
  if [ -n "$AUTO_ORG" ]; then ORG="$AUTO_ORG"; echo "  ℹ️ org 自动从 token 提取: $ORG"; fi
fi
PASS=0; FAIL=0
ok(){ echo "  ✅ $1"; PASS=$((PASS+1)); }
bad(){ echo "  ❌ $1"; FAIL=$((FAIL+1)); }
echo "🚦 流程闸门（Gate Check）— 必须全部通过才能开始流程"
echo "[1] 必读文档存在（唯一真源）"
for f in RULES.md INDEX.md specs/threshold-method.md specs/domain-scale-sop.md specs/sequence-config.md; do
  [ -f "$KB/$f" ] && ok "文档 $f" || bad "文档 $f 缺失"
done
echo "[2] token 有效（流程第一步=登录检查,建议先跑 tools/check_login.py——引导更全）"
if [ -z "$TOKEN" ]; then
  bad "还差一步: 没有拿到 token"
  echo "  👉 请用户按教程获取后发来: $TOKEN_GUIDE"
  echo "     (控制台一键复制: copy(localStorage.getItem(\"accesstoken\")); 显示 undefined=正常已复制)"
  echo "  拿到 token 后带上 --token 重跑本闸门即可"
elif [ -z "$ORG" ]; then
  bad "token 格式不对(提取不到 orgId,应为 web.laifaxin.com&<orgId>&<hash>)——大概率没复制完整,建议用教程方法二一键复制"
else
  curl -sSL -X POST "https://web.laifaxin.com/api/benefits/refine-data?uid=$ORG" -H "Content-Type: application/json" -H "accesstoken: $TOKEN" -d '{}' | grep -q '"success":true' && ok "token有效(已登录)" || { bad "token失效/未登录(若刚才能上网,则不是网络问题,重取即可)"; echo "  📖 获取token教程: $TOKEN_GUIDE"; echo "     方法一: 检查→应用程序→本地存储→web.laifaxin.com→accesstoken→复制'值'整串"; echo "     方法二: 检查→控制台→copy(localStorage.getItem(\"accesstoken\")); → undefined=已复制"; }
fi
echo "[3] 强制流程关键项（开始前自查）"
grep -q "排除中国" "$KB/RULES.md" && ok "4区排除规则已读" || bad "RULES 缺4区排除"
grep -q "selectOption:\"front\"" "$KB/specs/domain-scale-sop.md" && ok "front保存规则已读" || bad "domain-scale-sop 缺front"
grep -q "等联系人保存任务" "$KB/RULES.md" && ok "时序规则已读" || bad "RULES 缺时序规则"
grep -q "lfxFieldVeriable" "$KB/specs/sequence-config.md" && ok "模板code变量规则已读" || bad "sequence-config 缺code变量"
grep -q "搜索锚" "$KB/RULES.md" && ok "S3搜索锚规则已读(双路径:query_en直存/域名锚)" || bad "RULES 缺S3搜索锚规则"
echo "[4] 未解决问题警示(仅提醒,不计入闸门失败,不拦你现在找客户)"
echo "  ℹ️ 下面几条是「发信激活前」的待办提醒——不影响搜索/保存/建序列; AI 会在激活(S12)前再提醒你"
# 本地数据表（不入库，缺失自动跳过）
[ -f "$KB/db/issues.tsv" ] && awk -F'\t' '$7=="open" && $2=="P0"{print "  ⚠️ 激活前待办(本地): "$3}' "$KB/db/issues.tsv" | head -5
echo "🚦 结果: 通过=$PASS 失败=$FAIL"
if [ "$FAIL" -gt 0 ]; then echo "🚫 闸门未通过 — 按上面 👉 提示处理后重跑本闸门(多为: 拿 token / 补必填参数)"; exit 1; else echo "🟢 闸门通过 — 可以开始流程（先读 RULES.md 状态机 S0-S12）"; exit 0; fi
