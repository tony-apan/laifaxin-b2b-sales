#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 新会话第一步：自检引导。运行本脚本 = "自动读取" 当前域的一切。
新会话/换AI：先跑 `python3 tools/onboard_check.py`，看输出即知：该读什么/当前状态/下一步/可用工具。
（本脚本只能在 Python 已可运行后做检查；全新电脑没有 Python 时，先由 AI 跑零 Python 前提的
  tools/bootstrap.sh（macOS/Linux/Git Bash/WSL）或 tools/bootstrap.ps1（Windows PowerShell），SOP 见 specs/environment-setup.md）
新增：扫描 runs/*/*/operation-record.md 输出"可续接项目"表（解析 frontmatter 状态定位节点，禁止从 S0 重跑；换机 SOP 见 specs/migration-handoff.md）。
"""
import sys, subprocess, re
from pathlib import Path
KB = Path(__file__).resolve().parent.parent
def show(path, maxh=12):
    p=KB/path
    if not p.exists(): print(f"  (缺 {path})"); return
    lines=p.read_text().split("\n")
    print(f"── {path} ──")
    for l in lines[:maxh]:
        if l.strip(): print("  "+l)

# ---------- frontmatter 解析（只取白名单外的标量键也仅限元数据；绝不输出 token/审批原话/邮箱/正文内容） ----------
def parse_frontmatter(path):
    """解析 Markdown 头部 frontmatter（--- ... ---），返回 {key: value}；文件缺失/无 frontmatter 返回 {}。"""
    meta = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return meta
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return meta
    for l in lines[1:]:
        s = l.strip()
        if s == "---":
            break
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_\-]*)\s*:\s*(.*)$", s)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
            v = v[1:-1].strip()
        meta[k] = v
    return meta

# 状态机节点 → 下一步提示（摘自 RULES.md/SKILL.md 状态机，供续接定位）
NODE_HINT = {
    "S0": "补齐昵称+一句话产品 → 登录检查 check_login.py → 闸门 gate_check.sh → 出 A/B/C/D 方案用户选字母",
    "S0A": "产品档案节点(S0a_PRODUCT_PROFILE)：AI 填①~⑧字段(每字段 内容/source/confidence)→ 用户拍板 product_profile.py confirm --by <纯昵称> --quote <原话>；用户明确不给 → init --declined；draft/缺档案不得进 S2",
    "S1": "确认路径 A(有精准网址)/B(标准路径)——自动选择不追问，用户可随时补网址切换",
    "S2": "推演 4 客群(优先读 product-profile.md)并请用户确认 → segments_infer.py 落地",
    "S3": "AI 数据库搜索链三步(预览→id 取域名→域名扩量) → seed_resolve.py，用户确认锚点",
    "S4": "70% 临界审计(50页跳→三页平均→逐页，AI 语义反思)——审计未完成不能保存",
    "S5": "建标签 tag_add.py → 展示保存参数请用户确认 → save_first_n.py --approval 保存前 N",
    "S6": "等保存 finished+标签对账 wait_save_done.py → 主动出示数量账(S6-数量账)",
    "S7": "模板草稿预览(render_preview.py 渲染后收件人视图)请用户确认后才批量创建",
    "S8": "批量建 120 模板 + check_template_diff.py 实测差异(≤0.70)，失败回 S7",
    "S9": "resolve_schedule.py 运行时解析时区 → build_sequence.py 建序列(12步/纽约/30000/5/notSentTags)",
    "S9A": "账号固定标签「询盘/不发」：先 tags-list 查同名复用 id，不存在才建，不随产品重建",
    "S10": "时序守卫(finished+标签联系人>0+序列 inactive+人数对账)通过后 contact_add.py(views:[] 铁律)",
    "S11": "终检 verify_sequence/verify_exclude + 核实面板，保持 inactive，发『流程待确认』等用户明确指令",
    "S12": "已激活：转入运维(询盘打『询盘』标签停发/复盘)；★空序列测完激活后须回滚 inactive",
    "ERROR_BLOCKED": "只读检查定位异常/对账不一致，修复后重跑 gate_check.sh——禁止自动写操作",
}

# ★静态红队P2: S0a_PRODUCT_PROFILE 等带子标记/下划线的复合状态须优先于裸 S0 定位
# (旧正则 S\d+[aA]? 会把 S0a_PRODUCT_PROFILE 截成 S0A 但 NODE_HINT 无此键, 退回泛化提示, 也存在被误读回 S0 的风险)
_STATUS_TOKEN_RE = re.compile(r"(S\d+[A-Za-z]*(?:_[A-Za-z_]+)?|ERROR_BLOCKED)", re.IGNORECASE)

def locate_node(status):
    """从 status 值定位状态机节点（如 S4 / S0a_PRODUCT_PROFILE→S0A / S9A / ERROR_BLOCKED）；定位不到返回 None。
    复合状态(带子标记/下划线)整段匹配后取基础节点号——S0a_PRODUCT_PROFILE 优先解析为 S0A, 不会被当成 S0;
    ERROR_BLOCKED 整体是一个节点, 不拆成 ERROR。"""
    m = _STATUS_TOKEN_RE.search(str(status))
    if m:
        token = m.group(1)
        if token.upper() == "ERROR_BLOCKED":
            return "ERROR_BLOCKED"
        return token.split("_", 1)[0].upper()
    return None

def next_step_for(status):
    node = locate_node(status)
    if node and node in NODE_HINT:
        return f"当前节点={node}：{NODE_HINT[node]}"
    return "读该档案『✅ 本轮最终记录』表定位最后完成环节，从下一环节续接（禁止从 S0 重跑；换机校验见 specs/migration-handoff.md）"

def scan_resumable():
    """扫描 runs/<运营方>/<产品>/operation-record.md（排除 _template 等 _ 开头目录），返回项目列表。
    只解析状态元数据（status/updated/product-profile 的版本字段），不读取/输出正文、凭证、邮箱。"""
    projects, incomplete = [], []
    runs_dir = KB / "runs"
    if not runs_dir.is_dir():
        return projects, incomplete
    for op_dir in sorted(runs_dir.iterdir()):
        if not op_dir.is_dir() or op_dir.name.startswith("_"):
            continue
        for prod_dir in sorted(op_dir.iterdir()):
            if not prod_dir.is_dir():
                continue
            rec = prod_dir / "operation-record.md"
            if not rec.exists():
                if any(prod_dir.iterdir()):
                    incomplete.append(f"{op_dir.name}/{prod_dir.name}")
                continue
            meta = parse_frontmatter(rec)
            status = meta.get("status", "(frontmatter 无 status)")
            updated = meta.get("updated", "-")
            prof_line = "-"
            prof = prod_dir / "product-profile.md"
            if prof.exists():
                pm = parse_frontmatter(prof)
                bits = []
                if pm.get("status"):        bits.append("status=" + pm["status"])
                if pm.get("profile_version"): bits.append("v" + pm["profile_version"])
                if pm.get("updated_at"):    bits.append("更新 " + pm["updated_at"])
                if pm.get("confirmed_at"):  bits.append("确认 " + pm["confirmed_at"])
                prof_line = " ".join(bits) if bits else "有档案(无版本元数据)"
            projects.append({
                "operator": op_dir.name, "product": prod_dir.name,
                "status": status, "updated": updated, "profile": prof_line,
                "next": next_step_for(status),
            })
    return projects, incomplete

print("🛰 当前域: 来发信外贸获客 (本仓库)")
print("📌 核心规则热身(全文见 SKILL.md/RULES.md):")
print("   · 广撒网拿询盘≠精准开发;询盘只是信号,不等于订单")
print("   · 系统不自动识别回复/打标签;人/AI助手打'询盘'标签且实际生效后才停邮件")
print("   · 渐进索取:每步只问当前必需的一件事;公司名/官网/邮箱/认证/产能/MOQ=用户自己的商业资产,AI可主动要但仅供建档/背调,绝不写进邮件签名;客户/联系人邮箱等他人信息不索要")
print("   · ★产品资料(卖什么)=必填；卖给谁/卖到哪/自己的官网均选填，缺失时AI先推荐、不阻断、不冒充用户输入")
print("   · ★自己的网址可走独立website-profile增强：只读公开页→六区候选→用户批准才导入；失败/跳过不影响主线")
print("   · 落款只用昵称;邮件正文=目标市场语言;标签=语言-行业-角色(客户群体,非产品名)")
print("★ 安装/学习入口: ①bootstrap准备环境 → ②本脚本自检+扫描旧项目 → ③汇报结果 → ④询问用户想做什么 → ⑤按SKILL路由；不默认进入S0")
print("")
print("🔧 环境自检(30秒):")
# 启动时自动检查新版本（静默失败，绝不阻塞自检）
try:
    sys.path.insert(0, str(KB / "tools"))
    from version_check import print_notice_if_newer
    print_notice_if_newer()
    print("")
except Exception:
    pass
import shutil
env_ok = True
# ★静态红队P2: python_cmd 首选当前正在运行的 sys.executable(必然可用), 再探测 python3/python/py
def detect_python_cmd():
    cands = []
    if getattr(sys, "executable", ""):
        cands.append(sys.executable)
    for name in ("python3", "python", "py"):
        try:
            w = shutil.which(name)
        except Exception:
            w = None
        if not w:
            continue
        try:
            if any(Path(c).resolve() == Path(w).resolve() for c in cands if c):
                continue  # 与已选命令同一解释器, 不重复
        except Exception:
            pass
        cands.append(w)
    return cands[0] if cands else None
python_cmd = detect_python_cmd()
print(f"  {'✅' if python_cmd else '❌'} Python 3 实际命令: {python_cmd or '未找到'}")
env_ok = bool(python_cmd)
print("   (说明: 本脚本≠安装器——它只能在 Python 已可运行后检查;全新电脑无 Python 时,由 AI 先跑零 Python 前提的")
print("    环境引导: Windows PowerShell→tools/bootstrap.ps1(-CheckOnly/-Install); macOS/Linux/Git Bash/WSL→tools/bootstrap.sh(--check-only/--install); SOP=specs/environment-setup.md)")
for tool, tip in [("curl", "Mac/Linux 自带; Windows 由Git for Windows/系统提供"), ("bash", "Mac/Linux 自带; Windows 需Git Bash/WSL"), ("grep", "gate_check依赖;Git Bash自带"), ("awk", "gate_check依赖;Git Bash自带")]:
    found = shutil.which(tool) is not None
    env_ok = env_ok and found
    print("  {} {}: {}".format("✅" if found else "❌", tool, "已安装" if found else "未找到——" + tip))
if python_cmd is None:
    print("  ❗ 未找到 python。本脚本自己就是 Python 脚本,不能自举安装——先让 AI 跑环境引导(命令可复制):")
    print("     · Windows PowerShell: powershell -NoProfile -ExecutionPolicy Bypass -File tools\\bootstrap.ps1 -CheckOnly")
    print("       (装缺失依赖: 同命令把 -CheckOnly 换成 -Install,用 winget 装 Python/Git;SOP 见 specs/environment-setup.md)")
    print("     · macOS/Linux/Git Bash/WSL: bash tools/bootstrap.sh --check-only")
    print("       (装缺失依赖: bash tools/bootstrap.sh --install,用 brew/apt-get/dnf/yum/pacman/apk;不自动装 Homebrew)")
    print("     · 手动兜底(引导脚本也提示这些): Windows https://www.python.org/downloads/ 勾选『Add python to PATH』,或 Git Bash https://git-scm.com/download/win")
    print("       macOS: `xcode-select --install` 或 https://www.python.org/downloads/ ; Linux: `sudo apt install python3` 或 `sudo yum install python3`")
    print("   👉 装好后回到本步骤重跑自检(下面命令用你实际能用的 python3/py 之一)。")
if not env_ok:
    print("  ⚠️ 缺环境依赖: Windows 用户请先安装 Git Bash(https://git-scm.com/download/win) 或 WSL 后重跑; Mac 弹出'需要安装开发者工具'点安装即可")
print("")
projects, incomplete = scan_resumable()
print("📂 可续接项目扫描 (runs/*/*/operation-record.md,排除 _template;只读状态元数据,绝不输出 token/审批原话/邮箱):")
if projects:
    for i, p in enumerate(projects, 1):
        print(f"  {i}. 运营方={p['operator']}  产品={p['product']}")
        print(f"     流程状态={p['status']}  (updated {p['updated']})")
        print(f"     产品档案 product-profile.md: {p['profile']}")
        print(f"     👉 下一步: {p['next']}")
    print("  ★ 续接纪律: 按 runs/<运营方>/<产品>/operation-record.md 的『✅ 本轮最终记录』表定位节点续跑,禁止从 S0 重跑(会重复建档/重复保存浪费点数)")
    print("     换电脑/新机器续接的完整校验清单(token 重取/审批凭证边界/序列 inactive 核对)见 specs/migration-handoff.md")
else:
    print("  未发现可续接项目档案；安装完成后仍先让用户选择任务，不自动创建新项目")
if incomplete:
    print(f"  ℹ️ 另有目录有档案但缺 operation-record.md(非标准档案,续接前先让用户确认是否补建/废弃): {'; '.join(incomplete)}")
print("")
print("📖 新会话引导: 按顺序读下面 → 你已读取 → 下一步")
print("  （本地运行状态/审批凭证在 .local/，首次运行自动生成，不入 Git）")
# ★静态红队P2: 多公司运营方档案各一份(.local/operators/<operator_key>.md), 兼容提示旧版单运营方文件
_ops_dir = KB / ".local" / "operators"
if _ops_dir.is_dir():
    _ops_found = sorted(p.name for p in _ops_dir.glob("*.md"))
    if _ops_found:
        print(f"  · 运营方档案(多公司各一份): {', '.join('.local/operators/' + n for n in _ops_found)}")
_legacy_op = KB / ".local" / "operator-profile.md"
if _legacy_op.is_file():
    print("  ⚠️ 检测到旧版单运营方档案 .local/operator-profile.md——多运营方请迁移到 .local/operators/<operator_key>.md(tools/operator_profile.py 兼容读取旧文件; flow_orchestrator 等旧引用以仓库最新文档为准)")
show("README.md", 10)
show("RULES.md", 10)
print("\n🛠 可用工具(自足):")
for t in sorted(p.name for p in list((KB/"tools").glob("*.py")) + list((KB/"tools").glob("*.sh"))):
    print(f"  {t}")
if projects:
    print("\n✅ 安装/学习自检完成；发现可以续接的旧项目（本次不自动继续）:")
    print("  · 先向用户报告上方项目名称和当前节点；只有用户选择‘继续以前的项目’后，才读取对应档案、重新获取 token 并从记录节点续跑。")
else:
    print("\n✅ 安装/学习自检完成；未发现标准可续接项目。")

print("\n🗣 安装完成后只向用户展示这个任务菜单，不索取业务资料:")
print('   "安装完成。你现在想做什么？"')
print("   1. 开始一个新的获客项目")
print("   2. 判断产品是否适合批量冷邮件")
print("   3. 从自己的官网、产品页或目录提炼资料")
print("   4. 继续以前没有完成的项目")
print("   5. 更新系统或换电脑继续")
print("   6. 先了解完整流程")
print("\n🔴 安装/学习阶段到此停止：不要问产品、市场、官网、昵称或 token，不要默认进入 S0。")
print("   用户选择具体任务后，再按 SKILL.md 对应路由渐进询问；只有选择新获客项目，才问纯个人昵称+一句话产品。")
