---
doc_id: "docs-fresh-computer-checklist"
title: "全新电脑首次安装检查清单（AI 执行）"
description: "全新 Windows/macOS 首次安装的逐步自检清单：AI 照单执行，用户零命令。",
type: "guide"
status: "active"
updated: "2026-10-25"
---

# 全新电脑首次安装检查清单（AI 执行）

> 用途：在一台**从未装过**本 Skill 的 Windows 或 Mac 上，AI 按本清单逐项检查；用户不用敲命令、不用懂 Python/Git。
> 配套：[Windows/Mac 差异与报错对表](cross-platform-setup.md)、[仓库说明](../README.md)、[安装自检脚本](../tools/onboard_check.py)。

## 0. 原则（AI 必须遵守）

- **不用您敲命令**：所有检查由 AI 执行。您需要配合的只有 4 件事：回昵称+产品、装环境弹窗点「是/允许」、连账号时粘贴两行登录信息、最后回「确认激活」。
- **每一步给播报**：10–30 秒一条，说「在做什么 / 还要多久 / 您不用操作」。
- **失败先自查**：同一命令重试 1 次 → 查 `specs/problems-and-fixes-2026-10-23.md` → 仍不行就用人话说明「卡在哪、影响什么、下一步选什么」，禁止把报错原文丢给用户。
- **不要假设环境**：全新机可能没有 Python、Git、bash、curl；按下面顺序探测，缺什么由 AI 装或降级。
- **需要您点「允许」的地方**：装 Git/Python 时系统会弹「是否允许安装」，请用户点「是/允许」；连账号时按提示粘贴两行登录信息；其余全部由 AI 做。
- **下表命令全部由 AI 执行**，用户不用照着敲。

## 1. 开始前（约 1 分钟）

| # | 检查项 | Windows | macOS | 通过标准 |
|---|---|---|---|---|
| 1 | 系统与客户端 | Win10/11 + 可操作文件的 AI 客户端 | macOS 12+ + 可操作文件的 AI 客户端 | 能读写工作目录、能跑命令。**硬门：只有浏览器/不能跑命令的普通聊天 AI → 停**：换 Claude Code/Codex/ZCode，或让有权限的人代跑；本仓库无法代跑 |
| 2 | 目录可写 | 优先 `C:/laifaxin` 或 `D:/laifaxin`（短、纯英文；避开中文用户名/OneDrive/桌面）；路径过长时 `git config --global core.longpaths true` | 避开 iCloud 同步目录；用 `~/laifaxin` | 新建/删除测试文件成功 |
| 3 | 编码 | 跑 `py -X utf8 -c "print('中文 emoji ✅')"`（PowerShell 可 `$env:PYTHONUTF8='1'`，Git Bash 用 `export PYTHONUTF8=1`；**不要用 `set`**） | 默认 UTF-8 | 中文/emoji 输出不乱码 |
| 4 | 网络 | 能访问 GitHub 与 `web.laifaxin.com` | 同左 | 拉取仓库成功 |

## 2. 环境探测（约 3–8 分钟，缺什么装什么）

| # | 探测 | Windows 命令 | macOS 命令 | 缺失时 AI 怎么做 |
|---|---|---|---|---|
| 5 | Git | `git --version` | `git --version` | 缺 Git：Windows 用 `powershell -NoProfile -ExecutionPolicy Bypass -File tools/bootstrap.ps1 -Install`（会装 Git，按提示点允许）；macOS 先 `xcode-select --install`（GUI 点安装），没有 brew 就用 CLT 自带的 git |
| 6 | Python 3.9+ | `py -V`，不行再 `python -V` | `python3 -V` | 缺 Python：Windows 同样用上面的 `bootstrap.ps1 -Install`（装完重开终端，或直接用脚本返回的 `python_cmd`）；**不要自己拼 winget，没有“Add to PATH”选项**。macOS 用 `xcode-select --install`（GUI 安装） |
| 7 | bash（onboard_check 必需） | `bash --version`（必须是 Git Bash/MSYS；WSL 的 bash **不算**，缺 python3/grep 时会自动走 Python 兜底） | 系统自带 | 没有 Git Bash 时 `preflight` 可用 Python 兜底，但 `onboard_check` 会报缺依赖并 **exit 2**；必须先装 Git Bash 再做第 11 步，不能跳过 |
| 8 | 行尾 | — | — | 仓库 `.gitattributes` 已固定；不要手工改 CRLF |

## 3. 装仓库与自检（约 2–4 分钟）

| # | 动作 | Windows | macOS | 通过信号 |
|---|---|---|---|---|
| 9 | 拉取仓库 | `git clone https://github.com/tony-apan/laifaxin-b2b-sales.git`（目录名用英文） | 同左 | 看到 `README.md`、`SKILL.md`、`tools/` |
| 10 | 安装自检 | `py tools/onboard_check.py` | `python3 tools/onboard_check.py` | **退出码 0** 才算通过；⚠️「安装/学习自检完成」在缺依赖时也会打印，不能只看这句话。需要 Python（`py`/`python3` 任一可运行）+ curl + bash + grep + awk |
| 11 | 提交钩子（可选） | Git Bash 里 `bash tools/install_hooks.sh` | `bash tools/install_hooks.sh` | 之后 commit/push 前自动自检 |

> **维护者交付前（不属安装流程）**：`py tools/preflight.py` 末行 `PREFLIGHT PASS`、退出码 0。这是发布门，安装时不跑、不对用户提；Windows 上失败按已知欠账单独记录。

## 4. 进入业务流程（AI 按 SKILL.md 路由）

1. **读必读**：`SKILL.md`、`RULES.md`、`CORE-POINTS.md`、`specs/beginner-flow.md`、`specs/novice-flow-contract.md`、`specs/problems-and-fixes-2026-10-23.md`；有网站再读 `specs/website-profile-sop.md`。
2. **第 0 屏**：照 `output-templates/S0-install-report.md` 全文说，不得自行删句（首句照模板原文，不自造）+ 能帮什么 + **有人回复不会自动停** + 发信要您点头 + 问「昵称 + 产品」两样（不展示菜单、不要数字）。
3. **登记开工**：拿到昵称+产品后运行 `py tools/startup_gate.py ack --nickname <昵称> --product <产品>`（macOS 用 `python3`）；未登记时所有写操作会被工具拒绝。
4. **第 1 屏**：给 6 步全景 + 当前第 1 步 + 大约还要回几次 + 该回什么。

## 5. 成功判定（除标注「维护者可选」外全部满足，才算「新电脑可用」）

- [ ] `onboard_check` **退出码 0**，无红色阻断项（仅看「自检完成」字样不算通过）
- [ ] 第 0 屏话术与 `output-templates/S0-install-report.md` 一致
- [ ] 用户已回昵称+产品，`startup_gate.py ack` 成功
- [ ] 第 1 屏发出，用户知道「现在第几步、该回什么」

## 6. 失败对表（先自查，再升级）

| 现象 | 最可能原因 | 处理 |
|---|---|---|
| `python3` 不是内部命令 | Windows 没有 python3 别名 | 改用 `py`，或装 Python 时勾 Add to PATH |
| `python3` 存在却报「Python was not found」/ 退出码 49 | Windows 应用商店占位符 | 改用 `py`；仓库脚本会自动跳过占位符 |
| `bash` 找不到 | Windows 没装 Git Bash | 先装 Git Bash 再重跑 `onboard_check`（`preflight` 是维护者发布门，不能修安装门）；钩子暂不装 |
| 中文/emoji 乱码 | 控制台编码不是 UTF-8 | PowerShell `$env:PYTHONUTF8='1'` 或 Git Bash `export PYTHONUTF8=1` 后重跑 |
| `Permission denied`（钩子） | 脚本无执行位 | Git Bash 里 `chmod +x .githooks/*` |
| `onboard_check` 打印「自检完成」但退出码 2 / 缺 curl、bash、grep、awk | 环境依赖没齐 | 装 Git Bash（自带 grep/awk/curl）或对应工具后重跑；**不能跳过**（AGENTS 硬门：未通过不得开始），确实装不上就先停下问作者 |
| 自检较慢 | `onboard_check` 正常 30 秒内；超过 2 分钟多半卡在版本检查 | 播报「正在自检，约 1 分钟，您不用操作」 |

## 7. 证据留存

新电脑首次成功安装后，把下面三项记到项目档案或反馈给作者：

1. 系统版本 + Python 版本（`py -V` 或 `python3 -V` 的输出）
2. `onboard_check` 退出码 0 的输出（安装门证据）
3. 任何与本清单不一致的地方（命令写法、乱码、路径问题）

> 说明：本清单覆盖 Windows/macOS 的**静态适配与可复现检查**；Windows 全新实机的完整业务流程仍需首次使用者反馈，见 [cross-platform-setup.md](cross-platform-setup.md) 第 7 节。
