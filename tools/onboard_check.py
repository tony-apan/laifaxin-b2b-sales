#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 新会话第一步：自检引导。运行本脚本 = "自动读取" 当前域的一切。
新会话/换AI：先跑 `python3 tools/onboard_check.py`，看输出即知：该读什么/当前状态/下一步/可用工具。
"""
import sys, subprocess
from pathlib import Path
KB = Path(__file__).resolve().parent.parent
def show(path, maxh=12):
    p=KB/path
    if not p.exists(): print(f"  (缺 {path})"); return
    lines=p.read_text().split("\n")
    print(f"── {path} ──")
    for l in lines[:maxh]:
        if l.strip(): print("  "+l)
print("🛰 当前域: 来发信外贸获客 (本仓库)")
print("★ 会话入口总线: ①本脚本(环境+文档引导) → ②check_login.py 登录检查(流程第一步) → ③gate_check.sh 闸门 → ④flow_orchestrator.py 向导")
print("")
print("🔧 环境自检(30秒):")
import shutil
env_ok = True
for tool, tip in [("python3","(本机已具备)"), ("curl", "Mac/Linux 自带; Windows 需先装 Git Bash 或 WSL"), ("bash", "Mac/Linux 自带; Windows 需 Git Bash/WSL"), ("grep", "gate_check 依赖; Windows Git Bash 自带"), ("awk", "gate_check 依赖; Windows Git Bash 自带")]:
    found = shutil.which(tool) is not None
    env_ok = env_ok and found
    print("  {} {}: {}".format("✅" if found else "❌", tool, "已安装" if found else "未找到——" + tip))
if not env_ok:
    print("  ⚠️ 缺环境依赖: Windows 用户请先安装 Git Bash(https://git-scm.com/download/win) 或 WSL 后重跑; Mac 弹出'需要安装开发者工具'点安装即可")
print("")
print("📖 新会话引导: 按顺序读下面 → 你已读取 → 下一步")
print("  （本地运行状态/审批凭证在 .local/，首次运行自动生成，不入 Git）")
show("README.md", 10)
show("RULES.md", 10)
print("\n🛠 可用工具(自足):")
for t in sorted(p.name for p in list((KB/"tools").glob("*.py")) + list((KB/"tools").glob("*.sh"))):
    print(f"  {t}")
print("\n✅ 引导完成。下一步(按序):")
print("  1. 向用户要 token(用户没有→引导教程 https://www.laifa.xin/share/ai/laifaxin-ai-account-connection)+昵称+产品信息(+可选精准网址)")
print("  2. python3 tools/check_login.py --token '<T>'   ← 流程第一步:登录检查(org自动提取)")
print("  3. bash tools/gate_check.sh --token '<T>'        ← 闸门(必过才准写操作)")
print("  4. python3 tools/flow_orchestrator.py ...        ← 节点确认向导(S0-S11)")
