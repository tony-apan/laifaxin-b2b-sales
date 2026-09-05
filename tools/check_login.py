#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★流程第一步·登录检查（只读）：验证来发信 accesstoken 是否有效（benefits/refine-data 只读，不搜客/不保存/不扣点/不发信）。
无 token / 失效时打印官方教程引导，让用户获取后交给 AI。
用法:
  python3 check_login.py --token '<accesstoken完整串>'   # org 自动从 token 提取(官方:accesstoken已含账号信息)
  python3 check_login.py --token '<...>' --org <orgId>   # 也可显式传
官方教程: https://www.laifa.xin/share/ai/laifaxin-ai-account-connection
"""
import json, subprocess, argparse, sys, re

GUIDE_URL = "https://www.laifa.xin/share/ai/laifaxin-ai-account-connection"

def guide(reason):
    print(f"❌ {reason}")
    print(f"""
📖 获取 token 官方教程: {GUIDE_URL}
  方法一（小白，不敲代码）: 登录 web.laifaxin.com → 页面右键"检查" → 顶部"应用程序"(Application) →
      左侧 存储→本地存储→https://web.laifaxin.com → 分别复制 accesstoken 和 orgId 两项的"值"
  方法二（⭐推荐，一条命令两样全拿）: 页面右键"检查" → 顶部"控制台"(Console) → 粘贴这一行并回车:
      var t=localStorage.getItem("accesstoken");t&&t!=="null"?(copy("accesstoken="+t+"\\norgId="+localStorage.getItem("orgId")),console.log("✅ 已复制到剪贴板！请回到对话框 Ctrl+V 粘贴发送给 AI")):console.log("❌ 未登录或页面不对——请先登录 web.laifaxin.com 再重试");
      成功会显示 ✅ 提示（不再是无意义的 undefined）；显示 ❌ = 未登录，先登录再试
      复制出来的是两行：accesstoken=... 和 orgId=...（字段名与页面存储一致），整段发给 AI 即可
  ⚠️ 粘贴代码时浏览器可能提示 "Don't paste code"——输入 allow pasting 再粘
  🔴 企业账号/多组织：右上角头像"切换账号"后 orgId 会变、token 不变——切换后必须重新执行上面的命令
  ❓ ORG=null = 未登录/页面不对 → 确认已登录，刷新重试
拿到后把剪贴板整段发给 AI——首次连接只做本只读检查，不搜客/不保存/不发信。""")

ap = argparse.ArgumentParser()
ap.add_argument("--token", default="", help="accesstoken 完整串（用户按教程复制）")
ap.add_argument("--org", default="", help="工作空间ID=localStorage orgId（🔴企业账号必填！个人账号可省略=token中段）")
args = ap.parse_args()

if not args.token:
    guide("未传 token")
    sys.exit(1)

# ★token 形状校验（B1-4/AI-6: 复制不全是高频错误——提前用人话拦截,不触网）
tok = args.token.strip()
if tok != args.token:
    print("⚠️ token 首尾带空格/换行——已自动去除（下次复制时注意别带上）")
args.token = tok

# ★一键双取格式自动拆分（2026-09-06：用户用一条 copy 命令同时复制 token+orgId，
#   AI 可把剪贴板整段原样传给 --token，本工具自动拆出 TOKEN=/ORG= 两行——防 AI 转述出错）
if ("accesstoken=" in tok or "TOKEN=" in tok) and ("orgId=" in tok or "ORG=" in tok):
    m_tok = re.search(r"(?:accesstoken|TOKEN)=([^\s]+)", tok)
    m_org = re.search(r"(?:orgId|ORG)=([^\s]+)", tok)
    if m_tok and m_org:
        parsed_tok, parsed_org = m_tok.group(1), m_org.group(1)
        if parsed_tok.lower() == "null" or parsed_org.lower() == "null":
            print("❌ 复制内容含 null——未登录或页面不对。请在 web.laifaxin.com 登录后重新执行复制命令。")
            sys.exit(2)
        if not args.org:
            args.org = parsed_org
        args.token = parsed_tok
        tok = parsed_tok
        print("# 检测到一键双取格式（accesstoken/orgId）——已自动拆分")
    else:
        print("⚠️ 看起来是一键双取格式但解析失败——请回到网页控制台重新执行复制命令")

segs = tok.split("&")
uid_from_token = segs[1] if len(segs) >= 3 else ""
if args.org:
    org = args.org
    if uid_from_token and org == uid_from_token:
        print(f"# 当前工作空间: {org}（个人账号：orgId==用户ID）")
    else:
        print(f"# 当前工作空间: {org}（企业org，操作用户={uid_from_token or '?'}）")
elif len(segs) >= 3:
    org = segs[1]
    print(f"# 当前工作空间: {org}（⚠️回退=token中段用户ID——个人账号成立；🔴企业账号必须显式传 --org <localStorage的orgId>）")
    print("   🔴 多org提醒：网页右上角头像可'切换账号'（个人↔企业）——切换后 orgId 会变，token 中段不变；")
    print("      请在控制台执行 copy(localStorage.getItem(\"orgId\")) 取当前工作空间ID，随 --org 传入，否则会操作错空间！")
else:
    print("❌ token 格式不对（应有 3 段: web.laifaxin.com&<orgId>&<长串>，你给的只有 %d 段）——大概率是没复制完整。" % len(segs))
    print("   ★建议改用方法二一键复制（控制台 copy 命令），或对照教程重新复制整串；也可显式传 --org <orgId>。")
    sys.exit(2)

cmd = ["curl","-sSL","-m","30","-X","POST",f"https://web.laifaxin.com/api/benefits/refine-data?uid={org}",
       "-H","Content-Type: application/json","-H",f"accesstoken: {args.token}","-d","{}"]
r = None
try:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
    d = json.loads(r.stdout) if r.stdout.strip() else {}
except Exception:
    d = {}

# ★B7-1/terra 3-①: 三分类——curl层失败(rc!=0)=网络; 空/非JSON=平台接口间歇空(已知)(轻文案); success=false=token
if r is not None and r.returncode != 0:
    print("❌ 网络不通/超时（curl 层失败, rc={}）：这不是 token 问题，不用重新登录！".format(r.returncode))
    print("   下一步：检查网络（公司网/VPN/代理）或等几分钟后重跑本命令。")
    sys.exit(3)
if r is not None and r.returncode == 0 and not d:
    body = (r.stdout or "").strip()
    if not body:
        print("ℹ️ 已连通但返回为空——已知问题 平台接口间歇空(已知)（接口偶发抽风）：等 5-10 分钟重跑本命令即可，无需重登、无需重取 token。")
    else:
        print("ℹ️ 返回了非 JSON 内容（可能是网关错误页, 前 60 字: {}）——等几分钟重跑；反复出现再查网络。".format(body[:60]))
    print("   教程备查: " + GUIDE_URL)
    sys.exit(3)
if not d and r is None:
    print("❌ 请求未完成（超时/异常）——稍等重跑；这不是 token 问题。")
    sys.exit(3)

if d.get("success") is True:
    data = d.get("data", {}) or {}
    vip = data.get("vip")
    vip_label = "SVIP" if vip == 2 else f"VIP {vip}"  # vip2=SVIP（平台等级映射,2026-09-03 用户确认）
    dl, du = data.get('dailyLimit') or 0, data.get('dailyUsed') or 0
    ml, mu = data.get('monthlyLimit') or 0, data.get('monthlyUsed') or 0
    duptext = "已用尽" if data.get('dailyUsedUp') else f"剩 {max(dl-du,0)}"
    muptext = "已用尽" if data.get('monthlyUsedUp') else f"剩 {max(ml-mu,0)}"
    print("✅ 连接成功！您的来发信账号状态：")
    print(f"   操作用户：{uid_from_token or '?'} ｜ 工作空间(orgId)：{org}" + ("  ← 企业org" if org != uid_from_token else ""))
    print(f"   账号等级：{vip_label}")
    print(f"   今日查看配额：{dl} 条，已用 {du} 条（{duptext}）")
    print(f"   本月查看配额：{ml} 条，已用 {mu} 条（{muptext}）")
    if data.get('monthlyChargeCount') is not None or data.get('monthlyAutoCharge') is not None:
        auto = "已开启" if data.get('monthlyAutoCharge') else "未开启"
        print(f"   本月充值：{data.get('monthlyChargeCount') or 0} 次（自动充值：{auto}）")
    print("   本次只做了连接检查——没搜索、没保存、不扣点。")
    if data.get('dailyUsedUp'):
        print("   ⚠️ 今日搜索配额已用尽：次日恢复；保存邮箱和发信不受影响（见 wiki/faq）")
    print("   下一步(AI): 按 output-templates/S0-连接成功.md 展示 → 请用户提供 昵称(+一句话产品) → gate_check → RULES 状态机")
    # 启动时自动检查新版本（静默失败，绝不阻塞主流程）
    try:
        sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
        from version_check import print_notice_if_newer
        print_notice_if_newer()
    except Exception:
        pass
    sys.exit(0)
else:
    msg = d.get("message") or (r.stdout[:80] if isinstance(r.stdout, str) else "")
    guide(f"token 无效或未登录（接口返回: {msg}）")
    sys.exit(1)
