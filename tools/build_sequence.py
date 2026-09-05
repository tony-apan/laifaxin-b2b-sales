#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★S9 建序列（一条龙缺口#1）：resolve 时区 → sequence-create → sequence-save(规则) → 12步 step-create
多租户铁律：schedule_id 与 notSentTags id **各账号不同**——一律运行时按 --tz / 标签解析，禁止硬编码。
★tmap 溯源校验(静态红队P1, 全部在审批与任何平台写之前): <tmap>.meta.json 须含
  tmap_sha256(=tmap 文件内容hash, 防手改)/project_key(=--project)/org_sha256(=sha256(--org), 防跨账号复用)/
  profile_path_rel+profile_sha256+profile_status(=当前档案, 防跨档案建序列); 缺字段=旧版产物, 须重新生成模板。
用法:
  python3 build_sequence.py --token <T> --org <orgId> --name "产品-英语-12轮10封-多轮开发" \
      --tmap runs/<operator_key>/<product_key>/tmap.json --profile runs/<operator_key>/<product_key>/product-profile.md --from-name <纯昵称> --tz "America/New_York" \
      --approval <ap-id> --project <operator_key>/<product_key> [--dry-run]
默认规则(用户拍板): max_emails_per_day=30000 / domain_emails_per_day=5 / notSentTags=按名解析 询盘+不发
步长: step1=minute/30, step2=day/5, step3=day/15, step4-12=day/30；完成后跑 verify_sequence.py 终检
"""
import json, subprocess, sys, argparse, re, hashlib
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KB / "tools"))
from approval import require_approval, stable_params_hash
from profile_utils import ensure_same_project_paths, profile_gate, validate_nickname
from project_lock import acquire_project_lock
from update_run_state import require_state, update_frontmatter

ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True, help="accesstoken 整串(web.laifaxin.com&<orgId>&<hash>)")
ap.add_argument("--org", required=True, help="orgId(=token 第2段)")
ap.add_argument("--name", required=True, help="序列名,如 产品-英语-12轮10封-多轮开发")
ap.add_argument("--tmap", required=True, help="gen_templates --out 产出的 name→id 映射 json(120个,有序);同目录须有 <tmap>.meta.json")
ap.add_argument("--profile", required=True, help="当前产品档案路径；须与 tmap.meta 的 profile_sha256/status 一致")
ap.add_argument("--from-name", required=True, help="发信昵称=纯个人昵称；邮件签名/发件人不得含公司/职位/网址/邮箱")
ap.add_argument("--tz", default="America/New_York", help="目标市场时区(默认纽约;运行时 schedule-list 解析,勿硬编码id)")
ap.add_argument("--max-per-day", type=int, default=30000, help="单日上限(默认30000=用户拍板)")
ap.add_argument("--per-domain", type=int, default=5, help="单家上限(默认5)")
ap.add_argument("--record", default="", help="项目operation-record；12步全部完成后推进S9,next=S10")
ap.add_argument("--approval", default="", help="★绑定profile+tmap+序列规则的S9审批凭证id")
ap.add_argument("--project", required=True, help="稳定项目键=<operator_key>/<product_key>；须与profile一致")
ap.add_argument("--dry-run", action="store_true", help="只打印将执行的 payload,不写")
args = ap.parse_args()
if not args.dry_run and not args.record:
    print("❌ 正式建序列必须带 --record <operation-record.md>，否则换机状态无法推进"); sys.exit(2)
if not args.dry_run:
    try: require_state(args.record, ("S8", "S9")); acquire_project_lock(args.record, "build_sequence")
    except (ValueError, RuntimeError) as exc: print(f"❌ {exc}"); sys.exit(4)

nick_ok, nick_reason = validate_nickname(args.from_name)
if not nick_ok:
    print(f"❌ --from-name 不是纯个人昵称: {nick_reason}"); sys.exit(2)
profile_path = Path(args.profile)
if not profile_path.is_absolute(): profile_path = KB / profile_path
if not args.dry_run and not ensure_same_project_paths(args.record, profile_path):
    print("❌ --record 与 --profile 不在同一项目目录"); sys.exit(4)
profile_status, profile_issues, profile_meta, profile_sha = profile_gate(profile_path)
expected_project = f"{profile_meta.get('operator_key', '').strip()}/{profile_meta.get('product_key', '').strip()}"
if not profile_issues and args.project != expected_project:
    profile_issues.append(f"--project={args.project!r} 与档案项目键 {expected_project!r} 不一致")
if profile_issues:
    for issue in profile_issues: print(f"❌ 产品档案闸门: {issue}")
    sys.exit(4)
meta_path = Path(args.tmap + ".meta.json")
if not meta_path.is_file():
    print(f"❌ 缺模板溯源元数据: {meta_path}——须用新版 gen_templates.py --out 生成"); sys.exit(1)
try:
    tmeta = json.loads(meta_path.read_text(encoding="utf-8"))
except Exception as e:
    print(f"❌ 模板溯源元数据无效: {e}"); sys.exit(1)

# ★tmap 溯源校验(静态红队P1): tmap 内容 hash / project_key / org 哈希 / 档案路径·hash·状态
# 全部在审批(require_approval)与任何平台写之前——任何一项失配即拒, 不允许手改 tmap 或跨项目/账号/档案复用
def _meta_fail(msg):
    print(f"❌ {msg}——tmap/meta 由 gen_templates.py --out 一体生成, 勿手改; 有变动须重新生成模板后再建序列")
    sys.exit(1)

for _k in ("tmap_sha256", "project_key", "org_sha256", "profile_path_rel", "profile_sha256", "profile_status"):
    if not str(tmeta.get(_k) or "").strip():
        _meta_fail(f"tmap meta 缺字段 {_k}(旧版 gen_templates 产物或不完整)")
if not Path(args.tmap).is_file():
    print(f"❌ tmap 文件不存在: {args.tmap}")
    print("   先跑 gen_templates.py --out <路径> 生成 120 模板映射，再回来建序列。")
    sys.exit(1)
if hashlib.sha256(Path(args.tmap).read_bytes()).hexdigest() != tmeta.get("tmap_sha256"):
    _meta_fail("tmap 内容 hash 与 meta.tmap_sha256 不一致(文件被手改或损坏)")
if tmeta.get("project_key") != args.project:
    _meta_fail(f"tmap meta.project_key={tmeta.get('project_key')!r} 与 --project={args.project!r} 不一致——禁止跨项目复用模板映射")
_org_sha = hashlib.sha256(str(args.org).encode("utf-8")).hexdigest()
if tmeta.get("org_sha256") != _org_sha:
    _meta_fail("tmap meta.org_sha256 与 --org 不一致——禁止跨账号/租户复用模板映射")
try:
    _prof_rel = str(profile_path.resolve().relative_to(KB.resolve()))
except ValueError:
    _prof_rel = str(profile_path)
if tmeta.get("profile_path_rel") != _prof_rel:
    _meta_fail(f"tmap meta.profile_path_rel={tmeta.get('profile_path_rel')!r} 与当前档案 {_prof_rel!r} 不一致——禁止跨档案建序列")
if tmeta.get("profile_sha256") != profile_sha or tmeta.get("profile_status") != profile_status:
    print("❌ tmap 对应的产品档案版本/hash 已变化——重新生成模板计划与模板，禁止跨档案建序列"); sys.exit(1)

# ★N1/N5: tmap 先校验(最常见错误最早暴露,且在审批前; 存在性已在上面 meta 校验中确认) → 再审批
try:
    mapping = json.load(open(args.tmap))
except Exception as e:
    print(f"❌ tmap 不是合法 JSON（{e}）——用 gen_templates.py --out 重新生成，勿手改。"); sys.exit(1)
S9_RULES_BINDING = {"steps": 12, "waits": "step1=30分,step2=5天,step3=15天,step4-12=30天",
                    "tz": args.tz, "daily_limit": f"{args.max_per_day}/{args.per_domain}", "not_sent_tags": "询盘/不发"}
binding = {"project": args.project, "org_sha256": _org_sha, "name": args.name, "from_name": args.from_name,
           "profile": {"sha256": profile_sha, "status": profile_status, "version": profile_meta.get("profile_version", "")},
           "tmap": {"sha256": tmeta.get("tmap_sha256")}, "rules": S9_RULES_BINDING}
require_approval(args.approval, args.project, ("S9",), what="建序列", expected_hash=stable_params_hash(binding))

def api(path, p, t=60, exit_on_fail=True):
    cmd = ["curl","-sSL","-m","55","-X","POST",f"https://web.laifaxin.com/api/{path}?uid={args.org}",
           "-H","Content-Type: application/json","-H",f"accesstoken: {args.token}","-d",json.dumps(p)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=t)
    try:
        d = json.loads(r.stdout)
        if d.get("success") is False:
            msg = d.get("message") or ""
            hint = "（token 失效——按教程重取: https://www.laifa.xin/share/ai/laifaxin-ai-account-connection）" if "token" in str(msg) else "（检查权限/参数）"
            if exit_on_fail:
                print("❌ 服务端拒绝: {}{}".format(msg, hint)); sys.exit(1)
            d["_error"] = msg
        return d
    except SystemExit: raise
    except:
        if exit_on_fail:
            print("  ⚠️ 接口无返回——可能是网络不通（这不是配置问题，不用改参数），稍等重试；反复出现再看 平台接口间歇空(已知)。")
        return {}

# 1) tmap 校验（120 个 24hex + 唯一 + 按 name 轮/变体网格重构序——防手工重排错组, terra 1-④）
all_ids = list(mapping.values())
bad = [i for i in all_ids if not re.fullmatch(r"[0-9a-f]{24}", str(i))]
if len(all_ids) != 120 or bad or len(set(all_ids)) != 120:
    print(f"❌ tmap 异常: 数量={len(all_ids)}(应120) 坏id={bad[:3]} 重复={len(all_ids)-len(set(all_ids))}——先跑 gen_templates.py 重新生成"); sys.exit(1)
# 尝试按 name 的 (轮号, 变体号) 网格排序; 解析不出该模式才回退字典序并警告
grid = {}
for name, tid in mapping.items():
    m2 = re.search(r'R(\d{2}).*V(\d{2})', name)
    if m2: grid[(int(m2.group(1)), int(m2.group(2)))] = tid
if len(grid) == 120 and sorted(grid) == [(r, v) for r in range(1, 13) for v in range(1, 11)]:
    ordered = [grid[(r, v)] for r in range(1, 13) for v in range(1, 11)]
    print("✅ tmap 网格校验通过(12轮×10变体,按轮序)")
    groups = [ordered[i*10:(i+1)*10] for i in range(12)]
else:
    print("⚠️ tmap name 不含 R轮/V变体 模式，按文件字典序分组（手工重排过=有错组风险，建议用 gen_templates 原始产物）")
    groups = [all_ids[i*10:(i+1)*10] for i in range(12)]

# 2) 运行时解析 schedule_id（各账号不同）
d = api("settings/sequence/schedule-list", {"current":1,"pageSize":100})
lst = d.get("data", {})
lst = lst if isinstance(lst, list) else lst.get("list", [])
hits = [s for s in lst if s.get("time_zone") == args.tz]
if not hits:
    print(f"❌ 时区 {args.tz} 无模板——用 resolve_schedule.py --list 看全部,或创建自定义 schedule"); sys.exit(1)
hits.sort(key=lambda x: (not x.get("isDefault"),))
sched_id = hits[0].get("id") or hits[0].get("_id")
if not re.fullmatch(r"[0-9a-f]{24}", str(sched_id)):
    print(f"❌ schedule id 形状异常: {sched_id}"); sys.exit(1)
print(f"✅ schedule 解析: {hits[0].get('name')} | {args.tz} | {sched_id}")

# 3) 运行时解析 notSentTags（按名称 询盘/不发——各账号 id 不同）
d = api("contacts/tags-list", {"type":"contacts"})
tl = d.get("data", {})
tl = tl if isinstance(tl, list) else tl.get("list", [])
def tag_by_name(nm):
    for t in tl:
        if t.get("name") == nm: return t.get("id") or t.get("_id")
    return None
t_inq, t_stop = tag_by_name("询盘"), tag_by_name("不发")
if not (t_inq and t_stop):
    miss = [n for n, v in (("询盘",t_inq),("不发",t_stop)) if not v]
    print(f"❌ 未找到 notSent 标签: {miss}——先在系统建这两个联系人标签(名字须完全一致),或本工具加参数扩展"); sys.exit(1)
print(f"✅ notSentTags 解析: 询盘={t_inq} 不发={t_stop}")

rules = {"finishReply": False, "notSentInvalid": True, "notSentBlack": True, "aiGuard": True,
         "max_emails_selected": True, "max_emails_per_day": args.max_per_day,
         "domain_emails_selected": True, "domain_emails_per_day": args.per_domain,
         # ★公司触发器=什么都不做（2026-09-03 用户拍板）：同公司其他联系人继续正常触达，回复处理由询盘标签+人工接管
         "otherReplaySelected": True, "otherReplayValue": "nothing",
         "notSentTags": [t_inq, t_stop]}
others = {"trackSelected": True, "fromNameSelected": True, "fromNameValue": args.from_name}

if args.dry_run:
    print("\n[dry-run] 将执行: sequence-create {{name:{}, channel:system}} → sequence-save(rules:30000/{}/notSent[询盘,不发], fromName:{}) → 12×step-create(30分/5/15/30天,每步10模板)".format(args.name, args.max_per_day, args.per_domain, args.from_name))
    sys.exit(0)

# 4) 幂等预检: 同名序列已存在则拒绝（terra 1-①）
exist = api("sequences/sequence-list", {"current":1,"pageSize":100,"filter":{},"sort":{}})
elst = exist.get("data", {})
elst = elst if isinstance(elst, list) else elst.get("list", [])
if any((it.get("name") == args.name) for it in elst if isinstance(it, dict)):
    print(f"❌ 已存在同名序列「{args.name}」——先删旧的（界面或 sequence-delete 接口 id）再重跑，避免重复建")
    sys.exit(1)

r = api("sequences/sequence-create", {"name": args.name, "channel": "system"})
data = r.get("data", {}) or {}
seq_id = data.get("id") or data.get("_id") or (data if isinstance(data, str) else "")
if not re.fullmatch(r"[0-9a-f]{24}", str(seq_id)):
    print(f"❌ sequence-create 失败: {str(r)[:120]}"); sys.exit(1)
print(f"✅ 序列已建: {seq_id}")
r = api("sequences/sequence-save", {"id": seq_id, "name": args.name, "schedule_id": sched_id, "others": others, "rules": rules}, exit_on_fail=False)
if not r.get("success"):
    print("❌ 规则保存失败: " + str(r.get("_error") or r.get("message") or str(r)[:90]))
    print(f"  ⚠️ 半成品序列 {seq_id}（已建但规则未保存）——勿激活；到界面删除它后重跑")
    sys.exit(1)

# ★回读校验公司触发器生效（2026-09-03 拍板=什么都不做；防静默失效）
chk = api("sequences/sequence-details", {"id": seq_id})
rl = (chk.get("data") or {}).get("rules") or {}
if not rl:
    print(f"❌ 规则回读为空——半成品序列 {seq_id} 勿激活；删除后重跑")
    sys.exit(1)
orv = rl.get("otherReplayValue")
if orv is not None and str(orv).lower() not in ("nothing", "none", "0"):
    print(f"❌ 回读发现公司触发器未生效(otherReplayValue={orv})——半成品序列 {seq_id} 勿激活；删除后重跑")
    sys.exit(1)
print("✅ 回读确认: 公司触发器=什么都不做 已生效")
print(f"✅ 规则已存: {args.tz}时区/{args.max_per_day}/{args.per_domain}/询盘不发不送/发信人={args.from_name}")

# 5) 12 步
wait_cfg = {1:("minute",30), 2:("day",5), 3:("day",15)}
for step in range(1, 13):
    wm, wt = wait_cfg.get(step, ("day",30))
    r = api("sequences/step-create", {"seqId": seq_id, "step": step, "template_ids": groups[step-1],
                                      "wait_mode": wm, "wait_time": wt, "senders": []}, exit_on_fail=False)
    ok = r.get("success")
    print(f"  step{step} ({wm}/{wt}): {'✅' if ok else '❌ '+str(r)[:80]}")
    if not ok:
        print(f"  ⚠️ 半成品序列 {seq_id}（{step-1}/12 步）——勿激活；到界面删除它后从本工具重跑（重跑会因同名被拦，先删）")
        sys.exit(1)

if args.record:
    update_frontmatter(args.record, {"status": "S9", "next_state": "S10", "updated": __import__('time').strftime("%Y-%m-%d"),
                                      "sequence_id": f'"{seq_id}"',
                                      "profile_version": f'"{profile_meta.get("profile_version", "")}"',
                                      "profile_sha256": f'"{profile_sha}"'}, expected_states=("S8", "S9"))
    print(f"✅ 运行状态已推进: {args.record} → S9 (next=S10)")

print(f"""
🎉 序列完成: {seq_id}
下一步终检: python3 tools/verify_sequence.py --token <T> --org {args.org} --seq {seq_id}
然后 S10:   python3 tools/contact_add.py --token <T> --org {args.org} --seq {seq_id} --tags <联系人标签id> --task <保存任务id> --record {args.record or '<operation-record.md>'} --approval <S10凭证> --project {args.project}
（测试不激活——S12 仅用户明确"确认激活"）""")
