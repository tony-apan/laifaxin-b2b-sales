#!/bin/bash
# 平台连接前闸门。推荐由 AI 用 --credentials-stdin 程序化传入凭据。
# --token/--org 已 deprecated 且不安全：凭据会暴露在 shell/Python argv，仅保留 AI 内部兼容。
#
# ★本脚本的输出分两层（2026-09-11 用户反馈"py 文件名用户看不懂"后改）：
#   上半 = 给 AI 看的体检明细（含内部检查项名），**禁止原样转述给用户**；
#   最后一节「给用户看的这一段」= 已写好的白话，AI 照抄即可（不含任何工具名/错误码/行话）。
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
PASS=0; FAIL=0; PENDING=0
# BLOCK 取最高优先级的"卡在哪"（1=最需要用户动手），用于生成最后一节白话
BLOCK=""; BLOCK_RANK=99
note_block(){ # $1=kind $2=rank(越小优先级越高)
  if [ "$2" -lt "$BLOCK_RANK" ]; then BLOCK="$1"; BLOCK_RANK="$2"; fi
}
ok(){ echo "  [PASS] $1"; PASS=$((PASS+1)); }
bad(){ echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
# "还差一步"=流程性的未完成（通常是还没轮到用户/等用户粘账号钥匙），不是账号或环境出问题
pending(){ echo "  [还差一步] $1"; PENDING=$((PENDING+1)); }

echo "════════ 体检明细（给 AI 看，禁止原样转述给用户）════════"
echo "流程闸门（Gate Check）：必须全部通过才能开始流程"
echo "[1] 必读文档存在（唯一真源）"
for f in RULES.md INDEX.md specs/environment-setup.md specs/migration-handoff.md specs/operator-profile-sop.md specs/product-profile-sop.md specs/threshold-method.md specs/domain-scale-sop.md specs/sequence-config.md; do
  [ -f "$KB/$f" ] && ok "文档 $f" || { bad "缺少文档 $f（环境不完整，AI 自己修，不要麻烦用户）"; note_block env 9; }
done
echo "[2] 登录凭据与当前工作空间有效"
# stdin 只能读一次：先把两行凭据读到变量，再分别喂给登录校验与工作空间校验（两者都读同一份）
CRED_BLOB=""
if [ "$CREDENTIALS_STDIN" -eq 1 ] && [ -z "$TOKEN" ] && [ -z "$ORG" ]; then
  # $(cat) 会剥掉末尾换行；用 IFS= read -r -d '' 保留原始字节（凭据须原样转发）
  IFS= read -r -d '' CRED_BLOB <&0 || true
fi
if [ "$CREDENTIALS_STDIN" -eq 1 ]; then
  if [ -n "$TOKEN" ] || [ -n "$ORG" ]; then
    bad "内部用法互斥：本次同时传了旧参数与 stdin 方式，AI 自己改，不要麻烦用户"
    note_block env 9
  elif [ -z "$CRED_BLOB" ]; then
    # ★空输入=还没收到钥匙（不是"失效"）——否则会把"用户还没粘"误报成"您的钥匙过期了"
    pending "还没收到账号钥匙（本次没有读到任何内容）：等用户粘贴后重跑"
    echo "        （给 AI：这不是失败，也没有账号问题；别让用户重新登录，只等他粘贴）"
    echo "        教程: $TOKEN_GUIDE"
    note_block need_key 1
  else
    LOGIN_OUT=$(printf '%s' "$CRED_BLOB" | python3 "$KB/tools/check_login.py" --credentials-stdin --gate-mode 2>&1)
    LOGIN_RC=$?
    [ -n "$LOGIN_OUT" ] && printf '        └─原始输出(仅供 AI，禁转述): %s\n' "$(printf '%s' "$LOGIN_OUT" | head -1)"
    # ★复审 F-09R：rc=1 可能是脚本自身崩溃（Python 未捕获异常=1）——先排除，
    #   否则会把"工具坏了"说成"您的钥匙失效"，害用户白重登
    if printf '%s' "$LOGIN_OUT" | grep -q "Traceback"; then
      bad "登录检查工具自身出错了（不是您的问题），AI 需要先排查"; note_block env 9
    elif [ "$LOGIN_RC" -eq 0 ]; then
      ok "账号钥匙有效，登录检查通过"
    else
      case "$LOGIN_RC" in
        2) bad "收到的内容不是账号钥匙的格式（用户可能粘错了东西），让用户重新复制一次"; note_block format 3 ;;
        3) bad "平台没响应（网络/接口临时问题），不是账号问题"; note_block net 5 ;;
        *) bad "账号钥匙失效或不可用（换设备登录/重新登录都会让旧钥匙作废）"; note_block login 3 ;;
      esac
    fi
  fi
elif [ -n "$TOKEN" ] || [ -n "$ORG" ]; then
  # AI 内部兼容入口；凭据会进入本进程参数，不面向用户展示。
  if [ -z "$TOKEN" ] || [ -z "$ORG" ]; then
    bad "内部用法缺参数（旧入口必须同时给两项），AI 自己改"; note_block env 9
  else
    LOGIN_OUT=$(python3 "$KB/tools/check_login.py" --token "$TOKEN" --org "$ORG" --gate-mode 2>&1)
    LOGIN_RC=$?
    [ -n "$LOGIN_OUT" ] && printf '        └─原始输出(仅供 AI，禁转述): %s\n' "$(printf '%s' "$LOGIN_OUT" | head -1)"
    if printf '%s' "$LOGIN_OUT" | grep -q "Traceback"; then
      bad "登录检查工具自身出错了（不是您的问题），AI 需要先排查"; note_block env 9
    elif [ "$LOGIN_RC" -eq 0 ]; then
      ok "账号钥匙有效，登录检查通过"
    else
      case "$LOGIN_RC" in
        2) bad "收到的内容不是账号钥匙的格式，让用户重新复制一次"; note_block format 3 ;;
        3) bad "平台没响应（网络/接口临时问题），不是账号问题"; note_block net 5 ;;
        *) bad "账号钥匙失效或不可用（换设备登录/重新登录都会让旧钥匙作废）"; note_block login 3 ;;
      esac
    fi
  fi
else
  # ★这不是"失败"——只是流程还没走到用户复制那一步；报成失败会误导成"账号有问题"
  pending "还没收到账号钥匙：等用户把一键复制的两行粘贴到聊天框后重跑"
  echo "        （给 AI：这不是失败，也没有账号问题；用户粘贴后再跑一次即可）"
  echo "        教程: $TOKEN_GUIDE"
  note_block need_key 1
fi
echo "[2b] 工作空间核对（确认客户/模板会存进您选的那个工作空间）"
if [ "$CREDENTIALS_STDIN" -eq 1 ] && [ -z "$TOKEN" ] && [ -z "$ORG" ]; then
  if [ -n "$CRED_BLOB" ]; then
    WS_OUT=$(printf '%s' "$CRED_BLOB" | python3 "$KB/tools/workspace_guard.py" --credentials-stdin --require-verified 2>&1)
    WS_RC=$?
    [ -n "$WS_OUT" ] && printf '        └─原始输出(仅供 AI，禁转述): %s\n' "$(printf '%s' "$WS_OUT" | head -1)"
    # ★F-09：rc=1 也可能是脚本自身崩溃（Python 未捕获异常=1）——先排除，别把工具故障说成"您连错空间"
    if printf '%s' "$WS_OUT" | grep -q "Traceback"; then
      bad "核对工具自身出错了（不是您的问题），AI 需要先排查"; note_block env 9
    elif [ "$WS_RC" -eq 0 ]; then
      ok "工作空间核对通过"
    else
      case "$WS_RC" in
        1) bad "钥匙有效但连到的不是要用的那个工作空间（会存错地方，禁止开始写操作）"; note_block ws 2 ;;
        2) bad "收到的内容不完整/格式不对，让用户重新复制一次"; note_block format 3 ;;
        3) bad "平台没响应，这次没核对上（不是账号问题）"; note_block net 5 ;;
        5) bad "这次没能判定（可能是钥匙已失效或平台未返回依据）——不等于空间错了，也不等于通过"; note_block unverified 6 ;;
        *) bad "平台没给出判定字段，这次没能核对（不等于通过，也不等于失败）"; note_block unverified 6 ;;
      esac
    fi
  else
    pending "还没收到账号钥匙，无法核对工作空间"
    note_block need_key 1
  fi
elif [ -n "$TOKEN" ] && [ -n "$ORG" ]; then
  WS_OUT=$(python3 "$KB/tools/workspace_guard.py" --token "$TOKEN" --org "$ORG" --require-verified 2>&1)
  WS_RC=$?
  [ -n "$WS_OUT" ] && printf '        └─原始输出(仅供 AI，禁转述): %s\n' "$(printf '%s' "$WS_OUT" | head -1)"
  if printf '%s' "$WS_OUT" | grep -q "Traceback"; then
    bad "核对工具自身出错了（不是您的问题），AI 需要先排查"; note_block env 9
  elif [ "$WS_RC" -eq 0 ]; then
    ok "工作空间核对通过"
  else
    case "$WS_RC" in
      1) bad "钥匙有效但连到的不是要用的那个工作空间（会存错地方，禁止开始写操作）"; note_block ws 2 ;;
      2) bad "收到的内容不完整/格式不对，让用户重新复制一次"; note_block format 3 ;;
      3) bad "平台没响应，这次没核对上（不是账号问题）"; note_block net 5 ;;
      5) bad "这次没能判定（可能是钥匙已失效或平台未返回依据）——不等于空间错了，也不等于通过"; note_block unverified 6 ;;
      *) bad "平台没给出判定字段，这次没能核对（不等于通过，也不等于失败）"; note_block unverified 6 ;;
    esac
  fi
else
  pending "还没收到账号钥匙，无法核对工作空间"
  note_block need_key 1
fi
echo "[3] 强制流程关键项（开始前自查）"
# ★闸门写法：多关键词规则用【token 独立检查】而非同行正则——
#   同行正则（如 "签名区.*只有昵称"）在文档换行/拆行后会误报失败（2026-09-10 实测）。
grep -q "排除中国" "$KB/RULES.md" && ok "4区排除规则已读" || { bad "RULES 缺4区排除"; note_block env 9; }
grep -q 'selectOption:"front"' "$KB/specs/domain-scale-sop.md" && ok "front保存规则已读" || { bad "domain-scale-sop 缺front"; note_block env 9; }
if grep -q "时序" "$KB/RULES.md" && grep -q "finished" "$KB/RULES.md"; then ok "时序规则已读"; else bad "RULES 缺时序规则"; note_block env 9; fi
grep -q "lfxFieldVeriable" "$KB/specs/sequence-config.md" && ok "模板code变量规则已读" || { bad "sequence-config 缺code变量"; note_block env 9; }
grep -q "搜索锚" "$KB/RULES.md" && ok "S3搜索锚规则已读" || { bad "RULES 缺S3搜索锚规则"; note_block env 9; }
if grep -q "签名/落款铁律\|签名铁律" "$KB/RULES.md" && grep -q "只有昵称" "$KB/RULES.md"; then ok "邮件签名纯昵称铁律已读"; else bad "RULES 缺邮件签名纯昵称铁律"; note_block env 9; fi
if grep -q '`draft`' "$KB/specs/product-profile-sop.md" && grep -q '`confirmed`' "$KB/specs/product-profile-sop.md" && grep -q '`declined`' "$KB/specs/product-profile-sop.md"; then ok "产品档案状态机已读"; else bad "product-profile-sop 缺状态机"; note_block env 9; fi
if [ -n "$PRODUCT" ]; then
  PROFILE="$KB/runs/$PRODUCT/product-profile.md"
  if [ -f "$PROFILE" ]; then
    STATUS=$(grep -m1 '^status:' "$PROFILE" | cut -d: -f2- | tr -d ' "')
    case "$STATUS" in confirmed|declined) ok "产品档案可续跑" ;; *) bad "产品档案未确认，需要用户看过确认后才继续"; note_block profile 4 ;; esac
  else
    bad "未找到该项目的产品档案（AI 自己核对路径）"; note_block env 9
  fi
fi
echo "[4] 未解决问题警示（仅提醒）"
[ -f "$KB/db/issues.tsv" ] && awk -F'\t' '$7=="open" && $2=="P0"{print "  [WARN] 激活前待办(本地): "$3}' "$KB/db/issues.tsv" | head -5
echo "结果: 通过=$PASS 不通过=$FAIL 还差一步=$PENDING"

# ── 给用户的白话（AI 照抄，不要改写、不要补充术语）────────────────────────
echo
echo "════════ 给用户看的这一段（AI 请照抄，别加术语）════════"
case "$BLOCK" in
  need_key)
    echo "⛔ 我先停一下——**不是您的账号有问题**，是我还没收到您复制的那两行信息。"
    echo "您只需要做一件事：回浏览器把刚才那条复制命令再执行一次，把复制到的两行直接粘贴到聊天框**回复我**。"
    echo "（这次只做了检查：没有搜索客户、没有保存、没有扣点。）" ;;
  ws)
    echo "⚠️ 检查没通过：您给的信息是有效的，但它连到的**不是您想用的那个工作空间**，我怕客户存错地方。"
    echo "您只需要做一件事：在来发信网页右上角切换到您要用的那个空间，再重新执行一次复制命令，把两行**回复我**。"
    echo "（这次只做了检查：没有搜索客户、没有保存、没有扣点。）" ;;
  format)
    echo "⚠️ 我收到的内容不完整——比如只收到了账号钥匙、没收到工作空间编号"
    echo "（有的工具会教人只复制一半；这两样**缺一不可**）。"
    echo "您只需要做一件事：用**我给您的完整复制命令**再执行一次，"
    echo "把复制到的两行整段**回复我**。"
    echo "（不用重新登录，也不用改格式；完整命令一次就能拿到两行。）" ;;
  login)
    echo "⚠️ 检查没通过：您给的登录信息用不了了（可能已过期；在别的设备登录过也会让它失效）。"
    echo "您只需要做一件事：回浏览器重新执行一次复制命令，把新复制到的两行**回复我**。"
    echo "（这次只做了检查：没有搜索客户、没有保存、没有扣点。）" ;;
  net)
    echo "⚠️ 这次没检查成功，是网络或平台临时抽风，**不是您操作错**。"
    echo "您什么都不用做，等几分钟我再试一次；如果反复出现，**回复我**说一声就行。" ;;
  unverified)
    echo "⚠️ 有一项没能确认（平台这次没返回判断依据），**不是您操作错**。"
    echo "您什么都不用做，我稍后再核对一次，确认好之前我不会保存或发送任何东西。" ;;
  profile)
    echo "ℹ️ 在正式开始前，我需要您先看一眼产品资料整理得对不对（我会把要点列给您，您回复确认或修改就行）。" ;;
  env)
    echo "ℹ️ 我这边的准备工作还差一点（我来处理，**您不用管**），处理完我再请您继续。"
    echo "目前没有动您任何数据：没搜索、没保存、没发送。**请您**先等我一下。" ;;
  *)
    echo "✅ 检查全部通过，咱们可以往下走了。" ;;
esac
echo "═══════════════════════════════════════════════════════════"
[ "$FAIL" -eq 0 ] && [ "$PENDING" -eq 0 ]
