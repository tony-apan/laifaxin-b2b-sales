---
doc_id: "docs-15-live-run-pitfalls"
title: "实测踩坑速查（真机全流程跑完后的清单）"
description: "按症状查原因和处理：远程 Windows、token、票据目录、加人、收口证据、排除抽验。"
type: "guide"
status: "active"
updated: "2026-10-26"
related: ["../START-HERE.md", "cross-platform-setup.md"]
---

# 实测踩坑速查（真机跑完一轮后整理）

> 来源：2026-10-26 在远程 Windows 上真实跑完「椰子」全流程（建 48 模板 / 12 轮序列 / 加 2 联系人 / 收口到激活前）踩到的全部问题。
> 用法：**按症状查**。每条都给「现在该怎么做」；标 ✅ 的已修进代码并推送。

| # | 症状（你看到的） | 真因 | 现在怎么做 |
|---|---|---|---|
| 1 | 远程执行长命令没输出、引号被吃掉 | SSH 里再套 `bash -lc "..."`，内层双引号层层转义，命令被截断 | 不写长内联命令。把 Python 探针/驱动写成 `.py` → `scp` 上传 → 只执行 `py -3 <文件>` |
| 2 | Windows 输出中文/emoji 报 UnicodeEncodeError | 控制台/管道默认 GBK | 脚本首部统一 `sys.stdout.reconfigure(encoding="utf-8")`（工具内已内置） |
| 3 | token 不想落盘/不想进命令行 | argv 会被历史与日志记录 | 凭据只走 stdin：父进程读本地凭据文件，子进程 `sys.stdin.readline()`；不改写 `--token STDIN` 占位就不会真带 token |
| 4 | `E_AUTH_NO_TICKET: 票据文件不存在: ...\.local\auth\.local\auth\ticket-*.json` | 调用 `auth_guard.authorize(..., root=...)` 时把 root 传成了 `.local/auth`，票据在里层又建一套目录 | **root 传仓库根**（`ROOT`），票据会落在 `<root>/.local/auth/`；看到双层路径先删多余空目录再重试 |
| 5 | `DEPRECATED: use save_guard` | 用了已封条的旧加人脚本 | 加人走 `tools/contact_add_authorized.py`，需要 `--plan` + `--auth-ticket` + `--approval`；旧 `contact_add.py` 只作流程核对 |
| 6 | 审批卡里回「1」被判无效 | 只有 S7/S9/S10 接受纯数字；S5 要含「确认保存 前 N 家」，S12 要含「确认激活」 | 按卡面提示回；S7/S9/S10 回 `1` 即可（已加测试覆盖） |
| 7 | `E_AUTH_REUSED` / 重跑被拒 | 票据和审批是一次性的，hash 绑定了当次参数 | 正常保护。参数变了就重新授权一次，不复用旧票据 |
| 8 | 保存任务刚提交就报「没数据」 | 保存是异步的，`front` 提交后要等 `status:finished` | 轮询到 finished 再对账（`contactSaveCount`），别提前读 |
| 9 | 收口报「证据不在项目目录 / 文件 hash 不匹配」 | `finalize_run.py` 要求 4 份证据与 `operation-record.md` **同一目录**，manifest 里的 path 是相对该目录的**纯文件名** | 证据直接放 `runs/<运营方>/<产品>/`；manifest 写 `"path": "s11-sequence.txt"` 这类裸文件名，写完再算 sha256 |
| 10 | 4 区排除抽验报「记录缺 country_code」，整批阻断 | 平台个别记录国家字段为空（键在、值为空），旧逻辑直接 fail-closed | ✅ 已修：值为空的单列计数、不当作残留；真出现 CN/TW/HK/MO 仍判失败。改完已重跑通过 |
| 11 | 提交前自检要跑 1–2 分钟，超时像卡死 | `preflight` 是全量测试 | 后台跑或先独立跑一次；确认全绿后可 `SKIP_PREFLIGHT=1` 提交，但**不能不跑就宣称通过** |
| 12 | 建完序列担心已经在发信 | 序列默认 `inactive` | 未激活不发信、不扣赠送点数；激活只认用户「确认激活」原话 |
| 13 | 子进程报 `unrecognized arguments: <脚本路径>` | 用 `runpy.run_path` 执行脚本前没设置 `sys.argv`，脚本名被当成参数 | 调 `runpy` 前先 `sys.argv = args`；或直接用 `subprocess` 调脚本 |

## 上线前自查 4 件事（这次实际用到的）
1. 序列：12 步、状态 inactive、48 个模板全挂上。
2. 模板差异：最大相似度 ≤0.70。
3. 4 区排除：抽验无残留。
4. 核实面板：标签 / 客群 / 保存 / 模板 / 配额 / 审查 六项齐全。

四项都过才叫「设置核对完成」，接着才是等用户说激活。
