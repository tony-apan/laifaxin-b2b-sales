#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★统一模板生成器（多产品参数化）——替代旧版产品专用模板脚本
★差异达标(模板差异实测（工具级）): 正文 = 轮次angle全句 + 变体body全句, 仅 Hi+签名 固定 → 两两 Jaccard≤0.70
用法:
  python3 gen_templates.py --token <T> --org <orgId> --product 皮筏艇 --prefix "英-皮筏艇-" --suffix=-RT --name <昵称> --approval <ap-id> --project <产品> [--preview]
  生成后必跑 tools/check_template_diff.py --prefix 实测差异(模板差异实测（工具级）)
  ★任意产品(无需改代码): --plan <模板计划JSON> --plan-name <产品名>
      JSON 结构 = {"directions": [["R01","中文名","主题纯文案","正文轮次句"], ...], "variants": ["正文变体句", ...]}
"""
import json, subprocess, time, sys, argparse, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from approval import require_approval

VAR = '<code class="lfxFieldVeriable" contenteditable="false">{联系人:名称}</code>'

ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True)
ap.add_argument("--org", required=True)
ap.add_argument("--product", default="", help="产品名——★内置文案仅支持:皮筏艇/玻璃瓶;其他产品须先用 --plan 提供任意模板计划(或由AI现写文案入PRODUCTS)")
ap.add_argument("--prefix", required=True, help="模板名前缀,如 英-玻璃瓶-")
ap.add_argument("--suffix", default="-GL", help="命名后缀")
ap.add_argument("--foid", default="", help="模板分组id(默认自动按 --prefix 建同名分组并归入;传 0 = 未指定目录,不推荐——120 个模板会散落)")
ap.add_argument("--name", required=True, help="签名昵称=客户邮件里看到的落款(★GATE0昵称,建议英文如 Tina from ABC Corp;必填防误用他人默认名)")
ap.add_argument("--preview", action="store_true", help="仅草稿展示(渲染视图,不创建)")
ap.add_argument("--out", default="", help="可选: 落盘 name→id 映射 JSON(供重建序列 step-save 用)")
ap.add_argument("--approval", default="", help="★审批凭证id(审批闸门·工具级): .local/approvals.tsv 或编排器输出")
ap.add_argument("--project", default="", help="产品名(审批project匹配)")
ap.add_argument("--plan", default="", help="★模板计划JSON(任意产品,优先于内置PRODUCTS查找): {\"directions\": [[\"R01\",\"中文名\",\"主题纯文案\",\"正文轮次句\"], ...], \"variants\": [\"正文变体句\", ...]}")
ap.add_argument("--plan-name", default="", help="--plan 时的产品名(仅用于展示/提示,如 皮筏艇-经销商; 默认取 --product)")
try:
    args = ap.parse_args()
except SystemExit as _parse_exit:
    # ★argparse 必填校验失败(缺 --prefix/--name 等): 未用 --plan/--product 时追加一行提示(支持任意产品)
    if _parse_exit.code != 0 and "--plan" not in sys.argv and "--product" not in sys.argv:
        print("（提示：用 --plan <模板计划JSON> --plan-name <产品名> 支持任意产品；插件详情见 --help）", file=sys.stderr)
    raise
if not args.plan and not args.product:
    print("❌ 缺 --product <产品名>——或改用 `--plan <模板计划JSON> --plan-name <产品名>` 指定任意产品计划。")
    print("（提示：用 --plan <模板计划JSON> --plan-name <产品名> 支持任意产品；插件详情见 --help）")
    raise SystemExit(2)
SIGN = args.name

# 每轮 = (轮次号, 中文, 主题纯文案, 正文轮次句)；每变体 = 正文全句(唯一,互不相同)
PRODUCTS = {
  "皮筏艇": (
    [("R01","破冰","Inflatable rafts for your outfitter","We manufacture commercial inflatable rafts and supply outfitters running guided river trips."),
     ("R02","信任","Certified whitewater raft supplier","Our rafts are built to ISO 6185-1 (inflatable boats standard) and supplied to outfitter and rental fleets overseas."),
     ("R03","降本","Cut your fleet cost","Switching to us cuts your fleet cost per unit without sacrificing durability or safety."),
     ("R04","产能","Run more trips","Our factory keeps steady output so you can scale trips without waiting on supply."),
     ("R05","稀缺","Fall production slots filling","Our fall production slots are filling fast — booking early secures your delivery window."),
     ("R06","趋势","River tourism is growing","River tourism demand is climbing, and outfitters are booking earlier to secure capacity."),
     ("R07","环保","Durable repairable construction","Our rafts are built durable and repairable — patch kits included, so hulls stay in service longer."),
     ("R08","交期","20-day raft delivery","We deliver in about 20 days from order to your dock, even for mixed model fleets."),
     ("R09","服务","Full outfitter support","One team handles design, QA and after-sales so you get support through the whole life."),
     ("R10","促行动","Special fleet pricing now","We're offering an extra 8% off this month for outfitters who confirm their fleet plan now."),
     ("R11","二次触达","Your raft fleet options","Following up on the raft options from my earlier emails, ahead of the peak season rush."),
     ("R12","最后机会","Final call before stock ends","This is the final call before the remaining raft stock closes for the season.")],
    ["I've attached our 2026 outfitter catalog with 12 raft models, capacity specs and deck layouts for your fleet team.",
     "We'll courier a free fabric sample with welded-seam and abrasion test results so your team can feel the PVC quality.",
     "You can pick hull color, valve position and print your logo on each tube, and we configure every raft to your brand.",
     "We offer protected territory and local dealer support with spare parts stocked in your region for faster service.",
     "For fleet orders of 20 or more units we apply a tiered bulk rate and lock pricing for the whole season.",
     "Book a live video tour of our factory line and watch a raft go from PVC sheet to pressure-tested hull in eight minutes.",
     "I can send a per-trip cost worksheet showing where fleet savings typically come from — just reply.",
     "I can send the full spec sheet with MSDS, buoyancy tubes, floor type and valve pressure ratings this afternoon.",
     "Start with a small trial batch of two units to benchmark durability against your current supplier before scaling.",
     "Reply with your fleet size and I'll return a reference price list within 24 hours, with no commitment needed."]),
  "皮筏艇-经销商": (
    [("R01","破冰","Wholesale rafts for your catalog","We supply commercial inflatable rafts to dealers and distributors, and we're opening new wholesale accounts for next season."),
     ("R02","信任","ISO 6185-1 raft line for dealers","Our rafts are built to ISO 6185-1, the inflatable boats standard, and offered through dealer channels in North America and Europe."),
     ("R03","降本","Dealer margins on rafts","Wholesale pricing is set so dealers keep a healthy margin against local brand alternatives."),
     ("R04","产能","Reliable stock for your orders","Our factory holds steady output, so your dealer orders restock on schedule through the season."),
     ("R05","稀缺","Dealer allocation closing soon","This season's dealer allocation is nearly full — confirming early locks your supply window."),
     ("R06","趋势","Dealer demand for rafts rising","River tourism keeps growing, and dealers are adding inflatable rafts to their lines earlier each year."),
     ("R07","环保","Repairable rafts, fewer returns","Durable, repairable construction with patch kits means fewer warranty issues for your shop."),
     ("R08","交期","20-day delivery for dealers","Dealer orders ship about 20 days from order confirmation, with mixed pallet and container terms."),
     ("R09","服务","Dealer support program","Dealers get protected territory, spare parts, and marketing materials — one team for the whole account."),
     ("R10","促行动","First-order dealer discount","We're offering an additional 8% off first dealer orders confirmed this month."),
     ("R11","二次触达","Your wholesale raft program","Following up on the wholesale program from my earlier emails before allocation closes."),
     ("R12","最后机会","Dealer allocation closes this week","The sign-up window for dealer accounts closes this week — reply now and we'll hold your allocation.")],
    ["I've attached our wholesale price list with 12 raft models, tiered brackets and MOQ terms for your buyers.",
     "We'll courier a fabric sample with seam and abrasion test results your team can keep in the showroom.",
     "Add your own brand on every raft — private label, colors, logo printing — and reply for the brand options sheet.",
     "We assign protected territory to new dealers and stock spare parts in your region — reply to check your area.",
     "Combine 20+ units in one order and we apply a tiered wholesale rate, with pricing locked for the season — reply for the bracket sheet.",
     "Schedule a live factory tour and watch a raft go from PVC sheet to pressure-tested hull in real time.",
     "I'll send a dealer margin worksheet with typical resale math — just reply.",
     "I can send the full spec pack — materials, buoyancy, valves, load ratings — this afternoon.",
     "Start with a small sample order of two units to benchmark quality before you commit.",
     "Tell me your target monthly volume and I'll send dealer pricing within 24 hours."]),
  "皮筏艇-零售商": (
    [("R01","破冰","Rafts for your outdoor store","We make commercial inflatable rafts sold through outdoor retailers, and we're opening new retail accounts."),
     ("R02","信任","ISO 6185-1 raft line for retail","Built to the ISO 6185-1 standard for inflatable boats, our line is aimed at outdoor retail — and we're welcoming new store accounts."),
     ("R03","降本","Retail-friendly raft pricing","Our landed cost is set so your store keeps a healthy retail margin per unit."),
     ("R04","产能","Stock ready for your peak season","We keep steady output so your seasonal buy lands before the summer rush."),
     ("R05","稀缺","Season allocation filling fast","Seasonal allocation is filling — early orders lock your shelf units."),
     ("R06","趋势","Shoppers are asking for rafts","Paddle sports keep growing, and shoppers are asking stores for rafts and kayaks earlier each season."),
     ("R07","环保","Easy-care rafts, happy customers","Durable, easy-to-repair rafts mean fewer returns and more repeat customers for your store."),
     ("R08","交期","Fast delivery for store orders","Small store orders ship about 20 days from order confirmation, with low minimums to fit your stockroom."),
     ("R09","服务","Retail support kit","You get product photos, size charts, and after-sales support — everything your floor team needs."),
     ("R10","促行动","Seasonal opening order discount","Confirm your opening order this month and we'll apply 8% off your first seasonal buy."),
     ("R11","二次触达","Your store's raft options","Following up on the raft options from my earlier emails before season allocation closes."),
     ("R12","最后机会","Season allocation closes this week","The new-account window closes this week — reply and we'll hold seasonal stock for your store.")],
    ["I've attached our retail catalog with 12 raft models, sizes and suggested retail pricing for your category.",
     "We'll courier a fabric sample with wear-test results your floor team can show customers.",
     "Order a small mix of sizes and colors — low minimums fit a single store's stockroom — and reply for the order sheet.",
     "We include display photos, size matrix and care cards for your shelves and web store — reply to see the kit.",
     "Bundle 10+ units for your seasonal buy and we hold the tiered rate through summer — reply for the bracket sheet.",
     "Watch a live factory walkthrough and see our quality checks from material to finished hull.",
     "Want the numbers behind retail sell-through? I'll send a margin worksheet — just reply.",
     "I can send the full spec sheet with sizes, weights and safety ratings this afternoon.",
     "Start with a two-unit trial to see how it sells on your floor before scaling.",
     "Send your planned seasonal order size and I'll reply with store pricing the same day."]),
  "玻璃瓶": (
    [("R01","破冰","Cosmetic bottles for your brand","We manufacture cosmetic glass bottles and packaging for skincare and beauty brands."),
     ("R02","信任","Certified cosmetic packaging supplier","Our bottles are food-grade, supplied to beauty and personal-care brands overseas."),
     ("R03","降本","Cut your packaging cost","Switching to us lowers your packaging cost per unit while keeping premium glass quality."),
     ("R04","产能","Scale up bottle supply","Our lines keep steady output so you can scale launches without supply delays."),
     ("R05","稀缺","Quarter production slots filling","This quarter's production slots are filling — booking early secures your delivery window."),
     ("R06","趋势","Clean beauty packaging demand","Clean beauty demand is rising, and brands are reserving packaging capacity earlier."),
     ("R07","环保","Recyclable glass packaging","We use recyclable glass and low-waste molding so your packaging meets eco standards."),
     ("R08","交期","Fast stock-shape delivery","Stock shapes deliver in about 20 days; custom molds are quoted separately with realistic timelines."),
     ("R09","服务","Full packaging support","One team handles design, tooling and after-sales support through the full product life."),
     ("R10","促行动","Special batch pricing now","We're offering an extra 8% off this month for brands that confirm their packaging plan."),
     ("R11","二次触达","Your bottle options","Following up on the bottle options from my earlier emails, before your next launch."),
     ("R12","最后机会","Final call before stock ends","Final call before this season's glass stock closes for new orders.")],
    ["I've attached our catalog with 40 bottle shapes, neck finishes and closure options for your range.",
     "We'll courier free glass samples with wall-thickness and drop-test results for your QC team.",
     "You can pick bottle color, frosting, and print your logo on the glass for a fully branded look.",
     "We offer dedicated account support with a local engineer for tooling and color matching.",
     "For orders of 50,000 or more units we apply a tiered bulk rate and hold pricing for the quarter.",
     "Book a live video tour of our furnace and molding line to see quality control in real time.",
     "I can send a cost-per-unit breakdown showing where packaging savings typically come from — just reply.",
     "I can send the full spec with glass type, capacity, and decoration options this afternoon.",
     "Start with a small trial batch of 2,000 units to benchmark quality before you scale.",
     "Reply with your expected volume and I'll return reference pricing within 24 hours."]),
}

def load_plan(path):
    """读取 --plan 模板计划JSON(与 PRODUCTS 同构): {"directions": [[轮次号,中文名,主题,正文轮次句],...], "variants": [正文变体句,...]}
    无效(读不到/JSON错/结构错)→ 明确报错 exit 2,绝不静默兜底。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            plan = json.load(f)
    except FileNotFoundError:
        print(f"❌ --plan 文件不存在: {path}"); raise SystemExit(2)
    except json.JSONDecodeError as e:
        print(f"❌ --plan JSON 解析失败(无效JSON): {path} -> {e}"); raise SystemExit(2)
    except Exception as e:
        print(f"❌ --plan 读取失败: {path} -> {e}"); raise SystemExit(2)
    if not isinstance(plan, dict) or not isinstance(plan.get("directions"), list) or not isinstance(plan.get("variants"), list):
        print(f'❌ --plan JSON 结构无效(应为 {{"directions": [[轮次号,中文名,主题纯文案,正文轮次句],...], "variants": [正文变体句,...]}}): {path}'); raise SystemExit(2)
    directions, variants = plan["directions"], plan["variants"]
    if not directions or not variants:
        print(f"❌ --plan 内容为空: directions/variants 至少各 1 条: {path}"); raise SystemExit(2)
    for i, d in enumerate(directions):
        if not isinstance(d, (list, tuple)) or len(d) < 4 or not all(isinstance(x, str) and x.strip() for x in d[:4]):
            print(f"❌ --plan directions[{i}] 无效(应为 [轮次号,中文名,主题,正文轮次句] 四项字符串): {d!r}"); raise SystemExit(2)
    for i, v in enumerate(variants):
        if not isinstance(v, str) or not v.strip():
            print(f"❌ --plan variants[{i}] 无效(应为非空字符串): {v!r}"); raise SystemExit(2)
    if len({d[0] for d in directions}) != len(directions):
        print("❌ --plan 轮次号重复: directions 每项第 0 位(如 R01)须唯一"); raise SystemExit(2)
    print(f"  ✅ --plan 加载: {path} ({len(directions)}轮方向×{len(variants)}变体, 签名={SIGN})")
    return directions, variants

def pick():
    if args.plan:
        return load_plan(args.plan)  # ★--plan 优先,覆盖 PRODUCTS 查找(任意产品)
    for key in PRODUCTS:
        if args.product == key:
            return PRODUCTS[key]
    best = None
    for key in PRODUCTS:
        if key in args.product and (best is None or len(key) > len(best)):
            best = key
    if best:
        return PRODUCTS[best]
    print(f"❌ 内置文案暂不支持「{args.product}」——禁止兜底用其他产品文案(会生成内容全错的模板,新手门槛整改(工具级)/B3-2)。")
    print("   正确做法: 由 AI 按用户在 GATE0 给的产品信息与 RULES/sequence-config 生成规则现写 12轮方向句×10变体句,")
    print("   加入本文件 PRODUCTS 字典后再运行(参考 皮筏艇/玻璃瓶 的结构: 每轮一句angle+每变体一句body)。")
    print('   或用 `--plan <模板计划JSON> --plan-name <产品名>` 指定计划(JSON 结构: {"directions":[["R01","中文名","主题纯文案","正文轮次句"],...],"variants":["正文变体句",...]})。')
    raise SystemExit(2)

DIRECTIONS, VARIANTS = pick()
DISPLAY = args.plan_name or args.product or "自定义计划"  # 展示用产品名(--plan 时可用 --plan-name 指定)

def html_for(rnd, zh, subj, angle, body):
    return (f"<p>Hi {VAR},</p>"
            f"<p>{angle}</p>"
            f"<p>{body}</p>"
            f"<p>{SIGN}</p>")

def preview():
    print("★ 渲染视图预览(收件人看到):")
    for rnd, zh, subj, angle in DIRECTIONS[:5]:
        h = html_for(rnd, zh, subj, angle, VARIANTS[0])
        t = re.sub(r'<code[^>]*>\{联系人:([^}]+)\}</code>', lambda m: '【' + m.group(1) + '】', h)
        t = re.sub(r'<[^>]+>', '\n', t)
        t = re.sub(r'&amp;', '&', t)
        lines = [l.strip() for l in t.split('\n') if l.strip()]
        print(f"\n●{args.prefix}{rnd}-{zh}-V01 | 主题:{subj}")
        for l in lines:
            print("  " + l)
    print(f"\n(预览仅代表; 生成={len(DIRECTIONS)}轮x{len(VARIANTS)}={len(DIRECTIONS)*len(VARIANTS)}, 每轮正文句不同+每变体正文句不同)")

def ensure_folder():
    """S8 固化(2026-09-03 用户拍板): 模板必须归入分组,禁止散落在未指定目录。
    --foid 显式给 id 则直接用; 否则按 prefix 查 templates-folder-list, 无则建同名分组。"""
    if args.foid:
        return args.foid
    fl = subprocess.run(["curl", "-sSL", "-X", "POST",
                         f"https://web.laifaxin.com/api/mailbox/templates-folder-list?uid={args.org}",
                         "-H", "Content-Type: application/json", "-H", f"accesstoken: {args.token}", "-d", "{}"],
                        capture_output=True, text=True, timeout=60)
    try:
        lst = json.loads(fl.stdout).get("data") or []
        lst = lst if isinstance(lst, list) else lst.get("list", [])
    except Exception:
        lst = []
    for f in lst:
        if isinstance(f, dict) and f.get("name") == args.prefix:
            print(f"   分组复用: {args.prefix} (foid={f.get('id')})")
            return str(f.get("id"))
    fa = subprocess.run(["curl", "-sSL", "-X", "POST",
                         f"https://web.laifaxin.com/api/mailbox/template-folder-add?uid={args.org}",
                         "-H", "Content-Type: application/json", "-H", f"accesstoken: {args.token}",
                         "-d", json.dumps({"name": args.prefix})],
                        capture_output=True, text=True, timeout=60)
    try:
        d = json.loads(fa.stdout)
        dd = d.get("data") or {}
        fid = dd.get("id") or dd.get("_id") or (dd if isinstance(dd, str) else "")
        if fid and re.fullmatch(r"[0-9a-f]{24}", str(fid)):
            print(f"   分组已建: {args.prefix} (foid={fid})")
            return str(fid)
    except Exception:
        pass
    print("   ⚠️ 分组创建失败——模板将落入未指定目录(不推荐)。可 --foid <id> 重试")
    return "0"


def add(name, subject, html):
    p = {"name": name, "foid": args.foid, "subject": subject, "html": html}
    cmd = ["curl", "-sSL", "-X", "POST", f"https://web.laifaxin.com/api/mailbox/template-add?uid={args.org}",
           "-H", "Content-Type: application/json", "-H", f"accesstoken: {args.token}", "-d", json.dumps(p)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    try:
        d = json.loads(r.stdout)
        tid = d.get("data", {}).get("id", "") if d.get("success") else ""
        if tid and not re.fullmatch(r'[0-9a-f]{24}', str(tid)):
            raise SystemExit(f'id格式异常: {tid}')
        return tid or ("FAIL:" + d.get("message", ""))
    except SystemExit:
        raise
    except Exception as e:
        return "ERR:" + str(e)

if args.preview:
    preview()
    sys.exit(0)

args.foid = ensure_folder()  # S8: 模板必须归入分组(禁散落未指定目录)

require_approval(args.approval, args.project, ("S7", "S8"), what="批量创建模板")

print(f"生成 {DISPLAY} {len(DIRECTIONS)}x{len(VARIANTS)}={len(DIRECTIONS)*len(VARIANTS)} (签名={SIGN}, 每轮/每变体正文句不同):")
results = {}
for rnd, zh, subj, angle in DIRECTIONS:
    for vi, body in enumerate(VARIANTS, 1):
        nm = f"{args.prefix}{rnd}-{zh}-V{vi:02d}{args.suffix}"
        tid = add(nm, subj, html_for(rnd, zh, subj, angle, body))
        results[nm] = tid
        print(f"  {nm} -> {tid}")
        time.sleep(0.3)
print("  (失败行会标 FAIL/ERR——多为 token 失效或网络抖动; 失败的模板不会写入序列,修复后重跑本命令补齐即可,已建的不受影响)")
bad = [n for n, v in results.items() if not re.fullmatch(r"[0-9a-f]{24}", str(v))]
if bad:
    print(f"❌ {len(bad)} 个模板创建失败(示例: {bad[:3]} -> {results[bad[0]]})——中止，勿用此映射重建序列(模板id校验(工具级))")
    sys.exit(1)
if args.out:
    with open(args.out, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"已落盘 {len(results)} 条 name→id 映射到 {args.out}")
