#!/usr/bin/env bash
# 发布前自检：文档引用 + 全量测试 + 规则检查，一条命令跑完，全绿才交付。
# 用法：bash tools/preflight.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v py >/dev/null 2>&1; then PY=py
elif command -v python >/dev/null 2>&1; then PY=python
else echo "❌ 未找到 Python 解释器"; exit 1
fi
FAIL=0
run_gate() {
  local name="$1"; shift
  local log="$TMP/gate.log"
  printf '\n===== %s =====\n' "$name"
  if "$@" >"$log" 2>&1; then
    grep -E 'TOTAL_BAD|坏链|坏引用|缺失同名|^Ran |^OK|检查完成' "$log" | tail -8
    echo "✅ ${name}：通过"
  else
    cat "$log"
    echo "❌ ${name}：失败（上面是完整输出）"
    FAIL=1
  fi
}
run_gate "1/3 文档引用与索引核验" "$PY" tools/check_doc_links.py
run_gate "2/3 全量测试" "$PY" -m unittest discover -s tests
run_gate "3/3 规则检查" bash tools/check_rules.sh
printf '\n提示：INDEX 描述语义抽检可另跑 %s tools/check_doc_links.py --sample-index 20\n' "$PY"
if [ "$FAIL" -eq 0 ]; then
  printf '\n===== PREFLIGHT PASS（可以交付）=====\n'
  exit 0
else
  printf '\n===== PREFLIGHT FAIL（先修再交付）=====\n'
  exit 1
fi
