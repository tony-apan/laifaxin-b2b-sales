#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★统一模板生成器（多产品参数化）——生产路径一律 --plan <模板计划JSON>（旧内置 PRODUCTS 事实文案字典已删除,防未溯源事实直接上线）
★差异达标(模板差异实测（工具级）): 正文 = 轮次angle全句 + 变体body全句, 仅 Hi+签名 固定 → 两两 Jaccard≤0.70
★签名硬闸门: --name 须为纯个人昵称(如 Tony/Iris),启动即校验——含公司/职位/产品/邮箱/数字/from → 退出2;渲染只 <p>{昵称}</p>,plan 不允许自带 signature 字段
★产品档案硬闸门: --profile 必填,status 须 confirmed/declined(draft/缺失/结构错 → 退出4);plan.profile_sha256 须匹配当前档案(declined 也写实际 hash)
★事实闸门: 邮件文本(主题/正文轮次句/变体句)出现高风险事实(数字/%/ISO/认证/天数/MOQ/折扣/产能/库存/稀缺/价格/免费/food-grade/certified 等)
  → plan 必须含 claims[],每个命中句子被某条 exact_text 覆盖；source/profile_field/evidence_text 必须对应 product-profile 真实字段（evidence_text 逐字存在于字段内容）;declined 档案不允许任何高风险事实 → 退出2
  (轮次号 R01/中文主题名不参与扫描,只扫用户可见文案)
用法:
  python3 gen_templates.py --token <T> --org <orgId> --prefix "英-皮筏艇-" --suffix=-RT --name Tony \
      --profile runs/<operator_key>/<product_key>/product-profile.md --plan <plan.json> --approval <ap-id> --project <operator_key>/<product_key> [--preview]
  生成后必跑 tools/check_template_diff.py --prefix 实测差异(模板差异实测（工具级）)
  plan JSON = {"profile_sha256": "<当前档案sha256>", "directions": [["R01","中文名","主题纯文案","正文轮次句"], ...],
               "variants": ["正文变体句", ...], "claims": [{"exact_text":"...","source":"...","profile_field":"⑤","evidence_text":"档案字段中的原文"}](出现高风险事实时必填)}
退出码: 0=成功 1=审批/模板创建失败 2=输入校验失败(昵称/plan结构/哈希不匹配/claims) 4=产品档案闸门(draft/缺失/结构错)
"""
import json, subprocess, time, sys, argparse, re, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from approval import require_approval, stable_params_hash
from profile_utils import ensure_same_project_paths, profile_field_facts, profile_gate, validate_nickname
from project_lock import acquire_project_lock
from update_run_state import require_state, update_frontmatter

KB = Path(__file__).resolve().parent.parent

VAR = '<code class="lfxFieldVeriable" contenteditable="false">{联系人:名称}</code>'

ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True)
ap.add_argument("--org", required=True)
ap.add_argument("--product", default="", help="产品名(仅展示/兜底命名;文案一律来自 --plan)")
ap.add_argument("--prefix", required=True, help="模板名前缀,如 英-玻璃瓶-")
ap.add_argument("--suffix", default="-GL", help="命名后缀")
ap.add_argument("--foid", default="", help="模板分组id(默认自动按 --prefix 建同名分组并归入;传 0 = 未指定目录,不推荐——120 个模板会散落)")
ap.add_argument("--name", required=True, help="签名昵称=客户邮件落款·纯个人昵称(如 Tony/Iris;启动即校验:含公司/职位/产品/邮箱/数字/from→退出2)")
ap.add_argument("--profile", required=True, help="★产品档案路径(硬闸门): status 须 confirmed/declined,plan.profile_sha256 须匹配其 sha256(draft/缺失→退出4)")
ap.add_argument("--preview", action="store_true", help="仅草稿展示(渲染视图,不创建;各硬闸门照常执行)")
ap.add_argument("--out", default="", help="可选: 落盘 name→id 映射 JSON(供重建序列 step-save 用;同时写 <out>.meta.json 记录 profile/plan 溯源)")
ap.add_argument("--record", default="", help="项目 operation-record.md；创建全部成功后自动推进 status=S8,next_state=S9")
ap.add_argument("--approval", default="", help="★审批凭证id(审批闸门·工具级): .local/approvals.tsv 或编排器输出")
ap.add_argument("--project", required=True, help="稳定项目键=<operator_key>/<product_key>；须与 --profile frontmatter 一致(审批project匹配)")
ap.add_argument("--plan", default="", help="★模板计划JSON文件路径(必填,生产路径唯一文案来源): {\"profile_sha256\":..,\"directions\":[[\"R01\",\"中文名\",\"主题纯文案\",\"正文轮次句\"],...],\"variants\":[...],\"claims\":[...]}")
ap.add_argument("--plan-name", default="", help="--plan 时的产品名(仅用于展示/提示,如 皮筏艇-经销商; 默认取 --product)")
args = ap.parse_args()
if not args.prefix.strip() or not args.suffix.strip():
    print("❌ --prefix/--suffix 不能为空"); raise SystemExit(2)
SIGN = args.name

# ---------- 签名昵称硬闸门(启动即校验,退出2) ----------
_nick_ok, _nick_why = validate_nickname(SIGN)
if not _nick_ok:
    print(f"❌ --name 不是纯个人昵称({SIGN!r}): {_nick_why}")
    print("   签名=纯个人昵称(如 Tony/Iris);公司名/官网/邮箱/职位/产品绝不进签名——可写入 product-profile 供建档。改好昵称重跑。(exit 2)")
    raise SystemExit(2)

if not args.plan:
    print("❌ 缺 --plan <模板计划JSON>——内置 PRODUCTS 事实文案字典已删除,生产路径一律由 --plan 提供计划(防止未经用户确认/溯源的事实文案上线)。")
    print('   plan JSON: {"profile_sha256":"<当前档案sha256>","directions":[["R01","中文名","主题纯文案","正文轮次句"],...],"variants":["正文变体句",...],"claims":[...](有高风险事实时必填)}')
    raise SystemExit(2)

def load_plan(path):
    """读取 --plan 模板计划JSON: {"profile_sha256":..,"directions":[[轮次号,中文名,主题,正文轮次句],...],"variants":[..],"claims":[..]}
    返回 (directions, variants, plan_dict, plan_sha256); 无效(读不到/JSON错/结构错)→ 明确报错 exit 2,绝不静默兜底。"""
    try:
        plan_bytes = Path(path).read_bytes()
        plan = json.loads(plan_bytes.decode("utf-8"))
    except FileNotFoundError:
        print(f"❌ --plan 文件不存在: {path}"); raise SystemExit(2)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"❌ --plan JSON 解析失败(无效JSON): {path} -> {e}"); raise SystemExit(2)
    except Exception as e:
        print(f"❌ --plan 读取失败: {path} -> {e}"); raise SystemExit(2)
    if not isinstance(plan, dict) or not isinstance(plan.get("directions"), list) or not isinstance(plan.get("variants"), list):
        print(f'❌ --plan JSON 结构无效(应为 {{"profile_sha256":..,"directions": [[轮次号,中文名,主题纯文案,正文轮次句],...], "variants": [正文变体句,...], "claims": [...]}}): {path}'); raise SystemExit(2)
    directions, variants = plan["directions"], plan["variants"]
    if not directions or not variants:
        print(f"❌ --plan 内容为空: directions/variants 至少各 1 条: {path}"); raise SystemExit(2)
    for i, d in enumerate(directions):
        if not isinstance(d, (list, tuple)) or len(d) < 4 or not all(isinstance(x, str) and x.strip() for x in d[:4]):
            print(f"❌ --plan directions[{i}] 无效(应为 [轮次号,中文名,主题纯文案,正文轮次句] 四项字符串): {d!r}"); raise SystemExit(2)
    for i, v in enumerate(variants):
        if not isinstance(v, str) or not v.strip():
            print(f"❌ --plan variants[{i}] 无效(应为非空字符串): {v!r}"); raise SystemExit(2)
    if len({d[0] for d in directions}) != len(directions):
        print("❌ --plan 轮次号重复: directions 每项第 0 位(如 R01)须唯一"); raise SystemExit(2)
    if "signature" in plan:
        print("❌ plan 不允许 signature 字段——签名只能来自 --name(纯昵称),渲染固定为 <p>{昵称}</p> (exit 2)"); raise SystemExit(2)
    plan_sha = hashlib.sha256(plan_bytes).hexdigest()
    return directions, variants, plan, plan_sha

DIRECTIONS, VARIANTS, PLAN, PLAN_SHA = load_plan(args.plan)

# ---------- 产品档案硬闸门(confirmed/declined 才放行;draft/缺失/结构错→退出4) ----------
PROFILE_PATH = Path(args.profile)
if not PROFILE_PATH.is_absolute():
    PROFILE_PATH = KB / PROFILE_PATH
PROFILE_STATUS, PROFILE_ISSUES, _PROFILE_META, PROFILE_SHA = profile_gate(PROFILE_PATH)
EXPECTED_PROJECT = f"{_PROFILE_META.get('operator_key', '').strip()}/{_PROFILE_META.get('product_key', '').strip()}"
if not PROFILE_ISSUES and args.project != EXPECTED_PROJECT:
    PROFILE_ISSUES.append(f"--project={args.project!r} 与档案稳定项目键 {EXPECTED_PROJECT!r} 不一致——拒绝跨运营方/产品复用审批")
if PROFILE_ISSUES:
    print(f"❌ 产品档案闸门未过: {PROFILE_PATH}")
    for _i in PROFILE_ISSUES:
        print(f"   - {_i}")
    print("  指引: python3 tools/product_profile.py init --profile <档案> --operator-key <运营方> --product-key <产品> [--declined] 建档;")
    print("        用户拍板后 confirm --profile <档案> --by <纯昵称> --quote <用户原话> 置 confirmed;declined 可用无具体事实的通用计划。(exit 4)")
    raise SystemExit(4)

# ---------- 档案哈希绑定(plan 必须对准当前档案;declined 也写实际 hash) ----------
if PLAN.get("profile_sha256") != PROFILE_SHA:
    print(f"❌ plan.profile_sha256 与当前档案不匹配: plan={str(PLAN.get('profile_sha256'))[:16]}... != profile={PROFILE_SHA[:16]}...")
    print("   档案已变动或 plan 抄错——用 `python3 tools/product_profile.py status --profile <档案>` 取当前 profile_sha256 更新 plan 后重跑。(exit 2)")
    raise SystemExit(2)

# ---------- 事实闸门: 高风险句子必须被 claims 覆盖(轮次号/中文主题名不扫描) ----------
RISK_RE = re.compile(
    r"\d|[０-９%％]|certif(?:ied|ication)|food[- ]grade|\bMOQ\b|minimum order|discount|\bfree\b|"
    r"price|pricing|stock\w*|inventor\w*|scarc\w*|\blimited\b|allocation|capacity|lead time|"
    r"\bISO\b|\bCE\b|\bFDA\b|\bRoHS\b|\bUL\b|\bSGS\b|\bBPA\b|\bLFGB\b|"
    r"complian\w*|approv\w*|register\w+|warrant\w+|guarantee\w*|turnaround|ships?\s+in|\bweek\b|"
    r"认证|食品级|免费|折扣|库存|稀缺|产能|价格|交期|优惠|现货|清仓|质保|保修|担保|合规",
    re.IGNORECASE,
)

def _sentences(text):
    """切句前剥掉 <b>/</b> 排版标签（四要素铁律要求加粗，但标签不属于句子内容）。"""
    text = re.sub(r"</?b>", "", text or "")
    parts = re.split(r"[.!?。！？；;\n]+", text)
    return [re.sub(r"\s+", " ", s).strip() for s in parts if s and s.strip()]

def _risky_hits():
    """扫描用户可见文案(主题/正文轮次句/变体句)中含高风险事实的句子。轮次号(R01)与中文主题名不参与。"""
    hits = []
    for d in DIRECTIONS:
        for where, text in ((f"{d[0]}/主题", d[2]), (f"{d[0]}/正文轮次句", d[3])):
            for s in _sentences(text):
                if RISK_RE.search(s):
                    hits.append((where, s))
    for vi, body in enumerate(VARIANTS, 1):
        for s in _sentences(body):
            if RISK_RE.search(s):
                hits.append((f"V{vi:02d}/正文变体句", s))
    return hits

def _all_user_sentences():
    """用户可见文案的归一化片段全集（按文案段——主题/轮次句/变体句——整体归一化，不切句：
    CTA 推荐问句式 "Worth a look? Reply ..."，切句会把一段拆成多段导致 exact_text 误判）。
    exact_text 归一化后必须等于某一段的归一化全文（即 exact_text=整段原文），或为空由调用方报错。"""
    sents = set()
    for d in DIRECTIONS:
        for text in (d[2], d[3]):
            if str(text or "").strip():
                sents.add(_normalize_claim_sentence(text))
    for body in VARIANTS:
        if str(body or "").strip():
            sents.add(_normalize_claim_sentence(body))
    sents.discard("")
    return sents

# ---------- evidence↔风险句 强关联校验(静态红队P1): 实体/数字 token 保守子集 ----------
_CLAIM_STD_TOKENS = ("ISO", "CE", "FDA", "RoHS", "UL", "SGS", "BV", "TUV", "EMC", "LVD",
                     "REACH", "ASTM", "IEC", "BPA", "LFGB")
_CLAIM_CLASS_RES = (
    ("TIMING", re.compile(r"\b(?:week|weeks|day|days|hour|hours)\b|周|天|小时|工作日", re.IGNORECASE)),
    ("WARRANTY", re.compile(r"\bwarrant(?:y|ies)\b|\bguarantee\b|质保|保修|担保", re.IGNORECASE)),
    ("CERT", re.compile(r"certif|complian|approv|register|认证|合格|资质", re.IGNORECASE)),
    ("MOQ", re.compile(r"\bMOQ\b|minimum order|起订", re.IGNORECASE)),
    ("FOODGRADE", re.compile(r"food[- ]grade|食品级", re.IGNORECASE)),
    ("FREE", re.compile(r"\bfree\b|免费", re.IGNORECASE)),
    ("PRICE", re.compile(r"\bprice|pricing|价格|报价", re.IGNORECASE)),
    ("DISCOUNT", re.compile(r"discount|off\b|折扣|优惠", re.IGNORECASE)),
    ("STOCK", re.compile(r"stock|inventory|allocation|库存|现货|清仓", re.IGNORECASE)),
    ("CAPACITY", re.compile(r"capacity|产能", re.IGNORECASE)),
    ("SCARCITY", re.compile(r"scarce|scarcity|limited|slots?\s+(?:fill|clos)|稀缺|名额|档期", re.IGNORECASE)),
)

def _claim_tokens(text):
    """抽取风险实体(认证标准等, 逐个精确) / 语义类(时限·保修·认证·MOQ·食品级, 跨语言任一命中) / 数字 token。"""
    low = str(text or "").lower()
    ents = set()
    for std in _CLAIM_STD_TOKENS:
        if re.search(r"(?<![a-z0-9])" + re.escape(std.lower()) + r"(?![a-z0-9])", low):
            ents.add(std)
    for name, rx in _CLAIM_CLASS_RES:
        if rx.search(low):
            ents.add(name)
    nums = set()
    for tok in re.findall(r"\d[\d,，.]*", str(text or "")):
        t = tok.replace(",", "").replace("，", "").rstrip(".")
        # 年份(1900-2099)=目录/日程上下文，非需溯源事实数字——不参与强关联
        if t and not re.fullmatch(r"(?:19|20)\d{2}", t):
            nums.add(t)
    return ents, nums

def _normalize_claim_sentence(text):
    """归一化 exact_text：剥 <b> 标签+压缩空白（★不切句——CTA 推荐问句式，如 "Worth a look? Reply ..."，
    按切句器会被拆成两段导致误判非完整句）。完整性由"必须逐字出现在文案中"保证，而非句数。"""
    return re.sub(r"\s+", " ", re.sub(r"</?b>", "", str(text or ""))).strip()


def _check_claim_items(claims):
    facts = profile_field_facts(PROFILE_PATH)
    for i, c in enumerate(claims):
        if not isinstance(c, dict) or not all((c.get(k) or "").strip() for k in ("exact_text", "source", "profile_field", "evidence_text")):
            print(f"❌ plan.claims[{i}] 无效: 每项须含 exact_text/source/profile_field/evidence_text 且全部非空: {c!r} (exit 2)")
            raise SystemExit(2)
        field_text = str(c["profile_field"])
        m = re.search(r"[1-8①②③④⑤⑥⑦⑧]", field_text)
        if not m:
            print(f"❌ plan.claims[{i}].profile_field 须指向档案 ①..⑧ 某字段: {field_text!r} (exit 2)")
            raise SystemExit(2)
        token = m.group(0)
        field_no = int(token) if token in "12345678" else "①②③④⑤⑥⑦⑧".index(token) + 1
        fact = facts.get(field_no, {})
        source = (fact.get("source") or "").strip()
        content = (fact.get("content") or "").strip()
        if not content or content in ("（待补）", "待补") or source.lower() in ("", "none", "推断"):
            print(f"❌ plan.claims[{i}] 指向的档案字段 {field_no} 没有可引用的已确认内容/来源(source={source or 'none'}) (exit 2)")
            raise SystemExit(2)
        if str(c["source"]).strip() != source:
            print(f"❌ plan.claims[{i}].source 与档案字段 {field_no} 的 source 不一致: claim={c['source']!r} profile={source!r} (exit 2)")
            raise SystemExit(2)
        evidence = re.sub(r"\s+", " ", str(c["evidence_text"])).strip()
        content_norm = re.sub(r"\s+", " ", content).strip()
        if evidence not in content_norm:
            print(f"❌ plan.claims[{i}].evidence_text 未逐字存在于档案字段 {field_no} 内容中: {evidence!r} (exit 2)")
            raise SystemExit(2)
        # 强关联(静态红队P1): 风险句中的实体(ISO/CE/FDA/RoHS/UL...)与全部数字 token 必须在 evidence 中出现
        s_ent, s_num = _claim_tokens(str(c["exact_text"]))
        e_ent, e_num = _claim_tokens(evidence)
        miss_ent, miss_num = sorted(s_ent - e_ent), sorted(s_num - e_num)
        if miss_ent or miss_num:
            print(f"❌ plan.claims[{i}].evidence_text 与风险句强关联不足: 缺实体token {miss_ent} / 缺数字token {miss_num}——"
                  "evidence 须包含风险句中的认证标准/时限/保修等实体与全部数字, 不允许用无关真实短语挂靠声明 (exit 2)")
            raise SystemExit(2)

def validate_claims():
    hits = _risky_hits()
    claims = PLAN.get("claims")
    if claims is not None:
        if not isinstance(claims, list):
            print("❌ plan.claims 须为数组(每项 {exact_text, source, profile_field, evidence_text}) (exit 2)"); raise SystemExit(2)
        # exact_text 必须是文案中的完整句子(逐句相等; 不允许半句/拼句/无关句)——先查, 报错更准
        norm = [_normalize_claim_sentence(c["exact_text"]) for c in claims]
        all_sents = _all_user_sentences()
        unknown = [str(claims[i]["exact_text"]) for i, nc in enumerate(norm) if not nc or nc not in all_sents]
        if unknown:
            print("❌ 以下 claims[].exact_text 不是文案中的完整句子(把整句原文逐字写进 exact_text, 不允许半句/拼接/无关句):")
            for nc in unknown[:5]:
                print(f"   - {nc}")
            raise SystemExit(2)
        _check_claim_items(claims)
    if not hits:
        print("  ✅ 事实闸门: 未检出高风险事实句(通用口径)")
        return
    if PROFILE_STATUS == "declined":
        print("❌ 档案 status=declined——只能用无具体事实的通用计划,但文案出现高风险事实:")
        for loc, s in hits:
            print(f"   - [{loc}] {s}")
        print("   要用具体事实须先让用户提供资料并 confirm 档案(见 tools/product_profile.py)。 (exit 2)")
        raise SystemExit(2)
    if not claims:
        print("❌ 文案出现高风险事实但 plan 缺 claims 数组(每项 {exact_text, source, profile_field},句子原文写进 exact_text):")
        for loc, s in hits:
            print(f"   - [{loc}] {s}")
        raise SystemExit(2)
    norm_list = [_normalize_claim_sentence(c["exact_text"]) for c in claims]
    missing = [(loc, s) for loc, s in hits if not any(s in nc for nc in norm_list)]
    if missing:
        print("❌ 以下高风险句子未被 claims[].exact_text 覆盖(把整句原文逐字写进 exact_text):")
        for loc, s in missing:
            print(f"   - [{loc}] {s}")
        raise SystemExit(2)
    print(f"  ✅ 事实闸门: {len(hits)} 个高风险句子全部被 claims 完整逐句覆盖(来源可溯+evidence强关联, 档案 {PROFILE_STATUS})")

validate_claims()
print(f"  ✅ --plan 加载: {args.plan} ({len(DIRECTIONS)}轮方向×{len(VARIANTS)}变体, 档案={PROFILE_STATUS} sha={PROFILE_SHA[:12]}..., 签名={SIGN})")
DISPLAY = args.plan_name or args.product or "自定义计划"  # 展示用产品名(--plan 时可用 --plan-name 指定)

def html_for(rnd, zh, subj, angle, body):
    return (f"<p>Hi {VAR},</p>"
            f"<p>{angle}</p>"
            f"<p>{body}</p>"
            f"<p>{SIGN}</p>")

# ---------- 模板四要素铁律断言（★2026-09-04 用户拍板：sequence-config「模板四要素铁律」的工具级落地） ----------
_CTA_MARK_RE = re.compile(
    r"\b(?:reply|respond|just reply|yes or no|worth a look|shall i|should i|want me to)\b|"
    r"回复|回个|要不要|需要我",
    re.IGNORECASE)
_GENERIC_CTA_RE = re.compile(
    r"feel free to (?:reach out|contact)|look forward to hearing|don'?t hesitate",
    re.IGNORECASE)
_ADVANTAGE_RE = re.compile(
    r"\d+\s*(?:-?\s*(?:year|day|week|month)s?|年|天|日|个月|pcs|pieces?|units?|kg|tons?)|"
    r"MOQ|warranty|guarantee|repair[- ]friendly|drop[- ]?stitch|hypalon|pvc|seam|load|psi|denier|"
    r"food[- ]grade|lead time|质保|保修|交期|修复|食品级|起订",
    re.IGNORECASE)

def check_four_elements():
    """四要素+视觉扫读铁律（sequence-config）：①变体句含CTA（具体可回复）②优势具体化
    ③<b>加粗2-4处且含加粗回复关键词④CTA可回复性 ⑤整封≤120词 ⑥CTA回复关键词必须加粗。
    违例列出并 exit 2。claims 已单独校验事实来源。"""
    issues = []
    samples = []
    for d in DIRECTIONS:
        samples.append((f"{d[0]}", d[2], d[3]))
    for vi, body in enumerate(VARIANTS, 1):
        samples.append((f"V{vi:02d}", "", body))
    for loc, subj, text in samples:
        bolds = len(re.findall(r"<b>", text))
        if bolds and (bolds < 2 or bolds > 4):
            issues.append(f"[{loc}] <b>加粗数量={bolds}（要求2-4处）")
        # CTA 铁律只校验【变体句】——变体=每封邮件的收尾主体，CTA 是嵌入元素（sequence-config §42）；
        # 轮次句是铺陈（钩子/优势），不强制每句带 CTA
        is_variant = loc.startswith("V")
        if is_variant:
            if not _CTA_MARK_RE.search(text):
                issues.append(f"[{loc}] 缺CTA——变体句末段必须有具体可回复动作（Reply \"X\" / yes-or-no / 选项）")
            elif _GENERIC_CTA_RE.search(text):
                issues.append(f"[{loc}] 泛CTA违例（feel free/look forward——没说清回什么）")
            if not _ADVANTAGE_RE.search(text):
                issues.append(f"[{loc}] 缺具体化优势——须带数字/实体（质保年数/交期天数/材料工艺），裸能力陈述=违例")
            # 视觉扫读：CTA 回复关键词必须加粗（Reply "<b>X</b>" 或 <b>"X"</b>）
            plain = re.sub(r"<[^>]+>", "", text)
            # 提取回复关键词：优先带引号形式 Reply "X"；否则 Reply X（到标点/句尾）
            m = (re.search(r'(?:reply|respond)\s+["\']([A-Za-z0-9 ]{1,20})["\']', plain, re.IGNORECASE)
                 or re.search(r'(?:reply|respond)\s+to?\s*["\']?([A-Za-z][A-Za-z0-9 ]{1,20})["\']?(?=[,.;!?]|$)', plain, re.IGNORECASE))
            if m:
                kw = m.group(1).split()[0]
                bolded = re.search(r'<b>[^<]*' + re.escape(kw) + r'[^<]*</b>', text, re.IGNORECASE)
                if not bolded:
                    issues.append(f"[{loc}] CTA回复关键词「{kw}」未加粗——买家扫读必须看到回复动作（Reply \"<b>{kw}</b>\"）")
    # 视觉扫读：整封（钩子段+卖点段+CTA段，不含落款）≤120 词
    for d in DIRECTIONS:
        full_text = re.sub(r"<[^>]+>", " ", f"{d[2]} {d[3]} {VARIANTS[0]}")
        words = len(re.findall(r"[A-Za-z0-9']+", full_text))
        if words > 120:
            issues.append(f"[{d[0]}] 整封词数={words}（上限120）——超长=移动端折叠=CTA不可见")
    if issues:
        print(f"❌ 模板四要素+视觉扫读铁律未过（{len(issues)} 处违例）——按 sequence-config 修改 plan 后重跑：")
        for i in issues[:10]:
            print(f"   - {i}")
        raise SystemExit(2)
    print(f"  ✅ 四要素+视觉扫读铁律: {len(samples)} 句全部合规（CTA/优势/加粗/词数）")

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

check_four_elements()

def ensure_folder():
    """S8 固化(2026-09-03 用户拍板): 模板必须归入分组,禁止散落在未指定目录。
    --foid 显式给 id 则直接用(★foid=0=未指定目录, 拒绝); 否则按 prefix 查 templates-folder-list,
    无则建同名分组; 解析/创建失败必须退出——不允许模板散落未指定目录。"""
    if args.foid:
        if str(args.foid).strip() == "0":
            print("❌ --foid 0 = 未指定目录, 120 个模板会散落——S8 固化: 模板必须归入分组, 传已有分组 id 或留空自动建 (exit 1)")
            raise SystemExit(1)
        return str(args.foid).strip()
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
    print("❌ 模板分组解析/创建失败——为避免模板散落未指定目录, 已中止(未创建任何模板)。稍后重跑, 或 --foid <已有分组id> 指定 (exit 1)")
    raise SystemExit(1)


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
    if not args.record:
        print("❌ 模板预览必须带 --record <operation-record.md>，以便换机续接记录S7"); sys.exit(2)
    if not ensure_same_project_paths(args.record, PROFILE_PATH):
        print("❌ --record 与 --profile 不在同一项目目录"); sys.exit(4)
    try: require_state(args.record, ("S6", "S7"))
    except ValueError as exc: print(f"❌ {exc}"); sys.exit(4)
    preview()
    update_frontmatter(args.record, {"status": "S7", "next_state": "S8"}, expected_states=("S6", "S7"))
    print(f"✅ 运行状态已推进: {args.record} → S7 (next=S8；仍未创建线上模板)")
    sys.exit(0)
if not args.record or not args.out:
    print("❌ 正式创建模板必须带 --record <operation-record.md> 和 --out <项目/tmap.json>，否则换机状态/序列映射无法恢复"); sys.exit(2)
if not ensure_same_project_paths(args.record, PROFILE_PATH):
    print("❌ --record 与 --profile 不在同一项目目录"); sys.exit(4)
try: require_state(args.record, ("S6", "S7", "S8")); acquire_project_lock(args.record, "gen_templates")
except (ValueError, RuntimeError) as exc: print(f"❌ {exc}"); sys.exit(4)

# ★审批顺序(静态红队P1): 审批闸门必须先于任何平台写(ensure_folder 的分组查询/创建也是写路径的一部分)
try:
    out_rel = str(Path(args.out).resolve().relative_to(KB.resolve()))
except ValueError:
    out_rel = str(Path(args.out).resolve())
binding = {"project": args.project, "org_sha256": hashlib.sha256(str(args.org).encode()).hexdigest(),
           "profile": {"sha256": PROFILE_SHA, "status": PROFILE_STATUS, "version": _PROFILE_META.get("profile_version", "")},
           "plan": {"sha256": PLAN_SHA}, "name": SIGN, "prefix": args.prefix, "suffix": args.suffix,
           "foid": str(args.foid or "auto"), "out": out_rel}
require_approval(args.approval, args.project, ("S7", "S8"), what="批量创建模板", expected_hash=stable_params_hash(binding))

args.foid = ensure_folder()  # S8: 模板必须归入分组(禁散落未指定目录; 失败即退出)

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
    out_p = Path(args.out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"已落盘 {len(results)} 条 name→id 映射到 {args.out}")
    # 溯源元数据(与 tmap 同目录; 静态红队P1): 写完 tmap 后计算其内容 hash,
    # 连同 project_key/org_sha256(哈希非明文)/档案路径(相对KB)+hash+status/plan 哈希 供 build_sequence 逐项校验
    tmap_sha = hashlib.sha256(out_p.read_bytes()).hexdigest()
    try:
        profile_rel = str(PROFILE_PATH.resolve().relative_to(KB.resolve()))
    except ValueError:
        profile_rel = str(PROFILE_PATH)
    meta = {"tmap_sha256": tmap_sha, "project_key": args.project,
            "org_sha256": hashlib.sha256(str(args.org).encode("utf-8")).hexdigest(),
            "profile_path": str(PROFILE_PATH), "profile_path_rel": profile_rel,
            "profile_sha256": PROFILE_SHA, "profile_status": PROFILE_STATUS,
            "plan_sha256": PLAN_SHA, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(args.out + ".meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"已落盘溯源元数据到 {args.out}.meta.json (tmap_sha={tmap_sha[:12]}..., profile={PROFILE_STATUS} sha={PROFILE_SHA[:12]}..., plan_sha={PLAN_SHA[:12]}...)")
if args.record:
    update_frontmatter(args.record, {"status": "S8", "next_state": "S9", "updated": time.strftime("%Y-%m-%d"),
                                      "profile_version": f'"{_PROFILE_META.get("profile_version", "")}"',
                                      "profile_sha256": f'"{PROFILE_SHA}"'}, expected_states=("S6", "S7", "S8"))
    print(f"✅ 运行状态已推进: {args.record} → S8 (next=S9)")
