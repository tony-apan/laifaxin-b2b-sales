---
doc_id: "docs-cross-platform-setup"
title: "Windows 与 macOS 通用上手说明"
description: "Windows/macOS 通用上手：Python 命令写法、Git Bash 与钩子、编码换行、自检命令与常见报错对表。"
type: "guide"
status: "active"
updated: "2026-10-25"
---

# Windows 与 macOS 通用上手说明

> **这页是给 AI 的跨平台排障表，用户不用照着敲命令。** AI 碰到系统差异时照这张表处理，就不会卡在「python3 不是内部命令」「bash 不存在」「中文乱码」这些坑上。

## 1. 先确认 Python（只需一次）

| 系统 | 先试这条 | 成功标志 |
|---|---|---|
| Windows | `py -V`，不行再 `python -V` | 显示 Python 3.9 或更高 |
| macOS | `python3 -V` | 同上 |

没有 Python？由 AI 处理：Windows 统一用 `powershell -NoProfile -ExecutionPolicy Bypass -File tools/bootstrap.ps1 -Install`（安装时按提示点「允许」，装完重开终端或用脚本返回的 `python_cmd`；不要自己拼 winget，也没有「Add to PATH」选项）；macOS 先 `xcode-select --install` 再重试。

**本仓库所有 Python 命令的写法**：Windows 把 `python3` 换成 `py`（或 `python`），macOS/Linux 保持 `python3`。

## 2. 自检命令（两个门，别混）

- **安装门（用户装完）**：Windows `py tools/onboard_check.py`；macOS / Linux `python3 tools/onboard_check.py`。**退出码 0** 才算通过。
- **发布门（维护者改完仓库）**：Windows `py tools/preflight.py`（正斜杠，Git Bash 不吞路径）；macOS / Linux `python3 tools/preflight.py`。末行 `PREFLIGHT PASS` 才算通过。**安装阶段不跑，失败也不等于没装好。**

旧版 Unix 也可用 `bash tools/preflight.sh`，内容相同：文档引用核验 + 全量测试 + 规则检查。

## 3. Git 钩子（可选，但推荐）

- 两个系统相同：装好 Git 后，在仓库根目录跑一次 `bash tools/install_hooks.sh`（Windows 用 Git 自带的 Git Bash）。
- 之后每次提交/推送前自动跑自检；应急跳过用 `SKIP_PREFLIGHT=1 git commit ...`。
- Windows 没装 Git Bash 时钩子无法执行：改用第 2 节的 `py tools/preflight.py` 手动跑发布门，不影响业务。

## 4. 编码与换行（仓库已统一）

- `.gitattributes` 固定行尾：脚本/文档用 LF，`.ps1` 用 CRLF，Windows 检出后 bash 脚本不会因 `\r` 报错。
- Windows 控制台若中文/emoji 乱码：跑 `py -X utf8 -c "print('中文 emoji ✅')"`；PowerShell 用 `$env:PYTHONUTF8='1'`、Git Bash 用 `export PYTHONUTF8=1`（`set` 在 PowerShell/Git Bash 都不是环境变量）。
- 路径一律用仓库相对路径（`tools\...` 或 `tools/...`），不要手写 `C:\Users\...`、`/Users/...` 这类本机绝对路径。

## 5. 常见报错对表

| 报错/现象 | Windows | macOS |
|---|---|---|
| 找不到 `python3` | 改用 `py` 或 `python` | `xcode-select --install` 后重试 |
| `python3` 存在却报「Python was not found」/ 退出码 49 | 微软商店占位符：改用 `py`；仓库脚本会自动跳过占位符 | 一般不出现 |
| 找不到 `bash` | `preflight` 用 `py tools/preflight.py`（会走 Python 兜底）；但 `onboard_check` 会 exit 2——先装 Git for Windows 的 Git Bash（WSL 的 bash 不算） | 系统自带 bash，直接跑 |
| 中文/emoji 乱码 | 用 `py -X utf8 ...`，或 PowerShell `$env:PYTHONUTF8='1'` / Git Bash `export PYTHONUTF8=1` | 一般无需处理 |
| 钩子 `Permission denied` | Git Bash 里 `chmod +x .githooks/*` | `chmod +x .githooks/*` |
| 脚本报 `\r` 相关错误 | `git config core.autocrlf false` 后重新检出 | 一般不会出现 |

## 6. 新手只需要记住三件事（用户视角）

1. 装好后让 AI 跑一次安装自检；通过后 AI 会告诉您「可以开始」——您不需要自己看任何命令输出。
2. 您只需要回昵称、产品、编号确认；命令都交给 AI。
3. 换电脑：重装环境 → 跑自检 → 让 AI 继续旧项目（本地项目数据不要删）。

## 7. Windows 实机验证状态（证据边界）

- 本仓库 CI 在 ubuntu 跑 bash 与 python 两个入口；windows-latest 另有一个**非阻断冒烟** job（`continue-on-error`），用于积累 Windows 证据，不作为验收门。
- **尚未在全新 Windows 实机跑完整个业务流程**。首次在 Windows 验收时，由维护者/复现者提供 `py tools/preflight.py` 的输出和系统差异反馈给作者；AI 在安装首屏不运行、不提及它。在此之前，Windows 按「静态适配 + 对表排障」理解，不宣称已实机验收。
- 因此 `preflight` 在 Windows 上失败属于已知欠账，**不作为安装验收门**；安装门只看 `onboard_check` 退出码 0。
