#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★S10 加联系人入序列（一条龙缺口#2）：时序守卫(保存finished+标签>0) → contact-add(views:[]铁律) → 核对 add 数
用法:
  python3 contact_add.py --token <T> --org <orgId> --seq <seqId> --tags <联系人标签id,可逗号多个> \
      --task <保存任务id>(★必填:时序铁律) --approval <ap-id> --project <产品> [--dry-run]
铁律: views 恒为 []（传 "all" 会把全库 139万 联系人加进来!）; 时序不满足=拒绝执行
"""
import json, subprocess, sys, time, argparse
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KB / "tools"))
from approval import require_approval

ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True, help="accesstoken 整串(web.laifaxin.com&<orgId>&<hash>)")
ap.add_argument("--org", required=True, help="orgId(=token 第2段)")
ap.add_argument("--seq", required=True, help="序列id")
ap.add_argument("--tags", required=True, help="联系人标签id(逗号分隔)")
ap.add_argument("--task", required=True, help="保存任务id(refine/company-save 返回)——★必填:时序铁律,无任务id=无法确认finished,拒绝执行")
ap.add_argument("--approval", default="", help="★S10 审批凭证id(.local/approvals.tsv)")
ap.add_argument("--project", required=True, help="产品名(审批匹配)")
ap.add_argument("--timeout", type=int, default=900, help="等保存任务最大秒数")
ap.add_argument("--dry-run", action="store_true", help="只打印 payload/时序检查,不写")
args = ap.parse_args()

require_approval(args.approval, args.project, ("S10",), what="加联系人入序列")
tags = [t.strip() for t in args.tags.split(",") if t.strip()]
gots = {}

def api(path, p, t=40):
    cmd = ["curl","-sSL","-m","35","-X","POST",f"https://web.laifaxin.com/api/{path}?uid={args.org}",
           "-H","Content-Type: application/json","-H",f"accesstoken: {args.token}","-d",json.dumps(p)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=t)
    try: return json.loads(r.stdout)
    except:
        print("  ⚠️ 接口无返回——可能是网络不通（这不是配置问题），稍等重试；反复出现看 平台接口间歇空(已知)。")
        return {}

# —— 语言前缀识别表(铁律9 三方配对用; 多字优先, 单字形带"-"防误命中正常词) ——
LANG_MARKERS = [
    (lang, m)
    for lang, ms in {
        "en": ("英语", "英文", "english", "英-"),
        "es": ("西语", "西班牙语", "西班牙文", "spanish", "西-"),
        "pt": ("葡萄牙语", "葡语", "portuguese", "葡-"),
        "de": ("德语", "德文", "german", "德-"),
        "fr": ("法语", "法文", "french", "法-"),
        "ru": ("俄语", "俄文", "russian", "俄-"),
        "ja": ("日语", "日文", "japanese", "日-"),
        "ko": ("韩语", "韩文", "korean", "韩-"),
        "it": ("意大利语", "意语", "italian", "意-"),
        "ar": ("阿拉伯语", "arabic"),
        "tr": ("土耳其语", "turkish"),
        "zh": ("中文", "汉语", "chinese", "中-"),
    }.items()
    for m in ms
]
def detect_lang(text):
    """尽力而为: 从名称中识别语言前缀(如 英语-…/西语-…), 识别不出返回 None(legacy 无前缀→不阻断)。"""
    t = (text or "").lower()
    for lang, marker in sorted(LANG_MARKERS, key=lambda x: -len(x[1])):
        if marker.lower() in t:
            return lang
    return None

def find_seq():
    """翻页查 --seq 对应序列(sequences/sequence-list,与 build_sequence 同口径)。
    返回 (seq_item|None, authoritative|None): authoritative=None=接口取不到(平台接口间歇空,已知问题), True=列表权威可判定, False=翻页中断列表不全不作权威。"""
    page = 1
    while page <= 5:
        d = api("sequences/sequence-list", {"current": page, "pageSize": 100, "filter": {}, "sort": {}})
        data = d.get("data")
        lst = data if isinstance(data, list) else (data.get("list") if isinstance(data, dict) else None)
        if not isinstance(lst, list):
            return None, (None if page == 1 else False)
        for it in lst:
            if isinstance(it, dict) and str(it.get("id") or it.get("_id") or "") == args.seq:
                return it, True   # 命中即权威,不需翻完
        if len(lst) < 100:
            break
        page += 1
    return None, True

# 0a) 本地只读守卫①: --seq 序列存在性(★接口间歇空是已知问题 平台接口间歇空(已知) → 取不到只警告不阻断,不打断流程)
seq_item, seq_authoritative = None, None
for _attempt in range(3):  # 平台接口间歇空(已知): 接口偶发空,重试3次再放弃
    seq_item, seq_authoritative = find_seq()
    if seq_authoritative is not None:
        break
if seq_authoritative is None:
    print("  ⚠️ 序列存在性未能确认(sequences/sequence-list 无返回,平台接口间歇空——已知问题)——不阻断,建议 sequence-details 复核")
elif seq_item is None:
    print(f"❌ 序列不存在/不可见: --seq {args.seq}(sequences/sequence-list 未命中)——禁止 contact-add")
    sys.exit(1)
else:
    print(f"✅ 序列存在: {seq_item.get('name')} (status={seq_item.get('status','?')})")

# 0b) 本地只读守卫②: 语言三方配对(铁律9)——--tags 标签名 vs 序列名语言; ★解析失败不阻断(尽力而为:任一取不到/识别不出语言即跳过)
tag_names = {}
d = api("contacts/tags-list", {"type": "contacts"})
data = d.get("data")
tl = data if isinstance(data, list) else (data.get("list") if isinstance(data, dict) else [])
if isinstance(tl, list):
    for t in tl:
        if isinstance(t, dict) and (t.get("id") or t.get("_id")):
            tag_names[str(t.get("id") or t.get("_id"))] = t.get("name") or ""
if seq_item is None:
    print("  ⚠️ 序列名未解析(序列存在性未能确认,平台接口间歇空(已知))——语言三方配对跳过(★尽力而为,不阻断)")
elif not tag_names:
    print("  ⚠️ 标签名列表未取到(tags-list 无返回,平台接口间歇空(已知))——语言三方配对跳过(★尽力而为,不阻断)")
else:
    seq_lang = detect_lang(seq_item.get("name") or "")
    unresolved = [tg for tg in tags if tg not in tag_names]
    if unresolved:
        print(f"  ⚠️ 标签名未解析(可能新建/其他类型标签,★尽力而为不阻断): {unresolved}")
    bad = []
    for tg in tags:
        nm = tag_names.get(tg)
        tl_ = detect_lang(nm) if nm else None
        if tl_ and seq_lang and tl_ != seq_lang:
            bad.append((tg, nm, tl_))
    if bad:
        det = ", ".join(f"{tg}({nm})={l}" for tg, nm, l in bad)
        print(f"❌ 语言三方配对失败(铁律9): 序列「{seq_item.get('name')}」语言={seq_lang}, 标签 {det} 语言不同——西语客群禁收英语信,禁止 contact-add")
        sys.exit(1)
    pairs = ", ".join(f"{tg}({tag_names.get(tg,'?')}→{detect_lang(tag_names.get(tg)) or '未识别'})" for tg in tags)
    print(f"✅ 语言配对(铁律9): 序列「{seq_item.get('name')}」语言={seq_lang or '未识别(legacy 无前缀,按序列实际市场判定)'} | 标签 {pairs}")

# 1) 时序守卫①: 保存任务 finished
if args.task:
    start = time.time(); status = ""
    while time.time() - start < args.timeout:
        d = api("operation/backend-task-status", {"type":"cluesSave","id":args.task}).get("data",{})
        status = d.get("status","")
        if status == "finished":
            print(f"✅ 保存任务 finished: contactSaveCount={d.get('contactSaveCount')}"); break
        print(f"⏳ 等保存任务... status:{status} fin:{d.get('finished')}/{d.get('total')}", flush=True)
        time.sleep(10)
    else:
        print(f"❌ 超时({args.timeout}s)仍 {status}——禁止 contact-add"); sys.exit(1)

# 2) 时序守卫②: 每个标签联系人>0
for tg in tags:
    got = None
    for i in range(6):
        d = api("contacts/contacts/show", {"current":1,"pageSize":10,"filters":[{"property":"tags","operator":"include","value":tg,"values":[tg],"valueType":"select"}],"sort":{}})
        data = d.get("data")
        try:
            n = int(data.get("total")) if isinstance(data, dict) else int(data)
        except (TypeError, ValueError, AttributeError):
            n = None  # 形状异常(接口偶发 平台接口间歇空(已知))——重试,不裸崩(terra 2-④)
        if n and n > 0: got = n; break
        time.sleep(8)
    if not got:
        print(f"❌ 标签 {tg} 联系人为空/无法确认（接口偶发空 平台接口间歇空(已知): 等5-10分钟重跑即可）——禁止 contact-add"); sys.exit(1)
    print(f"✅ 标签 {tg} 联系人={got}")
    gots[tg] = got

payload = {"seqId": args.seq, "tags": tags, "views": []}  # ★views:[] 铁律
if args.dry_run:
    print(f"[dry-run] 将执行 sequences/contact-add payload={json.dumps(payload, ensure_ascii=False)}（views 恒为空数组）"); sys.exit(0)

# 3) contact-add
r = api("sequences/contact-add", payload, t=120)
data = r.get("data", {}) if isinstance(r.get("data"), dict) else {}
add = data.get("add")
if r.get("success"):
    print(f"✅ contact-add 成功: add={add} (标签人数合计={sum(gots.values())})")
    if add is None: print("   ⚠️ 返回无 add 数——用 sequence-details 核对 active 数")
    elif sum(gots.values()) and add > sum(gots.values()):
        print(f"   ❌ add={add} 明显超过标签人数合计 {sum(gots.values())}——异常!立即用 sequence-details 核对,必要时暂停序列")
else:
    print(f"❌ contact-add 失败: {str(r)[:150]}"); sys.exit(1)
