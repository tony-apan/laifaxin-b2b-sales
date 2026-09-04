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
print("📌 核心规则热身(全文见 SKILL.md/RULES.md):")
print("   · 广撒网拿询盘≠精准开发;询盘只是信号,不等于订单")
print("   · 系统不自动识别回复/打标签;人/AI助手打'询盘'标签且实际生效后才停邮件")
print("   · 渐进索取:每步只问当前必需的一件事;公司名/官网/邮箱/认证/产能/MOQ=用户自己的商业资产,AI可主动要但写入正文须用户拍板;客户/联系人邮箱等他人信息不索要")
print("   · ★产品资料(卖什么/卖点/客群方向)=获客素材,用户没给时AI主动要一次(给模板可跳过),不逼问")
print("   · 落款只用昵称;邮件正文=目标市场语言;标签=语言-行业-角色(客户群体,非产品名)")
print("★ 会话入口总线: ①本脚本(环境+文档引导) → ②check_login.py 登录检查(流程第一步) → ③gate_check.sh 闸门 → ④flow_orchestrator.py 向导")
print("")
print("🔧 环境自检(30秒):")
import shutil
env_ok = True
# 先探测 python3,再探测 Windows 常见的 py;并给出可执行命令名
python_cmd = None
for cand in ("python3", "py"):
    if shutil.which(cand):
        python_cmd = cand
        break
for tool, tip in [("python3","(本机已具备)"), ("py","Windows 常见 python 启动器(装了 python 就有)"), ("curl", "Mac/Linux 自带; Windows 需先装 Git Bash 或 WSL"), ("bash", "Mac/Linux 自带; Windows 需 Git Bash/WSL"), ("grep", "gate_check 依赖; Windows Git Bash 自带"), ("awk", "gate_check 依赖; Windows Git Bash 自带")]:
    found = shutil.which(tool) is not None
    # python3 与 py 只算一个能力(有其一即视为 python 可用)
    if tool in ("python3", "py"):
        found = python_cmd is not None
        tool_show = f"{tool} ({'即 python3 可执行' if python_cmd else '未找到'})"
    else:
        tool_show = tool
    env_ok = env_ok and (found if tool not in ("python3","py") else (python_cmd is not None))
    print("  {} {}: {}".format("✅" if found else "❌", tool_show, "已安装" if found else "未找到——" + tip))
if python_cmd is None:
    print("  ❗ 未找到 python。请安装 Python 3：")
    print("     · Windows: 打开 https://www.python.org/downloads/ 下载安装包,勾选『Add python to PATH』,装完重跑")
    print("       (若只想跑脚本不打字,也可以装 Git Bash: https://git-scm.com/download/win 或 WSL 后在 Bash 里操作)")
    print("     · macOS: 打开终端跑 `xcode-select --install`,或到 https://www.python.org/downloads/ 装")
    print("     · Linux: `sudo apt install python3` (Debian/Ubuntu) 或 `sudo yum install python3` (CentOS)")
    print("   👉 装好后回到本步骤重跑自检(下面命令用你实际能用的 python3/py 之一)。")
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
print("\n✅ 引导完成。AI 请按序执行:")
print(f"  1. 向用户要 token(没有→引导教程 https://www.laifa.xin/share/ai/laifaxin-ai-account-connection)+昵称+一句话产品")
print("     ★渐进索取:开跑只要这2项;公司名/官网/邮箱/认证/产能/MOQ 可主动要但写入正文须用户拍板;客户邮箱等他人信息不索要")
print("     ★昵称只放个人称呼;含公司/产品/职位→一次性请用户改")
print("     ★产品资料(卖什么/卖点/客群方向):用户没给→AI主动要一次,给模板可跳过,不逼问(见 specs/product-profile-sop.md)")
print(f"  2. {python_cmd or 'python3'} tools/check_login.py --token '<T>'   ← 登录检查+账号状态卡(按 output-templates/S0-连接成功.md 展示)")
print("  3. bash tools/gate_check.sh --token '<T>'        ← 闸门(必过才准写操作)")
print(f"  4. {python_cmd or 'python3'} tools/flow_orchestrator.py ...        ← 节点确认向导(S0-S11)")
print("")
print("🗣 对用户的开场白(照此说,把用户当小白):")
print('   "这是一个批量找外国买家的系统:批量触达筛出询盘,收到询盘后您再人工精准跟进。"')
print('   "您只需要给我账号钥匙(token)和您的落款昵称,再说一句卖什么,剩下的我来。"')
print('   "如果您方便,再给我两三句产品资料(卖什么/卖点/卖给哪些国家),我帮您把客群和开发信写得更准;不给也行,我先按通用口径出一版。"')
print('   "每一步我都会先给您方案,您回复确认/否/要改就行。最后发信前必须您明确点头。"')
