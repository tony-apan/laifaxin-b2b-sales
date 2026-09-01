#!/bin/bash
# AI 快速检查：token / 规则 / 问题状态（换机/断会话自查）
KB="$(cd "$(dirname "$0")/.." && pwd)"
TOKEN=""; ORG=""
while [ $# -gt 0 ]; do case "$1" in --token) TOKEN="$2"; shift 2;; --org) ORG="$2"; shift 2;; *) shift;; esac; done
echo "🩺 AI 快速检查 (KB=$KB)"
echo "[1] 规则文件"
for f in RULES.md INDEX.md specs/threshold-method.md specs/domain-scale-sop.md specs/sequence-config.md; do
  [ -f "$KB/$f" ] && echo "  ✅ $f" || echo "  ❌ $f 缺失"
done
echo "[2] 问题登记（open/未解决）"
# 问题/运行登记 = 本地数据表（不入库，缺失自动跳过）
[ -f "$KB/db/issues.tsv" ] && awk -F'\t' '$7=="open"{print "  ⚠️ " $1" "$3}' "$KB/db/issues.tsv" || echo "  ℹ️ 本地问题登记不存在（未随库分发，跳过）"
echo "[3] 产品运行记录"
[ -f "$KB/db/runs.tsv" ] && tail -n +2 "$KB/db/runs.tsv" | awk -F'\t' '{print "  " $1" | seed:"$2" | 保存:"$4" | 昵称:"$10" | 更新:"$NF}' || echo "  ℹ️ 本地运行记录不存在（未随库分发，跳过）"
echo "[4] token 校验"
if [ -z "$ORG" ]; then echo "  ⚠️ 未传 --org <orgId>(跳过线上校验)"; elif [ -n "$TOKEN" ]; then curl -sSL -X POST "https://web.laifaxin.com/api/benefits/refine-data?uid=$ORG" -H "Content-Type: application/json" -H "accesstoken: $TOKEN" -d '{}' | grep -q '"success":true' && echo "  ✅ token有效" || echo "  ⚠️ token失效，需更新——教程: https://www.laifa.xin/share/ai/laifaxin-ai-account-connection (控制台 copy(localStorage.getItem(\"accesstoken\")); 一键复制)"; else echo "  ⚠️ 未传token"; fi
echo "🩺 检查完成"
