#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★产品档案与签名硬闸门·公共库(stdlib only)——昵称校验/机读 frontmatter/哈希/档案结构校验/第三方资料检测。
最终口径(2026-09-04 用户拍板; 静态红队P1/P2加固 2026-09-04):
  - 邮件正文签名区=纯个人昵称,禁止公司名/官网/邮箱/职位/产品/电话/认证等任何其他内容;
    昵称校验另拒 职能词(support/admin/info/team/采购部等)/『X总』头衔/emoji/控制字符换行。
  - 用户自己的公司名/官网/邮箱/认证/产能/MOQ/交期/价格带可由 AI 主动索取并写入本地
    product-profile 供客群/事实分析;公司身份字段绝不进签名。
    (注意: 实际邮箱/电话号码本身也不得写入 product-profile——运营方自己的联系邮箱只放
     运营方档案(.local/operators/<operator_key>.md)的 contact_email 字段。)
  - 客户/潜在联系人等第三方联系方式不得写进 product-profile(实际邮箱/电话/清单标记/清单表头均拦)。
  - 产品档案 ①~⑧ 须全存在, 每字段 content/source/confidence 齐; source 值域
    none/用户/URL/URL:<url>/推断, confidence 值域 low/medium/high; confirmed 档案的具体
    事实(数字/认证)不得标 none/推断; sources_status/sources_present 须与字段实际一致。
被 tools/product_profile.py / tools/flow_orchestrator.py / tools/gen_templates.py /
   tools/operator_profile.py / tools/build_sequence.py 复用。
"""
import hashlib
import re
import unicodedata
from pathlib import Path

# ---------- 昵称硬校验 ----------

# 公司/职位/产品/职能常见词(中英)——出现在签名昵称里即拒绝(签名=纯个人昵称)
_NICK_COMPANY_WORDS_EN = (
    "corp", "corporation", "incorporated", "inc", "ltd", "limited", "llc", "llp",
    "company", "co", "group", "holding", "holdings", "industry", "industries",
    "manufacturing", "manufacturer", "factory", "supplier", "trading", "trader",
    "exporter", "export", "importer", "import", "enterprise", "enterprises",
    "solutions", "technology", "tech", "official", "store", "shop", "brand",
    "founder", "cofounder", "ceo", "cto", "coo", "cfo", "president", "director",
    "manager", "sales", "representative", "specialist", "supervisor", "owner",
    "boss", "chairman", "partner", "agent",
    # 职能/公共信箱词(静态红队P1): support/admin/info/team 等冒充个人昵称
    "support", "admin", "info", "team", "service", "help", "helpdesk",
    "assistant", "secretary", "office", "procurement", "purchasing", "sourcing",
    "noreply", "no-reply", "notification", "notifications", "mailer",
    "postmaster", "webmaster", "hr", "finance", "legal",
    "aftersales", "after-sales",
)
_NICK_COMPANY_WORDS_ZH = (
    "公司", "集团", "有限", "责任", "工厂", "制造", "科技", "技术", "贸易", "实业",
    "供应", "官网", "旗舰店", "专营", "专卖", "直营", "产品", "事业", "部门",
    "经理", "总监", "主管", "销售", "业务员", "创始人", "老板", "董事长", "代表",
    "客服", "厂长", "部长", "主任", "负责人", "运营",
    # 职能/公共身份词(静态红队P1): 采购部/团队/前台/行政等不是个人昵称
    "采购部", "采购", "团队", "服务", "前台", "行政", "人事", "财务", "法务",
    "工作室", "工作组", "部",
)
_NICK_FORBIDDEN_SYMBOLS = "|/\\()[]{}<>（）【】｛｝｜／"  # 竖线/斜杠/括号等
_NICK_MAX_LEN = 24
# emoji/杂项符号区(静态红队P1): 昵称不允许任何 emoji/装饰符号
_NICK_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U0001F1E6-\U0001F1FF\U00002600-\U000027BF"
    "\U00002B00-\U00002BFF\U0000FE00-\U0000FE0F\U0000200B-\U0000200F"
    "\U00002190-\U000021FF\U00002700-\U000027BF]"
)


def _nickname_bad_char(name):
    """返回 (是否含禁用字符, 原因): 控制字符/换行/零宽字符/未定义码位/emoji。"""
    for ch in name:
        if ch in ("\t", "\n", "\r"):
            return True, "控制字符/换行"
        cat = unicodedata.category(ch)
        if cat in ("Cc", "Cf", "Cs", "Co", "Cn"):
            return True, f"控制/不可见/异常字符(U+{ord(ch):04X})"
    if _NICK_EMOJI_RE.search(name):
        return True, "emoji/表情符号"
    return False, ""
_NICK_DOMAIN_RE = re.compile(
    r"(?:https?://|www\.)|[a-z0-9-]+\.(?:com|net|org|co|io|cn|com\.cn|xin|shop|store|tech|site|online)\b",
    re.IGNORECASE,
)


def validate_nickname(name):
    """昵称硬校验(签名闸门第一环)。返回 (ok: bool, reason: str)。
    拒绝: 空 / 过长(>24) / email / URL或域名 / 数字 / 竖线·斜杠·括号 / from /
          公司·职位·产品·职能常见词(中英, 含 support/admin/info/team/采购部等) /
          『X总』类头衔 / emoji / 控制字符·换行。
    通过例: Tony / Iris / 老王 / Jean-Pierre。"""
    if not isinstance(name, str) or not name.strip():
        return False, "昵称为空——签名必须是纯个人昵称(如 Tony/Iris)"
    name = name.strip()
    if len(name) > _NICK_MAX_LEN:
        return False, f"昵称过长(>{_NICK_MAX_LEN}字符)——落款应是简短个人称呼"
    bad, why = _nickname_bad_char(name)
    if bad:
        return False, f"昵称含{why}——签名只能是纯文本个人称呼"
    if any(ch.isspace() for ch in name):
        return False, "昵称含空格/换行——为保证签名只有单一个人称呼，请用单个昵称（如 Tony/Jean-Pierre/老王）"
    if "," in name or "，" in name:
        return False, "昵称含逗号/分隔符——禁止拼接公司或职位"
    if "@" in name:
        return False, "昵称含邮箱特征(@)——签名禁止邮箱"
    if _NICK_DOMAIN_RE.search(name):
        return False, "昵称含网址/域名特征——签名禁止官网"
    if re.search(r"[0-9０-９]", name):
        return False, "昵称含数字——签名只能是纯个人称呼"
    if any(ch in name for ch in _NICK_FORBIDDEN_SYMBOLS):
        return False, "昵称含竖线/斜杠/括号等符号——不允许"
    if name == "总" or (len(name) >= 2 and name.endswith("总")):
        return False, "昵称是『X总』类头衔称呼——签名须用姓名/花名(如 张伟/老王/Tony), 不带头衔"
    low = name.lower()
    if re.search(r"\bfrom\b", low):
        return False, "昵称含 from(『个人 from 公司』写法)——签名禁止携带公司身份;公司名只写入产品档案"
    for w in _NICK_COMPANY_WORDS_EN:
        if re.search(r"\b" + re.escape(w) + r"\b", low):
            return False, f"昵称含公司/职位/产品词『{w}』——签名=纯个人昵称,公司身份只入档案不进签名"
    for w in _NICK_COMPANY_WORDS_ZH:
        if w in name:
            return False, f"昵称含公司/职位/产品词『{w}』——签名=纯个人昵称,公司身份只入档案不进签名"
    return True, ""


# ---------- 机读 frontmatter(无需 PyYAML) ----------

def split_markdown(text):
    """把 markdown 文本拆成 (frontmatter 原始行列表, 正文)。
    约定: 文件以 --- 行开头的 frontmatter 块(至下一个 --- 行), 无则 frontmatter 为空。"""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return [], text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], "\n".join(lines[i + 1:])
    return [], text  # 有头无尾=格式坏,按无 frontmatter 处理(校验会报缺字段)


def parse_frontmatter(path):
    """解析简单 key:value frontmatter(冒号只按第一个切,跳过空行与 # 注释行)。返回 dict。"""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        return {}
    meta = {}
    for line in split_markdown(text)[0]:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if ":" not in s:
            continue
        key, _, val = s.partition(":")
        meta[key.strip()] = val.strip()
    return meta


def read_profile(path):
    """读取档案: 返回 (meta: dict, body: str)。文件不存在/读不了 → ({}, "")。"""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        return {}, ""
    fm_lines, body = split_markdown(text)
    meta = {}
    for line in fm_lines:
        s = line.strip()
        if not s or s.startswith("#") or ":" not in s:
            continue
        key, _, val = s.partition(":")
        meta[key.strip()] = val.strip()
    return meta, body


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def profile_sha256(path):
    """整个档案文件的 sha256(十六进制)。文件不存在返回空串。"""
    try:
        return _sha256_bytes(Path(path).read_bytes())
    except Exception:
        return ""


def content_sha256(path):
    """档案正文(去 frontmatter)的稳定 sha256: 逐行去行尾空白、整体去首尾空白后哈希。
    用途: confirm 时锁定正文——正文一字未改则哈希不变, 改了任何实质内容即失配。"""
    _, body = read_profile(path)
    norm = "\n".join(l.rstrip() for l in body.split("\n")).strip()
    return _sha256_bytes(norm.encode("utf-8"))


def profile_field_facts(path):
    """读取 product-profile 正文 ①..⑧ 字段，返回 {字段号: {content, source, confidence}}。"""
    _meta, body = read_profile(path)
    facts = {}
    current = None
    for raw in body.splitlines():
        line = raw.strip()
        m = re.match(r"^##\s*([①②③④⑤⑥⑦⑧])", line)
        if m:
            current = "①②③④⑤⑥⑦⑧".index(m.group(1)) + 1
            facts[current] = {"content": "", "source": "", "confidence": ""}
            continue
        if current is None:
            continue
        if line.startswith("- 内容："):
            facts[current]["content"] = line.split("：", 1)[1].strip()
        elif line.lower().startswith("- source:"):
            facts[current]["source"] = line.split(":", 1)[1].strip()
        elif line.lower().startswith("- confidence:"):
            facts[current]["confidence"] = line.split(":", 1)[1].strip()
    return facts


def ensure_same_project_paths(record_path, profile_path):
    """operation-record 与 product-profile 必须位于同一项目目录，防跨项目状态污染。"""
    try:
        return Path(record_path).resolve().parent == Path(profile_path).resolve().parent
    except OSError:
        return False


# ---------- 产品档案结构校验 ----------

PROFILE_STATUSES = ("draft", "confirmed", "declined")
SOURCES_PRESENT_VALUES = ("yes", "partial", "no")
SOURCES_STATUS_VALUES = ("requested", "provided", "partial", "declined")
FIELD_PLACEHOLDERS = ("", "（待补）", "待补")  # 视为"未填"的占位内容
SOURCE_EXACT_VALUES = ("none", "用户", "推断")  # URL来源须写 URL:https://... 完整地址
CONFIDENCE_VALUES = ("low", "medium", "high")

# 第三方联系方式清单标记——档案(用户自己的商业资产档案)里出现即违规
THIRD_PARTY_MARKERS = (
    "customer_email", "contact_email", "customer_emails", "contact_emails",
    "customer_list", "contact_list",
    "客户邮箱", "联系人邮箱", "买家邮箱", "潜在客户邮箱", "客户邮件地址",
    "联系人邮件", "客户名单", "联系人清单", "客户联系方式清单",
)

_REQUIRED_KEYS = ("profile_version", "status", "operator_key", "product_key",
                  "created_at", "updated_at", "sources_status", "sources_present")


# ---------- 第三方资料检测(静态红队P1: 实际邮箱/电话/联系人清单表头; 不误伤URL) ----------

_URL_STRIP_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"'）)\】]+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
# 电话候选: 7~15 位数字(可含 +/空格/横线/括号); 前后不能紧贴字母数字(避免命中型号/十六进制id)
_PHONE_CAND_RE = re.compile(r"(?<![0-9A-Za-z])\+?\d[\d\s\-()–]{5,19}\d(?![0-9A-Za-z])")
_DATE_LIKE_RE = re.compile(
    r"^\s*(?:19|20)\d{2}\s*[-/年.]\s*(?:0?[1-9]|1[0-2])\s*[-/月.]\s*(?:0?[1-9]|[12]?\d|3[01])\s*日?\s*$")
_YEAR_RANGE_RE = re.compile(r"^\s*(?:19|20)\d{2}\s*[-–/]\s*(?:19|20)\d{2}\s*$")
# 候选前若紧贴标准号/编号类前缀(ISO 9001-2015 / GB 4806 / SKU-xxx)则不算电话
_CODE_PREFIX_RE = re.compile(
    r"(?:ISO|GB|GB/T|IEC|EN|ASTM|CE|FDA|RoHS|REACH|EMC|LVD|TUV|SGS|BV|IP|SKU|MPN|SN|No|№|#|"
    r"型号|标准|版本|证书|批号|货号|款号|色号)\s*[.:#\-]?\s*$", re.IGNORECASE)
# 候选后紧跟数量单位(3000000 只/2000000 pcs)则更像产能数字而非电话
_QUANTITY_SUFFIX_RE = re.compile(
    r"^\s*(?:[只件个双支把套台辆箱吨克升]|千克|公斤|平方|万|million|pcs|pc|"
    r"pieces?|pairs?|sets?|units?|cartons?|sqm|m2|m²|ml|kg)(?![A-Za-z])", re.IGNORECASE)
# 联系人清单表头: markdown 表格行中同时出现 ≥2 类(姓名/邮箱/电话·IM)表头
_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
_TABLE_HEADER_CELL_CATS = (
    (re.compile(r"^(?:姓名|名字|称谓|联系人|contact\s*person|full\s*name|name)$", re.IGNORECASE), "姓名"),
    (re.compile(r"^(?:邮箱|电子邮件|e-?mail|e-?mail\s*address|邮件地址)$", re.IGNORECASE), "邮箱"),
    (re.compile(r"^(?:电话|手机|手机号|联系电话|联系方式|phone|tel|telephone|mobile|whatsapp|微信|wechat|line|skype)$",
                re.IGNORECASE), "电话/IM"),
)
# 客户/买家/联系人清单类字样(用于运营方档案字段值扫描)
LIST_MARKER_WORDS = (
    "customer_list", "customer list", "contact_list", "contact list",
    "buyer_list", "buyer list", "customer_email", "customer_emails",
    "buyer_email", "contact_emails", "采购名单",
    "客户名单", "客户清单", "买家名单", "买家清单", "联系人名单", "联系人清单",
    "客户邮箱", "买家邮箱", "联系人邮箱", "客户联系方式清单",
)


def strip_urls(text):
    """去掉 http(s)/www URL 片段, 避免把网址里的 @/数字误判成邮箱/电话。"""
    return _URL_STRIP_RE.sub(" ", text or "")


def find_emails(text):
    """返回文本中的实际邮箱列表(先剥离 URL 防误伤, 如 https://x.com/@handle)。"""
    return _EMAIL_RE.findall(strip_urls(text))


def find_phones(text):
    """返回文本中的疑似电话号码列表(7~15位数字; 排除日期/标准号/年份区间/数量)。"""
    text = strip_urls(text)
    out = []
    for m in _PHONE_CAND_RE.finditer(text):
        cand = m.group(0).strip()
        digits = re.sub(r"\D", "", cand)
        if not (7 <= len(digits) <= 15):
            continue
        if _DATE_LIKE_RE.match(cand) or _YEAR_RANGE_RE.match(cand):
            continue
        if _CODE_PREFIX_RE.search(text[max(0, m.start() - 14):m.start()]):
            continue
        if _QUANTITY_SUFFIX_RE.match(text[m.end():]):
            continue
        out.append(re.sub(r"\s+", " ", cand))
    return out


def find_contact_list_headers(text):
    """返回 markdown 表格中的联系人清单表头行(≥2 类 联系要素列)。"""
    hits = []
    for line in (text or "").splitlines():
        m = _TABLE_ROW_RE.match(line)
        if not m:
            continue
        cats = set()
        for cell in m.group(1).split("|"):
            c = cell.strip().strip("*").strip()
            for rx, name in _TABLE_HEADER_CELL_CATS:
                if c and rx.match(c):
                    cats.add(name)
                    break
        if len(cats) >= 2:
            hits.append(line.strip())
    return hits


def find_list_markers(text):
    """返回文本中出现的客户/买家/联系人清单类标记词。"""
    low = (text or "").lower()
    return [w for w in LIST_MARKER_WORDS if w.lower() in low]


def mask_email(email):
    loc, _, dom = email.partition("@")
    tld = dom.rsplit(".", 1)[-1] if "." in dom else ""
    return f"{loc[:1]}***@***.{tld}" if tld else f"{loc[:1]}***@***"


def mask_phone(phone):
    digits = re.sub(r"\D", "", phone)
    return f"{digits[:3]}***{digits[-2:]}" if len(digits) >= 5 else "***"


def detect_third_party_contact(text, label="档案"):
    """检测产品档案里不得出现的第三方联系方式: 实际邮箱/电话号码/联系人清单表头。
    返回问题列表(样本脱敏输出)。URL 本身不算违规(先剥离再扫, 不误伤)。"""
    issues = []
    emails = find_emails(text)
    if emails:
        issues.append(f"{label}含实际邮箱({len(emails)}处, 如 {mask_email(emails[0])})——"
                      "运营方自己的联系邮箱只放运营方档案 contact_email 字段, 任何客户/第三方邮箱禁止写入产品档案")
    phones = find_phones(text)
    if phones:
        issues.append(f"{label}含疑似电话号码({len(phones)}处, 如 {mask_phone(phones[0])})——电话号码禁止写入产品档案")
    for h in find_contact_list_headers(text):
        issues.append(f"{label}含联系人清单表头『{h[:60]}』——客户/联系人名单禁止写入产品档案")
    return issues


# ---------- 字段结构/来源校验(静态红队P1) ----------

_CONCRETE_FACT_RE = re.compile(
    r"[0-9０-９%％]|ISO\s*\d|\bCE\b|\bFDA\b|RoHS|\bUL\b|\bSGS\b|\bBPA\b|LFGB|"
    r"认证|食品级|food[- ]grade|certif|complian|approved|registered|质保|保修|warrant",
    re.IGNORECASE)


def _source_ok(src):
    low = (src or "").strip().lower()
    if low in SOURCE_EXACT_VALUES:
        return True
    return bool(re.match(r"^url:https?://[^\s]+$", low))


def _fact_stats(facts):
    """按字段来源归类: (有来源字段号, 推断字段号, 有内容但无来源字段号)。占位内容不计。"""
    provided, inferred, unsourced = [], [], []
    for n in sorted(facts):
        f = facts.get(n) or {}
        content = (f.get("content") or "").strip()
        src = (f.get("source") or "").strip().lower()
        if content in FIELD_PLACEHOLDERS:
            continue
        if src == "推断":
            inferred.append(n)
        elif src not in ("", "none") and _source_ok(src):
            provided.append(n)
        else:
            unsourced.append(n)
    return provided, inferred, unsourced


def validate_product_profile(path, require_confirmed=True):
    """校验产品档案结构, 返回问题列表(空列表=通过)。
    require_confirmed=True 时额外要求 status=confirmed。
    检查项: 文件存在 / 机读 frontmatter / 必需字段非空 / 枚举值合法 /
            ①~⑧ 字段全存在且每字段 content/source/confidence 齐 /
            source 值域(none/用户/URL/URL:<url>/推断)·confidence 值域(low/medium/high) /
            confirmed 时具体事实(数字/认证)不得 source=none/推断 /
            sources_status·sources_present 与字段实际一致 /
            confirmed 时 confirmed_at·confirmed_by·content_sha256 齐且哈希匹配 /
            全文不得含第三方联系方式(实际邮箱/电话/清单标记/清单表头)。"""
    issues = []
    p = Path(path)
    if not p.is_file():
        return [f"档案文件不存在: {p}"]
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as e:
        return [f"档案读取失败: {p} -> {e}"]

    fm_lines, _body = split_markdown(text)
    if not fm_lines:
        issues.append("缺 frontmatter(文件须以 --- 块开头, 机读字段见 runs/_template/product-profile.md)")
    meta = parse_frontmatter(p)

    for key in _REQUIRED_KEYS:
        if not meta.get(key, "").strip():
            issues.append(f"frontmatter 缺必需字段或为空: {key}")

    status = meta.get("status", "")
    if status and status not in PROFILE_STATUSES:
        issues.append(f"status 非法({status})——须为 draft/confirmed/declined 之一")
    sp = meta.get("sources_present", "")
    if sp and sp not in SOURCES_PRESENT_VALUES:
        issues.append(f"sources_present 非法({sp})——须为 yes/partial/no 之一")
    ss = meta.get("sources_status", "")
    if ss and ss not in SOURCES_STATUS_VALUES:
        issues.append(f"sources_status 非法({ss})——须为 requested/provided/partial/declined 之一")

    if status == "confirmed":
        if not meta.get("confirmed_at", "").strip():
            issues.append("status=confirmed 但缺 confirmed_at")
        by = meta.get("confirmed_by", "")
        if not by.strip():
            issues.append("status=confirmed 但缺 confirmed_by")
        else:
            ok, why = validate_nickname(by)
            if not ok:
                issues.append(f"confirmed_by 不是纯昵称({by}): {why}")
        h = meta.get("content_sha256", "")
        if not h:
            issues.append("status=confirmed 但缺 content_sha256(用 product_profile.py confirm 生成)")
        elif h != content_sha256(p):
            issues.append("content_sha256 与正文不匹配——正文在确认后被改动, 须重新 confirm")

    # ①~⑧ 字段结构与来源(静态红队P1)
    facts = profile_field_facts(p)
    missing = [n for n in range(1, 9) if n not in facts]
    if missing:
        issues.append("正文缺字段: " + "、".join(f"{n}" for n in missing) + "——①~⑧ 须全部存在")
    for n in sorted(facts):
        f = facts[n] or {}
        for k in ("content", "source", "confidence"):
            if not (f.get(k) or "").strip():
                issues.append(f"字段{n}缺 {k}——每字段须有 内容/source/confidence 三行")
        src = (f.get("source") or "").strip()
        conf = (f.get("confidence") or "").strip().lower()
        if src and not _source_ok(src):
            issues.append(f"字段{n} source 非法({src})——值域: none/用户/推断/URL:https://完整来源")
        if conf and conf not in CONFIDENCE_VALUES:
            issues.append(f"字段{n} confidence 非法({f.get('confidence')})——须为 low/medium/high")
        content = (f.get("content") or "").strip()
        if (status == "confirmed" and content not in FIELD_PLACEHOLDERS
                and src.lower() in ("", "none", "推断") and _CONCRETE_FACT_RE.search(content)):
            issues.append(f"字段{n} 含具体事实(数字/认证等)但 source={src or 'none'}——"
                          "confirmed 档案的具体事实须有 用户/URL 来源, 推断/无来源不得写数字与认证")

    # sources 状态与字段实际一致(静态红队P1)
    provided, inferred, _unsourced = _fact_stats(facts)
    given = provided + inferred
    if sp:
        exp_sp = "yes" if len(provided) == 8 else ("partial" if given else "no")
        if sp != exp_sp:
            issues.append(f"sources_present={sp} 与字段实际不一致(有来源 {len(provided)}/8, 推断 {len(inferred)})——应为 {exp_sp}")
    if ss:
        if len(provided) == 8:
            exp_ss = "provided"
        elif given:
            exp_ss = "partial"
        else:
            exp_ss = None  # 无任何已填事实: requested(尚未给) 或 declined(明确不给) 均合法
        if exp_ss is not None and ss != exp_ss:
            issues.append(f"sources_status={ss} 与字段实际不一致(有来源 {len(provided)}/8, 推断 {len(inferred)})——应为 {exp_ss}")
        if exp_ss is None and ss not in ("requested", "declined"):
            issues.append(f"sources_status={ss} 与字段实际不一致(无任何已填事实)——应为 requested 或 declined")

    if require_confirmed and status != "confirmed":
        issues.append(f"require_confirmed: status={status or '(空)'} 不是 confirmed")

    low = text.lower()
    for marker in THIRD_PARTY_MARKERS:
        if marker.lower() in low:
            issues.append(f"档案含第三方联系方式清单标记『{marker}』——客户/潜在联系人信息禁止写入本档案")
    issues.extend(detect_third_party_contact(text, label="档案"))
    return issues


def profile_gate(path):
    """写操作前硬闸门(编排器/模板生成器共用): status 须为 confirmed 或 declined。
    返回 (status: str, issues: list, meta: dict, sha256: str)。
    status 为 '' 表示文件不存在/不可用; issues 非空表示不可放行。"""
    p = Path(path)
    if not p.is_file():
        return "", [f"档案文件不存在: {p}"], {}, ""
    meta = parse_frontmatter(p)
    status = meta.get("status", "")
    issues = validate_product_profile(p, require_confirmed=False)
    if not issues and status not in ("confirmed", "declined"):
        issues.append(f"status={status or '(空)'} 不是 confirmed/declined——draft 未拍板, 禁止平台写操作")
    return status, issues, meta, profile_sha256(p)
