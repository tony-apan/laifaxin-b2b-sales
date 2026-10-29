#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★审批凭证模块(审批闸门(工具级)): 写操作工具执行前必须 require_approval 通过, 否则拒绝写入。
approvals.tsv 列(8列, 换机兼容): id / project_id / state / decision / user_quote / memo(参数哈希或备注) / time / status
授权规则(2026-09-04 静态红队P0修复):
  - 只有 decision=confirm 且 status=confirmed 的凭证可授权写操作
  - backfilled(换机恢复的历史审计行)/modified(修改意见)/pending(参数不全的 decision_pending) 一律不可授权
  - record(decision="modify") 强制写 status=modified
参数绑定(防审批与执行参数不一致):
  - 工具端: require_approval(..., expected_hash=stable_params_hash(本次实际参数dict)) —— 哈希由工具按本次实际参数重算, 不信调用者/CLI传入的哈希
  - 铸造端: flow_orchestrator 确认节点(参数齐全时) 或专门审批命令:
      python3 tools/approval.py grant --project <operator_key>/<product_key> --state S10_加联系人 \
          --quote "<用户确认原话>" --params-file <实际参数.json>
    ★S12禁止grant，只能用flow_orchestrator --resume-s12 --confirm 签发（校验更全：S11/档案/合规live/参数绑定）。
    参数JSON须与工具端绑定schema逐字段一致(工具不认路径类字段, 见各工具docstring)
用法(在写工具内):
  import sys; sys.path.insert(0, str(Path(__file__).resolve().parent))
  from approval import require_approval, stable_params_hash
  binding = {"project": args.project, "seq": args.seq, ...}   # 本次实际参数(工具自算, 不信CLI给的hash)
  require_approval(args.approval, args.project, ("S10",), what="加联系人", expected_hash=stable_params_hash(binding))
"""

def _utf8_stdout():
    """Windows 控制台/管道默认 GBK：输出 emoji 会抛 UnicodeEncodeError；显式改 UTF-8。"""
    import sys as _sys
    for _s in (_sys.stdout, _sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
_utf8_stdout()
import hashlib, json, os, re, time
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
os.makedirs(KB / ".local", exist_ok=True)  # 等价 (KB/".local").mkdir(exist_ok=True)
APPROVALS = KB / ".local" / "approvals.tsv"
AUTH_DECISION = "confirm"   # 只有 confirm 决定可授权
AUTH_STATUS = "confirmed"   # 只有 confirmed 状态可授权(backfilled/modified/pending 不可)
VALID_STATUS = ("confirmed", "backfilled")  # 历史读取兼容; backfilled 只作审计不再授权
COLUMNS = ["id","project_id","state","decision","user_quote","memo","time","status"]


BOM = b"\xef\xbb\xbf"


def _read_approvals_text(require_marked=False):
    """读 approvals.tsv。

    带 BOM → UTF-8；无 BOM → 按 UTF-8 严格解码（解不开就是旧 GBK，明确报错，不猜）。
    无 BOM 的中文存在「旧 GBK 字节恰好是合法 UTF-8」的二义性：读出来仅用于显示可以，
    但任何“重写整文件”的动作（demote-migrated / 追加前升级）必须 require_marked=True 拒绝二义性文件，
    避免把错读的结果永久写回磁盘。
    """
    data = APPROVALS.read_bytes()
    if not data:
        return ""
    if data.startswith(BOM):
        try:
            return data[len(BOM):].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"审批账本带 UTF-8 BOM，但正文不是合法 UTF-8：{APPROVALS}。"
                "为避免把审批原话永久写坏，本工具不改写该文件；请先备份，人工确认后修复编码再重跑。"
            ) from exc
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"审批账本不是 UTF-8：{APPROVALS}（很可能是旧版 Windows 按 GBK 写出）。"
            "为避免把审批原话永久写坏，本工具不自动猜编码；请先备份，人工确认后手动转成 UTF-8。"
        ) from exc
    if require_marked and not text.isascii():
        raise ValueError(
            f"审批账本是无 BOM 的中文文件：{APPROVALS}（UTF-8 与旧 GBK 存在二义性，部分 GBK 字节也是合法 UTF-8）。"
            "为避免迁移时把审批原话永久写坏，本操作拒绝自动重写；请先备份，人工确认后手动转成「带 BOM 的 UTF-8」。"
        )
    return text


def _rows(require_marked=False):
    if not APPROVALS.exists():
        return []
    lines = [l.rstrip("\n").split("\t")
             for l in _read_approvals_text(require_marked=require_marked).splitlines() if l.strip()]
    if not lines:
        return []
    header = lines[0]
    # ★ISS-51: 首行若以 ap- 开头 = 无表头(record 曾首次建文件不写表头) → 用标准列名, 不把数据行当 header
    if str(header[0]).lower().startswith("ap-"):
        rows = [dict(zip(COLUMNS + (["quote_encoding"] if len(l) == len(COLUMNS) + 1 else []), l)) for l in lines if len(l) in (len(COLUMNS), len(COLUMNS) + 1)]
    else:
        rows = [dict(zip(header + (["quote_encoding"] if len(l) == len(header) + 1 else []), l)) for l in lines[1:] if len(l) in (len(header), len(header) + 1)]
    for row in rows:
        value = row.get("user_quote", "")
        if row.get("quote_encoding") == "json-v1" and value.startswith("@quote-json-v1:"):
            try:
                decoded = json.loads(value[len("@quote-json-v1:"):])
                if isinstance(decoded, str):
                    row["user_quote"] = decoded
            except (ValueError, TypeError):
                raise ValueError("审批原话编码无效")
    return rows


def stable_params_hash(params):
    """对参数 dict 计算稳定哈希(审批↔执行参数绑定用)。
    canonical JSON(sort_keys+ensure_ascii+紧凑分隔符, default=str) → sha256 前16位, 加 sha256: 前缀便于目视识别。
    同一 dict 任意键序/换机重算结果一致; 工具端永远用本函数按本次实际参数重算, 不信外部传入的哈希。"""
    canonical = json.dumps(params, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


# ---------- 凭证一次性消费账本（三审 S1-5）----------
# 同一份 S12 凭证只允许成功激活一次；停发后再激活必须重新走 --resume-s12 由用户新原话签发。
USED_LEDGER = KB / ".local" / "approvals-used.tsv"


def mark_approval_used(approval_id, project="", state="", seq="", note=""):
    """激活成功后登记该凭证已消费；重复调用幂等（同一 id 只记一次）。"""
    if not approval_id:
        return
    if is_approval_used(approval_id):
        return
    if not USED_LEDGER.exists() or USED_LEDGER.stat().st_size == 0:
        USED_LEDGER.write_text("id\tproject\tstate\tseq\ttime\tnote\n", encoding="utf-8")
    with open(USED_LEDGER, "a", encoding="utf-8") as fh:
        fh.write(f"{approval_id}\t{project}\t{state}\t{seq}\t{time.strftime(chr(37)+chr(89)+chr(45)+chr(37)+chr(109)+chr(45)+chr(37)+chr(100)+chr(32)+chr(37)+chr(72)+chr(58)+chr(37)+chr(77)+chr(58)+chr(37)+chr(83))}\t{note}\n")


def is_approval_used(approval_id):
    """该凭证是否已消费过（用独立账本，不修改原 approvals.tsv 审计行）。"""
    if not approval_id or not USED_LEDGER.exists():
        return False
    for line in USED_LEDGER.read_text(encoding="utf-8").splitlines()[1:]:
        if line.split("\t", 1)[0] == approval_id:
            return True
    return False


def gen_id(project, state, quote, t=None):
    t = t or time.strftime("%Y-%m-%d %H:%M:%S")
    return "ap-" + hashlib.sha256(f"{project}|{state}|{quote}|{t}".encode()).hexdigest()[:12]


def _unique_id(project, state, quote, t):
    """id 唯一化(静态红队P0): 同一秒内同 project/state/quote 的两次铸造(如对错参数各铸一条)不得共享 id,
    否则按 id 找凭证会让错误参数的凭证搭正确参数凭证的便车, 参数绑定失效。"""
    seen = {r.get("id") for r in _rows()}
    aid = gen_id(project, state, quote, t)
    salt = 0
    while aid in seen:
        salt += 1
        aid = gen_id(project, state, quote, f"{t}#{salt}")
    return aid


def _state_matches(actual, expected):
    actual, expected = str(actual or ""), str(expected or "")
    return actual == expected or actual.startswith(expected + "_")


def find_approval(approval_id, project=None, states=None, expected_hash=None):
    """按 id 精确匹配; project 精确匹配; states 前缀匹配(state.startswith);
    expected_hash 非空时 memo 须逐字一致(参数绑定); ★只有 decision=confirm 且 status=confirmed 才返回(可授权)。"""
    for r in _rows():
        if r.get("id") != approval_id:
            continue
        if project and r.get("project_id") != project:
            continue
        if states and not any(_state_matches(r.get("state"), s) for s in states):
            continue
        if expected_hash is not None and (r.get("memo") or "").strip() != expected_hash:
            continue
        if r.get("decision") != AUTH_DECISION or r.get("status") != AUTH_STATUS:
            continue
        return r
    return None


def _deny_reasons(r, project, states, expected_hash):
    reasons = []
    if project and r.get("project_id") != project:
        reasons.append(f"project={r.get('project_id')!r}≠{project!r}")
    if states and not any((r.get("state") or "").startswith(s) for s in states):
        reasons.append(f"state={r.get('state')!r} 不在 {list(states)}")
    if expected_hash is not None and (r.get("memo") or "").strip() != expected_hash:
        reasons.append(f"参数哈希不匹配: memo={str(r.get('memo'))[:27]}… ≠ 本次实际参数重算 {expected_hash}(审批与本次执行参数不一致)")
    if r.get("decision") != AUTH_DECISION:
        reasons.append(f"decision={r.get('decision')!r}(只有 confirm 可授权; modify/decision_pending/gate_ok 不可)")
    if r.get("status") != AUTH_STATUS:
        reasons.append(f"status={r.get('status')!r}(只有 confirmed 可授权; backfilled/modified/pending 不可)")
    return reasons


def require_approval(approval_id, project, states, what="", expected_hash=None):
    """写操作硬闸门: 无有效审批 → 打印原因并 exit(1)。
    expected_hash: 工具按本次实际参数用 stable_params_hash() 重算的哈希; 凭证 memo 须逐字一致, 否则拒绝(参数绑定)。"""
    if not approval_id:
        print(f"❌ 缺审批凭证 --approval <id>（{what}）。写操作必须先经确认节点或专门审批命令(tools/approval.py grant)铸造, 凭证见 .local/approvals.tsv(审批闸门(工具级))。")
        raise SystemExit(1)
    try:
        r = find_approval(approval_id, project, states, expected_hash=expected_hash)
    except ValueError as exc:
        print(f"❌ 审批账本不可用：{exc}")
        raise SystemExit(1) from exc
    if not r:
        print(f"❌ 审批凭证无效/状态不符/参数绑定不匹配: approval={approval_id} project={project} states={list(states)}。拒绝写操作(审批闸门(工具级))。")
        cands = [x for x in _rows() if x.get("id") == approval_id]
        if not cands:
            print("   - 凭证 id 不存在于 .local/approvals.tsv")
        for x in cands[:3]:
            for why in _deny_reasons(x, project, states, expected_hash) or ["状态不符"]:
                print(f"   - {why}")
        if expected_hash is not None:
            print(f"   参数绑定: 本工具按本次实际参数重算哈希 {expected_hash}, 须与凭证 memo 一致。按本次实际参数重新铸造:")
            print(f"   python3 tools/approval.py grant --project {project} --state <节点> --quote \"<用户确认原话>\" --params-file <本次实际参数.json>")
        raise SystemExit(1)
    print(f"  ✅ 审批通过: {r.get('id')} | {r.get('state')} | {r.get('decision','')[:40]} | {r.get('status')}"
          + (f" | 参数哈希绑定 {expected_hash}" if expected_hash else ""))
    return r


def _tsv_cell(value, limit=1000):
    """审批字段固定为单行 TSV 单元格，防用户原话中的换行/制表符破坏换机后的8列解析。"""
    return " ".join(str(value or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").split())[:limit]


def record(project, state, decision, quote, params_hash, status="confirmed"):
    """追加一行审批并返回 id（编排器/专门审批命令铸造时调用）。
    ★decision="modify" 强制 status="modified"(不可授权); 其余非 confirm 的 decision 建议显式传 pending 等不可授权状态。"""
    if decision == "modify":
        status = "modified"  # ★修改记录不可授权
    try:
        _rows()
    except ValueError as exc:
        print(f"❌ 审批账本不可用：{exc}")
        raise SystemExit(1) from exc
    project, state = _tsv_cell(project, 200), _tsv_cell(state, 100)
    decision = _tsv_cell(decision, 100)
    quote = str(quote or "")
    params_hash, status = _tsv_cell(params_hash, 200), _tsv_cell(status, 50)
    t = time.strftime("%Y-%m-%d %H:%M:%S")
    aid = _unique_id(project, state, quote, t)
    encoded_quote = ("@quote-json-v1:" + json.dumps(quote, ensure_ascii=True)
                     if any(c in quote for c in "\t\n\r") or quote.startswith("@quote-json-v1:") else quote)
    marker = "\tjson-v1" if encoded_quote != quote else ""
    line = f"{aid}\t{project}\t{state}\t{decision}\t{encoded_quote}\t{params_hash}\t{t}\t{status}{marker}\n"
    # ★ISS-51: 首次创建文件须写表头（否则首行数据被当 header，闸门全失效）
    if not APPROVALS.exists() or APPROVALS.stat().st_size == 0:
        with open(APPROVALS, "w", encoding="utf-8-sig", newline="\n") as f:
            f.write("\t".join(COLUMNS) + "\n")
    elif not APPROVALS.read_bytes().startswith(BOM):
        # 旧账本若为纯 ASCII 才补 BOM（内容原样保留）；无 BOM 的中文有二义性，保持原样、只追加，
        # 任何整文件重写（demote-migrated）会被 require_marked 拒绝，避免永久写坏。
        if _read_approvals_text().isascii():
            # 读-改-写用临时文件 + 原子替换，避免中途崩溃/并发追加截断整本账
            tmp = APPROVALS.with_suffix(".tsv.bomtmp")
            tmp.write_bytes(BOM + APPROVALS.read_bytes())
            os.replace(tmp, APPROVALS)
    with open(APPROVALS, "a", encoding="utf-8", newline="\n") as f:
        f.write(line)
    return aid


# ---------- 确认原话的否定/等待/条件/修改意图识别（共享判定） ----------
# 放在 approval.py 而非新模块：临时仓库夹具只复制固定文件清单，审批模块必须在任何确认入口可用。
_NEG_PATTERNS = (
    r"不(?:要|用|必|需|能|行|可以|确认|激活|保存|建|开始|继续|执行|发|加|动|急|忙)",
    r"别(?:开始|激活|执行|继续|发|保存|存|建|加|改|动|急|忙|确认|操作|动手)",
    r"(?:先|暂|且|还)(?:别|不|不要|不用|勿|甭)",
    r"(?:先|暂)(?:等|缓)",
    r"尚未|还没|未(?:确认|激活|保存|完成|准备好)|没有确认",
    r"取消|暂停|停止|终止|回滚|撤回|作废|否决|拒绝|不同意",
    r"等等|稍等|等一下|等一会|先等|再看看|再想想|再考虑|考虑一下|下次|回头|再说|商量|犹豫",
    r"别急|别忙|不急|不着急",
    r"(?:大概|可能|也许|或许|估计|差不多|应该|不太确定|不确定|没把握|说不准)",
)
_CONDITIONAL_PATTERNS = (
    r"(?:如果|要是|假如|倘若|万一|除非)",
    r"(?:等|待)[^。，,；;]{0,16}再",
    r"先[^。，,；;]{0,12}再",
    r"的话",
)
_MODIFICATION_PATTERNS = (
    r"改成|改为|改到|改一下|改下|改数量|改人数|改邮箱|改配置|改批次|改标签|改文案",
    r"换成|换为|换个|换一个|替换为|替换成",
    r"调整为|调整成|调到|调成|调为",
    r"修改为|修改成|修正为|更改为|更改成|更新为|更新成",
    r"设置为|设为|设置成",
    r"新增|增加|加到|加一个|加个|多加|少加|减少|删掉|删了|删除|去掉|拿掉|撤回|补充|补上",
    r"换掉|换名|改名|改名单|换公司名|(?:要|需要)(?:改|换|换掉|动|调整|删|加|更新)",
    r"(?:名单|批次|客户|联系人|公司|客群|人群)[^。，,；;]{0,8}(?:重新选|重选|另选|重新挑|重挑|换一批)",
    r"(?:重新选|重选|另选|重新挑|重挑)[^。，,；;]{0,8}(?:名单|批次|客户|联系人|公司|客群|人群)",
    r"(?:要|需要|得)\s*(?:重新选|重选|另选|重新挑|重挑)",
    r"(?:认证|产能|交期|价格|卖点|规格|型号|公司名|官网|联系方式|人数|数量|家数|邮箱|批次|标签|模板|上限|时区|节奏|配置|名单)"
    r"\s*(?:改成|改为|换成|调成|调整为|设置为|设为|改|暂无|没有|去掉|删除|撤回|新增|补充|是|为|到|有|\d+)",
    r"(?:加|减|删|去)\s*(?:\d+|[零一二三四五六七八九十百千万两]+)\s*(?:家|人|个|封|位)",
)
_RESERVATION_PATTERNS = (
    r"(?:^|[，,。；;！!？?]|\s)\s*(?:但|但是|不过|可是|只是|然而)",
    r"(?:确认|确认了|确定|好的|可以|没问题|同意|通过)\s*(?:但|不过|可是|只是|然而)",
)


def _first_pattern(patterns, text):
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return ""


def negative_or_wait(quote):
    """返回 (是否含否定/等待/停止, 命中的原话片段)。"""
    text = " ".join(str(quote or "").split()).strip()
    hit = _first_pattern(_NEG_PATTERNS, text)
    return (bool(hit), hit)


def conditional(quote):
    """返回 (是否条件/等待后再做, 命中的原话片段)。"""
    text = " ".join(str(quote or "").split()).strip()
    hit = _first_pattern(_CONDITIONAL_PATTERNS, text)
    return (bool(hit), hit)


def modification_intent(quote):
    """返回 (是否带参数修改/增删意图, 命中的原话片段)。"""
    text = " ".join(str(quote or "").split()).strip()
    hit = _first_pattern(_MODIFICATION_PATTERNS, text)
    return (bool(hit), hit)


def reservation(quote):
    """汇总"不干净确认"判定，返回 (是否应暂停, 可读原因)。

    顺序：否定/等待 → 条件 → 修改/增删 → 转折保留；只返回第一个命中原因。
    """
    for check, label in (
        (negative_or_wait, "否定/等待/停止"),
        (conditional, "条件/等待后再做"),
        (modification_intent, "参数修改/增删"),
    ):
        hit, text = check(quote)
        if hit:
            return True, f"{label}『{text}』"
    text = " ".join(str(quote or "").split()).strip()
    hit = _first_pattern(_RESERVATION_PATTERNS, text)
    if hit:
        return True, f"保留/转折句『{hit.strip()}』"
    return False, ""




def authorize_quote(quote, state, binding=None):
    """仅匹配完整原话；动态值必须来自调用方已验证的绑定。"""
    if not isinstance(quote, str) or not isinstance(state, str):
        return False
    q = re.sub(r"\s+", " ", quote.strip()).rstrip("。.!！~～").strip()
    if "?" in q or "？" in q:
        return False
    binding = binding if isinstance(binding, dict) else {}
    state = state.upper()
    if state == "PROFILE":
        name = binding.get("product_name")
        return q in ("1", "确认", "确认当前档案", "确认重新启用档案") or (isinstance(name, str) and bool(name.strip()) and q in ("确认，产品是" + name, "确认,产品是" + name))
    if state == "S5":
        count = binding.get("count")
        if type(count) is not int or count <= 0:
            return False
        if q in ("确认", "确认保存", str(count)):
            return True
        m = re.fullmatch(r"确认保存\s*前\s*(\d+)\s*家", q)
        return bool(m and int(m.group(1)) == count)
    if state in ("S2", "S3"):
        return q == "确认"
    if state in ("S7", "S8", "S9", "S10"):
        return q in ("1", "①", "确认", "确认执行")
    if state == "WEBSITE":
        return q in ("1", "确认", "确认应用") and bool(binding.get("patch_id"))
    if state == "S12":
        if q in ("确认激活", "我确认激活", "我考虑清楚了，确认激活", "我考虑清楚了,确认激活"):
            return True
        name = binding.get("sequence_name")
        return isinstance(name, str) and bool(name.strip()) and q == "确认激活 " + name
    return False

# ---------- 专门审批命令(对应工具执行前按实际参数铸造绑定凭证) ----------

def confirm_quote_ok(quote):
    """严格正向确认：否定、疑问、等待/取消语义优先拒绝。

    ★2026-09-17 对抗模拟修复（真缺陷）：原实现用**疑问短语黑名单**
    （是否/能否/可否/要不要/是不是/确认吗/可以吗）——漏掉最常见的**句尾疑问助词**，
    实测「真的要激活吗」被当成授权、真的签发了 S12 凭证。
    现改为规则判定，不再依赖穷举短语：
      ①任何问号 ②剥尾标点后的句尾疑问助词（吗/呢/么）③疑问代词（为什么/怎么/…）
      ④A-not-A 疑问式（是否/能不能/行不行/好不好…）
    """
    q = " ".join(str(quote or "").replace("’", "'").split()).strip()
    if not q or re.search(r"[?？]", q):
        return False
    # 否定/等待/条件/修改/保留句先于正向词：同时含「确认」也不能放行。
    blocked, why = reservation(q)
    if blocked:
        return False
    # ② 句尾疑问助词：先剥掉结尾标点（"要激活吗。" 也应拒绝）
    if q.rstrip("。.!！~～、,，;；").endswith(("吗", "呢", "么")):
        return False
    # ③ 疑问代词（问"为什么/怎么"不是授权）
    if re.search(r"(?:为什么|为何|怎么|难道|凭什么)", q):
        return False
    # ④ A-not-A 疑问式
    if re.search(r"(?:是否|能否|可否|要不要|是不是|该不该|能不能|可不可以|行不行|好不好|要不要)", q):
        return False
    if re.search(r"\b(?:why|how|when|what|who|which|should i|do i|shall i)\b", q, re.I):
        return False
    if re.search(r"(?:^|[，,。；;！？!?\s])(?:否|拒绝|不同意)(?:$|[，,。；;！？!?\s])", q): return False
    # ★2026-10-23 三审第7关 S0：原实现「任何 不/考虑 子串」一律拒绝，导致序列名含「不锈钢」的产品
    #   按 S12 卡原话「确认激活 不锈钢-S04」必被拒死；「我考虑清楚了，确认激活」也被误杀。改为只拦明确否定/拖延短语。
    if re.search(r"(?:不确认|不激活|不保存|不建|不要|不用|先不|暂不|尚未|还没|未确认|等等|稍等|再考虑|考虑一下|再想想|再说|取消|暂停|停止|回滚|别急|别忙|别激活|别发|别存|别建)", q): return False
    if re.search(r"\b(?:no|not|never|won'?t|don'?t|do not|cannot|can'?t|wait|later|pending|cancel|stop|pause)\b", q, re.I): return False
    return bool(re.search(r"确认|确定|同意|通过|可以|好的|没问题|激活|^是$|^好$|^行$|\b(?:yes|ok|okay|confirm(?:ed)?|approve[de]?|activate)\b", q, re.I))


_NUMERIC_CONFIRM_STATES = ("S7", "S9", "S10")


def numeric_confirm_quote(quote, state):
    """★2026-10-26 真机卡点：确认卡话术统一是「回 1」（output-templates/S*-confirm.md），
    但 approval.py 只对 S7 放行纯数字 1，S9/S10 的合法「1」被拒 → 用户按卡回数字反而走不动。
    这里把「纯数字 1/①」限定放行到 S7/S9/S10；S5 由 save_plan 决定：带数量原话或卡面已写清 N 时只回「确认」都行，纯数字 1 仍不算，
    S12 不走本函数（由 flow_orchestrator 校验「确认激活」）。"""
    q = str(quote or "").strip()
    st = str(state or "").upper()
    return q in ("1", "①") and any(st.startswith(s) for s in _NUMERIC_CONFIRM_STATES)


def _load_params(args):
    raw = ""
    if getattr(args, "params_file", ""):
        p = Path(args.params_file)
        if not p.is_file():
            print(f"❌ --params-file 不存在: {p}"); raise SystemExit(2)
        raw = p.read_text(encoding="utf-8")
    elif getattr(args, "params", ""):
        raw = args.params
    else:
        print("❌ 须提供 --params-file <实际参数.json> 或 --params '<内联JSON>'——凭证必须绑定实际参数, 不允许无参铸造"); raise SystemExit(2)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"❌ 参数JSON解析失败: {e}"); raise SystemExit(2)
    if not isinstance(obj, dict):
        print("❌ 参数JSON须为对象(dict)——键结构须与对应工具的绑定schema逐字段一致(见各工具docstring)"); raise SystemExit(2)
    return obj


def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="approval.py", description="审批凭证铸造/查询(专门审批命令): 对应写工具执行前按实际参数铸造绑定凭证; 工具端会按本次实际参数重算哈希比对, 不信本命令之外传入的哈希")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grant", help="铸造一条绑定实际参数的审批凭证")
    g.add_argument("--project", required=True, help="稳定项目键=<operator_key>/<product_key>(与工具 --project 一致)")
    g.add_argument("--state", required=True, help="节点状态前缀, 如 S5_保存参数/S7_模板预览/S9_序列配置/S10_加联系人/S12_激活(工具按前缀匹配)")
    g.add_argument("--quote", required=True, help="用户确认原话(逐字)")
    g.add_argument("--decision", default="confirm", choices=["confirm", "modify"], help="默认 confirm; modify 强制 status=modified(不可授权)")
    g.add_argument("--params-file", default="", help="实际参数JSON文件(与 --params 二选一)")
    g.add_argument("--params", default="", help="内联参数JSON(与 --params-file 二选一)")
    h = sub.add_parser("hash", help="只计算参数稳定哈希(不落账), 供预填/比对")
    h.add_argument("--params-file", default="")
    h.add_argument("--params", default="")
    s = sub.add_parser("show", help="查看凭证行(诊断授权失败原因)")
    s.add_argument("--id", required=True)
    d = sub.add_parser("demote-migrated", help="换机恢复后把全部confirmed降为backfilled(只审计不可授权)")
    d.add_argument("--confirm", required=True, help="必须逐字 MIGRATION-DEMOTE")
    args = ap.parse_args(argv)

    if args.cmd == "demote-migrated":
        if args.confirm != "MIGRATION-DEMOTE":
            print("❌ 须 --confirm MIGRATION-DEMOTE"); raise SystemExit(2)
        rows = _rows(require_marked=True)
        changed = 0
        for row in rows:
            if row.get("status") == "confirmed": row["status"] = "backfilled"; changed += 1
        APPROVALS.parent.mkdir(parents=True, exist_ok=True)
        tmp = APPROVALS.with_suffix(".tsv.tmp")
        # 保持 BOM 标记：否则重写后的中文文件变成“无 BOM 二义性”，下次 demote 会被拒绝
        with open(tmp, "w", encoding="utf-8-sig", newline="\n") as f:
            f.write("\t".join(COLUMNS) + "\n")
            for row in rows:
                quote = str(row.get("user_quote", ""))
                needs_encoding = any(c in quote for c in "\t\n\r") or quote.startswith("@quote-json-v1:")
                cells = [("@quote-json-v1:" + json.dumps(quote, ensure_ascii=True) if needs_encoding else quote) if c == "user_quote" else _tsv_cell(row.get(c, "")) for c in COLUMNS]
                f.write("\t".join(cells) + ("\tjson-v1" if needs_encoding else "") + "\n")
        tmp.replace(APPROVALS)
        print(f"✅ 已将{changed}条旧confirmed凭证降为backfilled；仅历史审计，不可授权")
        return

    if args.cmd == "hash":
        obj = _load_params(args)
        print(stable_params_hash(obj))
        return
    if args.cmd == "show":
        for r in _rows():
            if r.get("id") == args.id:
                print("\t".join(r.get(c, "") for c in COLUMNS))
                return
        print(f"(未找到 {args.id})"); raise SystemExit(1)
    # grant
    if str(args.state).upper().startswith("S12"):
        print("❌ S12 激活凭证禁止通过 approval.py grant 铸造；用 flow_orchestrator --resume-s12 --confirm \"<用户原话>\" 签发（会一并校验 S11/档案/合规live 并绑定参数哈希）")
        raise SystemExit(2)
    obj = _load_params(args)
    state_key = str(args.state).upper().split("_", 1)[0]
    if args.decision == "confirm" and not authorize_quote(args.quote, state_key, {}):
        print("❌ --quote 不是明确正向确认（含否定/犹豫/疑问或缺确认词）——拒绝铸造可授权凭证")
        raise SystemExit(2)
    ph = stable_params_hash(obj)
    status = "modified" if args.decision == "modify" else "confirmed"
    aid = record(args.project, args.state, args.decision, args.quote, ph, status)
    print(f"✅ 凭证已铸造: {aid}")
    print(f"   project={args.project} | state={args.state} | decision={args.decision} | status={status} | 参数哈希={ph}")
    print("   参数JSON(工具端将按本次实际参数重算并逐字比对, 不一致即拒绝):")
    print("   " + json.dumps(obj, ensure_ascii=False, sort_keys=True))
    print(f"   → 工具执行须带: --approval {aid} --project {args.project} (且工具实际参数与本JSON逐字段一致)")
    if status != "confirmed":
        print("   ⚠️ status=modified——本凭证不可授权任何写操作, 仅作修改意见留痕")


def main(argv=None):
    """CLI 入口：账本编码不可确认时给一句白话退出，不甩 traceback（fail-closed）。"""
    try:
        return _main(argv)
    except ValueError as exc:
        print(f"❌ 审批账本不可用：{exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
