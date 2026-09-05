---
title: "环境就绪 SOP（AI 执行·零 Python 前提 bootstrap）"
description: "全新电脑（可能连 Python 都没有）由 AI 完成环境就绪的完整 SOP：bootstrap 悖论与解法、Windows/Unix 入口判断、check-only→install→复查流程、Python launcher 解析优先顺序、错误分级与处置。命令全部可复制，AI 执行，不让用户手工敲。"
created: 2026-09-04
updated: 2026-09-04
author: "AI Agent"
source: "bootstrap.sh / bootstrap.ps1 实操设计"
related: [RULES.md, ../tools/bootstrap.sh, ../tools/bootstrap.ps1, migration-handoff.md]
tags: [环境, bootstrap, SOP, 新电脑, 零Python, AI优先]
status: partial
audience: AI优先
---

# 🧰 环境就绪 SOP（AI 执行·零 Python 前提）

> **一句话**：本仓库的引导脚本 `onboard_check.py` 是 Python 写的，但**装 Python 这件事不能依赖 Python**——所以环境就绪的起点是 `tools/bootstrap.sh`（bash）或 `tools/bootstrap.ps1`（PowerShell），两者都只用操作系统自带的能力，**全新电脑没有 Python 也能跑**。
> **给谁看**：AI（执行者）。所有命令由 AI 复制执行；只有需要用户输 sudo 密码或点图形安装器时才提示用户。
> **Windows 验证边界**：`bootstrap.ps1` 已完成静态结构/参数检查，但当前开发环境无 Windows/pwsh，尚未在全新 Windows 实机完成 `CheckOnly→Install→复查→onboard`；执行失败时按本 SOP E2/E3 使用官方安装兜底，不得宣称 Windows 已实测。

## 0. bootstrap 悖论（为什么需要这两个脚本）

- 仓库的正式入口 `onboard_check.py` / `check_login.py` / `gate_check.sh` 都要求环境已就绪（python3 + curl + bash + grep + awk）。
- 但"检查环境的脚本"如果本身要求环境，就陷入死循环：**没有 Python 的电脑跑不了检查 Python 的脚本**（bootstrap 悖论）。
- 解法：把"环境就绪"这一步降到操作系统自带能力——bash（macOS/Linux/Git Bash/WSL 自带）和 PowerShell（Windows 自带）。`bootstrap.sh`/`bootstrap.ps1` 只用 shell 内建 + `command -v`/`Get-Command` 探测 + 包管理器安装，**零 Python 前提**。
- `onboard_check.py` **不是安装器**：它只能在 Python 已可运行后做检查与引导；环境没就绪时它自己都跑不起来。顺序永远是：**bootstrap → onboard_check**。

## 1. 入口判断（AI 第一步：判断当前环境走哪个脚本）

| 判断依据 | 环境 | 走哪个脚本 |
|---|---|---|
| AI 会话在 Windows 的 PowerShell（提示符/`$PSVersionTable` 可用、路径是 `C:\...`） | Windows 原生 | `tools/bootstrap.ps1` |
| AI 会话在 bash（提示符/`uname` 可用）且 `uname -s` = `Darwin` | macOS | `tools/bootstrap.sh` |
| bash 且 `uname -s` = `Linux`（含 `/proc/version` 含 microsoft 或有 `WSL_DISTRO_NAME`） | Linux / WSL | `tools/bootstrap.sh` |
| bash 且 `uname -s` 以 `MINGW`/`MSYS`/`CYGWIN` 开头 | Windows Git Bash | `tools/bootstrap.sh`（可探测；但**装缺依赖要转 `bootstrap.ps1`**，Git Bash 无包管理器） |

> 不确定时先跑 `uname -s`（bash）或 `$PSVersionTable.PSVersion`（PowerShell）再决定。Windows 用户没有 Git Bash 也**不需要先装它**：`bootstrap.ps1` 会用 winget 装 Git for Windows（自带 bash/grep/awk）。

## 2. 标准流程：check-only → install → 复查 → onboard_check

### 2.1 Windows PowerShell（含无 Git Bash/无 WSL 的全新电脑）

```powershell
# ① 只探测（第一次永远先跑这个；-ExecutionPolicy Bypass 只对本次进程生效，不改系统设置）
powershell -NoProfile -ExecutionPolicy Bypass -File tools\bootstrap.ps1 -CheckOnly

# ② 有缺失 → 安装（winget 装 Python.Python.3.12 和 Git.Git；Git for Windows 顺带提供 bash/grep/awk）
powershell -NoProfile -ExecutionPolicy Bypass -File tools\bootstrap.ps1 -Install

# ③ 安装后复查（脚本会刷新 PATH 并搜索常见安装路径，无需重启/无需新开终端；仍缺才需新开一次终端）
powershell -NoProfile -ExecutionPolicy Bypass -File tools\bootstrap.ps1 -CheckOnly

# ④ 全绿后，用脚本输出的 python_cmd 跑自检引导（py/python/python3 之一）
py tools\onboard_check.py
```

- **不启用 WSL、不要求重启**：缺 bash/grep/awk 由 Git for Windows（winget 安装 Git.Git）补齐，不动 WSL。
- **无 winget** → 脚本明确失败并给出官网链接（Python：https://www.python.org/downloads/ ，勾选 "Add python to PATH"；Git：https://git-scm.com/download/win ）。AI 把链接和要点讲给用户、由用户图形界面安装，装完 AI 重跑 ③ 复查。
- **执行策略被挡**（报 "running scripts is disabled on this system"）→ 用上面的 `powershell -NoProfile -ExecutionPolicy Bypass -File ...` 一次性形式（只影响本次进程）。**脚本和 AI 都不得修改系统执行策略**。

### 2.2 macOS / Linux / WSL

```bash
# ① 只探测（第一次永远先跑这个）
bash tools/bootstrap.sh --check-only

# ② 有缺失 → 安装（自动选择 brew/apt-get/dnf/yum/pacman/apk；需要 sudo 时正常使用 sudo）
bash tools/bootstrap.sh --install

# ③ 安装后复查（脚本已刷新命令缓存；sudo 装完通常立即可见）
bash tools/bootstrap.sh --check-only

# ④ 全绿后，用脚本输出的 python_cmd 跑自检引导（python3/python 之一）
python3 tools/onboard_check.py
```

- **macOS 无 Homebrew** → 脚本**不会自动安装 Homebrew**（策略约束），明确失败并给出：Python 官方包 https://www.python.org/downloads/ ；git 可用 Apple 命令行工具 `xcode-select --install`；或用户同意后手动装 Homebrew（https://brew.sh ）再重跑 ②。
- **Git Bash（MINGW/MSYS）里发现缺失** → Git Bash 没有包管理器，脚本会明确失败并引导转 PowerShell 跑 `bootstrap.ps1 -Install`。

### 2.3 退出码与稳定输出（AI 解析约定）

两个脚本语义一致：**exit 0=全部就绪；1=仍有缺失（含无法自动安装）；2=参数错误**。结尾固定输出 `# ---- bootstrap summary (key=value) ----` 块（`python_cmd / python_ok / curl_ok / bash_ok / grep_ok / awk_ok / git_ok / missing / all_ok / install_result` 等 key 名稳定，勿解析人类可读行）。**`python_cmd` 就是后续所有节点该用的实际 Python 命令**。

## 3. 依赖边界：主流程零第三方包，但需要 OS 工具

- 主流程工具（`check_login.py`/`save_first_n.py`/`gen_templates.py`/`verify_*`/`flow_orchestrator.py` 等）= **纯 Python 标准库 + subprocess 调 curl**，`pip install` 一律不需要。
- 但必须有 OS 工具：**python3 + curl + bash + grep + awk + git**（gate_check.sh 依赖 grep/awk；工具全部用 curl 调 API；git 用于取仓库）。
- `requirements.txt`（playwright）只服务研究/抓包脚本，**环境就绪阶段不装**。

## 4. Python launcher 解析优先顺序（跨平台约定）

| 平台 | 优先顺序 | 说明 |
|---|---|---|
| Windows | `py` → `python` → `python3` | `py` 是官方 Python launcher（装 Python 勾选默认项就有）；`py -3` 可指定大版本。防呆：Windows 商店占位别名会打印 "Python was not found" 且退出码非 0，bootstrap.ps1 已按退出码过滤，不误判为可用 |
| macOS / Linux / WSL | `python3` → `python` | `python` 在老系统可能指向 Python 2 或不存在，必须验证 `--version` 以 `Python 3` 开头才算可用（bootstrap.sh 已做） |

AI 规则：**以 bootstrap 输出的 `python_cmd` 为准**，后续所有命令里的 `python3`/`py` 都替换成它；跨会话不要凭记忆换命令。

## 5. 错误分级与处置（bootstrap 阶段）

| 级别 | 现象（脚本行为） | AI 处置 |
|---|---|---|
| **E0 参数错**（exit 2） | 未知参数 / 同时给两个模式开关 | 修正命令重跑；这是 AI 自己的调用错误，不惊动用户 |
| **E1 装后仍缺**（install 后 exit 1，`missing` 非空） | 包管理器装了但探测仍失败 | 按脚本提示：新开一次终端（PATH 刷新）后重跑 check-only；Windows 里 `python_cmd` 可能已是全路径，直接用全路径跑 onboard_check；仍失败→E2 路径 |
| **E2 无法自动安装**（`install_result=no_pm`/`no_winget`） | macOS 无 brew / Git Bash 无包管理器 / Linux 无已知包管理器 / Windows 无 winget | 脚本已打印官方下载地址：AI 把地址+勾选项（Add python to PATH）讲给用户，用户图形界面安装后 AI 重跑 check-only 复查；**不自动安装 Homebrew**；Windows 无 winget 可从 Microsoft Store 装 "App Installer" 后重试 |
| **E3 执行策略阻挡**（仅 PowerShell） | "running scripts is disabled…" | 改用 `powershell -NoProfile -ExecutionPolicy Bypass -File ...` 一次性形式；**不改系统策略、不提权** |
| **E4 sudo 需要密码/失败** | `sudo` 等待输入或报错 | Linux/WSL 正常现象：告知用户在终端输入密码，或让用户先手动 `sudo -v`；失败（无 sudo 权限）→ 转 E2 官方包/用户级安装 |
| **E5 网络失败** | curl/winget/包管理器下载超时 | 先重试一次；仍失败换网络/镜像源后重试；明确告知用户是网络问题，不是脚本或 token 问题 |
| **E6 版本不可用** | python 存在但 `--version` 非 `Python 3`（如 Python 2） | 视为缺失，走 install 装新版；并存时 Windows 用 `py -3`、Unix 用 `python3` |

## 6. 完成就绪后

1. 跑 `python3 tools/onboard_check.py`（Windows 用 bootstrap 给出的 `python_cmd`）：输出环境自检 + 可续接项目扫描（`runs/*/*/operation-record.md`，排除 `_template`）+ 新会话引导。
2. 若是**换电脑续接**（恢复过 `.local/`、`runs/`、`db/`），接着读 [migration-handoff.md](migration-handoff.md) 做迁移校验；冷启动则按 onboard_check 输出的新项目引导走（token → check_login → gate_check → flow_orchestrator）。
3. 环境结论要向用户汇报成一句话（人话）：缺什么、装了什么、下一步做什么；技术细节留在 AI 侧。
