#!/usr/bin/env bash
# ★ 环境引导（bootstrap）——零 Python 前提：本脚本只用 bash 自身探测/安装环境，全新电脑没有 Python 也能由 AI 直接执行。
# 用法（给 AI；用户不手工敲）:
#   bash tools/bootstrap.sh --check-only   # 只探测，不安装（第一步先跑这个）
#   bash tools/bootstrap.sh --install      # 用检测到的包管理器安装缺失项（brew/apt-get/dnf/yum/pacman/apk），需要 sudo 时正常使用 sudo
#   bash tools/bootstrap.sh                # 不带参数 = --check-only
# 退出码: 0=全部就绪  1=仍有缺失（含"无包管理器无法自动安装"）  2=参数错误
# 输出: 结尾固定输出稳定 key=value 摘要（含实际可用的 Python 命令 python_cmd=...）
# 平台: macOS / Linux / WSL / Windows Git Bash。不自动安装 Homebrew；Git Bash 无包管理器 → 明确失败并给官方下载地址。
# 配套 SOP: specs/environment-setup.md（入口判断/错误分级/安装后复查）；换机续接见 specs/migration-handoff.md
set -u

usage() {
  cat <<'EOF'
用法: bash tools/bootstrap.sh [--check-only|--install]
  --check-only  只探测 python3/python、curl、bash、grep、awk、git，不安装（第一步先跑这个）
  --install     用检测到的包管理器（brew/apt-get/dnf/yum/pacman/apk）安装缺失项；需要 sudo 时正常使用 sudo
  （不带参数 = --check-only）
退出码: 0=全部就绪  1=仍有缺失/无法自动安装  2=参数错误
平台: macOS / Linux / WSL / Windows Git Bash；不自动安装 Homebrew；Git Bash 无包管理器 → 明确失败+官方下载地址
SOP: specs/environment-setup.md
EOF
}

MODE="check-only"
case "${1:-}" in
  "")            MODE="check-only" ;;
  --check-only)  MODE="check-only" ;;
  --install)     MODE="install" ;;
  -h|--help)     usage; exit 0 ;;
  *)             echo "❌ 未知参数: $1（只支持 --check-only / --install）"; usage; exit 2 ;;
esac
if [ $# -ge 2 ]; then echo "❌ 参数过多（一次只接受一个模式参数）"; usage; exit 2; fi

PY_URL="https://www.python.org/downloads/"
GIT_URL="https://git-scm.com/downloads"
CLT_CMD="xcode-select --install"

# ---------- 平台探测 ----------
uname_s="$(uname -s 2>/dev/null || echo unknown)"
uname_m="$(uname -m 2>/dev/null || echo unknown)"
OS="unknown"
case "$uname_s" in
  Darwin*)  OS="macos" ;;
  Linux*)
    if grep -qi microsoft "/proc/version" 2>/dev/null || [ -n "${WSL_DISTRO_NAME:-}" ] || [ -n "${WSL_INTEROP:-}" ]; then OS="wsl"; else OS="linux"; fi ;;
  MINGW*|MSYS*|CYGWIN*) OS="gitbash" ;;
  *)        OS="unknown" ;;
esac
# 注: 变量后紧跟中文全角字符时必须用 ${VAR} 写法（部分 locale 会把多字节字符当变量名一部分）

# ---------- 包管理器探测（按优先级；不自动安装任何包管理器，包括 Homebrew）----------
PM=""
for m in brew apt-get dnf yum pacman apk; do
  if command -v "$m" >/dev/null 2>&1; then PM="$m"; break; fi
done
# Windows Git Bash 里没有 pacman 等包管理器（上面的 command -v 自然找不到）→ PM 为空 = 无法自动安装

# ---------- 探测函数 ----------
PYTHON_CMD=""; PYTHON_VER=""
probe_python() {
  PYTHON_CMD=""; PYTHON_VER=""
  local c ver
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then
      ver="$("$c" --version 2>&1 || true)"
      case "$ver" in
        "Python 3"*) PYTHON_CMD="$c"; PYTHON_VER="$ver"; return 0 ;;
      esac
    fi
  done
  return 1
}
have() { command -v "$1" >/dev/null 2>&1; }

probe_python
CURL_OK=0;  have curl  && CURL_OK=1
BASH_OK=0;  have bash  && BASH_OK=1
GREP_OK=0;  have grep  && GREP_OK=1
AWK_OK=0;   have awk   && AWK_OK=1
GIT_OK=0;   have git   && GIT_OK=1
PY_OK=0;    [ -n "$PYTHON_CMD" ] && PY_OK=1

missing_list() {
  local out=""
  [ "$PY_OK"   -eq 0 ] && out="$out python"
  [ "$CURL_OK" -eq 0 ] && out="$out curl"
  [ "$BASH_OK" -eq 0 ] && out="$out bash"
  [ "$GREP_OK" -eq 0 ] && out="$out grep"
  [ "$AWK_OK"  -eq 0 ] && out="$out awk"
  [ "$GIT_OK"  -eq 0 ] && out="$out git"
  echo "$out" | sed 's/^ *//'
}

echo "🛠 环境引导 bootstrap — 模式=${MODE}"
echo "   平台: OS=$OS (uname=$uname_s, arch=$uname_m)  包管理器: ${PM:-无}"

# ---------- 安装（仅 --install 且有缺失时）----------
INSTALL_RESULT="not_attempted"
if [ "$MODE" = "install" ]; then
  NEED="$(missing_list)"
  if [ -z "$NEED" ]; then
    INSTALL_RESULT="nothing_to_do"
    echo "✔ 无缺失项，不需要安装"
  else
    echo "→ 待安装: $NEED"
    case "$OS" in
      macos)
        if [ "$PM" = "brew" ]; then
          PKGS=""
          [ "$PY_OK"   -eq 0 ] && PKGS="$PKGS python3"
          [ "$CURL_OK" -eq 0 ] && PKGS="$PKGS curl"
          [ "$BASH_OK" -eq 0 ] && PKGS="$PKGS bash"
          [ "$GREP_OK" -eq 0 ] && PKGS="$PKGS grep"
          [ "$AWK_OK"  -eq 0 ] && PKGS="$PKGS gawk"
          [ "$GIT_OK"  -eq 0 ] && PKGS="$PKGS git"
          echo "→ brew install$PKGS"
          if brew install $PKGS; then INSTALL_RESULT="attempted"; else INSTALL_RESULT="failed"; echo "⚠ brew 安装有失败项，看上面日志"; fi
        else
          INSTALL_RESULT="no_pm"
          echo "❌ 无法自动安装：macOS 上未检测到 Homebrew（按约定不自动安装 Homebrew）。"
          echo "   · Python 官方安装包: $PY_URL"
          echo "   · git 可用 Apple 官方命令行工具（装完含 git）: $CLT_CMD"
          echo "   · 或先手动装 Homebrew（https://brew.sh）后重跑: bash tools/bootstrap.sh --install"
        fi ;;
      linux|wsl)
        case "$PM" in
          apt-get|dnf|yum)
            SUDO=""
            [ "$(id -u)" != 0 ] && SUDO="sudo"
            PKGS=""
            [ "$PY_OK"   -eq 0 ] && PKGS="$PKGS python3"
            [ "$CURL_OK" -eq 0 ] && PKGS="$PKGS curl"
            [ "$BASH_OK" -eq 0 ] && PKGS="$PKGS bash"
            [ "$GREP_OK" -eq 0 ] && PKGS="$PKGS grep"
            [ "$AWK_OK"  -eq 0 ] && PKGS="$PKGS gawk"
            [ "$GIT_OK"  -eq 0 ] && PKGS="$PKGS git"
            if [ "$PM" = "apt-get" ]; then
              echo "→ $SUDO apt-get update && $SUDO apt-get install -y$PKGS"
              if [ -n "$SUDO" ]; then $SUDO apt-get update && $SUDO apt-get install -y $PKGS; else apt-get update && apt-get install -y $PKGS; fi \
                && INSTALL_RESULT="attempted" || INSTALL_RESULT="failed"
            else
              echo "→ $SUDO $PM install -y$PKGS"
              if [ -n "$SUDO" ]; then $SUDO "$PM" install -y $PKGS; else "$PM" install -y $PKGS; fi \
                && INSTALL_RESULT="attempted" || INSTALL_RESULT="failed"
            fi ;;
          pacman)
            SUDO=""
            [ "$(id -u)" != 0 ] && SUDO="sudo"
            PKGS=""
            [ "$PY_OK"   -eq 0 ] && PKGS="$PKGS python"
            [ "$CURL_OK" -eq 0 ] && PKGS="$PKGS curl"
            [ "$BASH_OK" -eq 0 ] && PKGS="$PKGS bash"
            [ "$GREP_OK" -eq 0 ] && PKGS="$PKGS grep"
            [ "$AWK_OK"  -eq 0 ] && PKGS="$PKGS gawk"
            [ "$GIT_OK"  -eq 0 ] && PKGS="$PKGS git"
            echo "→ $SUDO pacman -S --noconfirm$PKGS"
            if [ -n "$SUDO" ]; then $SUDO pacman -S --noconfirm $PKGS; else pacman -S --noconfirm $PKGS; fi \
              && INSTALL_RESULT="attempted" || INSTALL_RESULT="failed" ;;
          apk)
            SUDO=""
            [ "$(id -u)" != 0 ] && SUDO="sudo"
            PKGS=""
            [ "$PY_OK"   -eq 0 ] && PKGS="$PKGS python3"
            [ "$CURL_OK" -eq 0 ] && PKGS="$PKGS curl"
            [ "$BASH_OK" -eq 0 ] && PKGS="$PKGS bash"
            [ "$GREP_OK" -eq 0 ] && PKGS="$PKGS grep"
            [ "$AWK_OK"  -eq 0 ] && PKGS="$PKGS gawk"
            [ "$GIT_OK"  -eq 0 ] && PKGS="$PKGS git"
            echo "→ $SUDO apk add$PKGS"
            if [ -n "$SUDO" ]; then $SUDO apk add $PKGS; else apk add $PKGS; fi \
              && INSTALL_RESULT="attempted" || INSTALL_RESULT="failed" ;;
          *)
            INSTALL_RESULT="no_pm"
            echo "❌ 无法自动安装：Linux/WSL 上未检测到包管理器（apt-get/dnf/yum/pacman/apk 均无）。"
            echo "   · Python: $PY_URL   · Git: $GIT_URL"
            [ "$OS" = "wsl" ] && echo "   · WSL 提示: Ubuntu 等 Debian 系发行版通常自带 apt-get；确认没有装精简版容器环境" ;;
        esac ;;
      gitbash)
        INSTALL_RESULT="no_pm"
        echo "❌ 无法自动安装：Git Bash 没有包管理器（pacman 不可用）。"
        echo "   请改在 Windows PowerShell 跑 Windows 版引导（用 winget 自动装 Python/Git）:"
        echo "     powershell -NoProfile -ExecutionPolicy Bypass -File tools\\bootstrap.ps1 -CheckOnly"
        echo "     powershell -NoProfile -ExecutionPolicy Bypass -File tools\\bootstrap.ps1 -Install"
        echo "   · Python 官方安装包: $PY_URL   · Git for Windows: https://git-scm.com/download/win" ;;
      *)
        INSTALL_RESULT="no_pm"
        echo "❌ 无法自动安装：未识别的平台（uname=$uname_s）。"
        echo "   · Python: $PY_URL   · Git: $GIT_URL" ;;
    esac
    # 安装后清掉 bash 的命令缓存再复查
    hash -r 2>/dev/null || true
  fi
fi

# ---------- 安装后复查（--install 必做；--check-only 就是首次探测结果）----------
probe_python
CURL_OK=0;  have curl  && CURL_OK=1
BASH_OK=0;  have bash  && BASH_OK=1
GREP_OK=0;  have grep  && GREP_OK=1
AWK_OK=0;   have awk   && AWK_OK=1
GIT_OK=0;   have git   && GIT_OK=1
PY_OK=0;    [ -n "$PYTHON_CMD" ] && PY_OK=1
MISSING="$(missing_list)"
ALL_OK=0; [ -z "$MISSING" ] && ALL_OK=1

# ---------- 人读摘要 ----------
echo ""
echo "📋 环境摘要（${MODE}）:"
if [ -n "$PYTHON_CMD" ]; then
  echo "   ✅ Python 可用: 实际命令 = $PYTHON_CMD （${PYTHON_VER}）——后续节点都用这个命令"
else
  echo "   ❌ Python 不可用（python3/python 都没找到或不是 Python 3）"
fi
for t in curl bash grep awk git; do
  eval "v=\$$(echo $t | tr 'a-z' 'A-Z')_OK"
  if [ "$v" = "1" ]; then echo "   ✅ $t"; else echo "   ❌ $t 缺失"; fi
done
if [ "$ALL_OK" = "1" ]; then
  echo "   🟢 全部就绪。下一步: $PYTHON_CMD tools/onboard_check.py（新会话自检引导）"
else
  echo "   🔴 仍缺: $MISSING"
  case "$MODE" in
    check-only) echo "      👉 AI 决策: 缺的是 python/curl/git → 跑 bash tools/bootstrap.sh --install；无包管理器 → 按脚本给出的官方地址装（见上）" ;;
    install)    echo "      👉 安装后仍缺 → 按错误分级处理（specs/environment-setup.md）: 换包管理器/官方安装包/让用户在图形界面装后重跑 --check-only 复查" ;;
  esac
fi

# ---------- 稳定 key=value 输出（供 AI/脚本解析；不要改动这些 key 名）----------
echo ""
echo "# ---- bootstrap summary (key=value) ----"
echo "mode=$MODE"
echo "os=$OS"
echo "platform=$uname_s/$uname_m"
echo "package_manager=${PM:-none}"
echo "install_result=$INSTALL_RESULT"
echo "python_cmd=${PYTHON_CMD:-none}"
echo "python_version=${PYTHON_VER:-none}"
echo "python_ok=$PY_OK"
echo "curl_ok=$CURL_OK"
echo "bash_ok=$BASH_OK"
echo "grep_ok=$GREP_OK"
echo "awk_ok=$AWK_OK"
echo "git_ok=$GIT_OK"
echo "missing=${MISSING:-none}"
echo "all_ok=$ALL_OK"

[ "$ALL_OK" = "1" ] && exit 0 || exit 1
