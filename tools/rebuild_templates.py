#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚠️⚠️ 原型(半自动)——皮筏艇2026-08-30实操用此脚本失败两次后改为手工分步(见 L-43 / 模板差异实测·模板id校验)。已知坑:
  - 模板名称唯一: 旧模板未删时同名 template-add 失败("模板名称已存在")
  - 被序列引用模板不可删("模板使用中,请在序列中删除"); 序列"至少保留一个步骤"; 步骤"邮件模板不能为空"
  - step-save/step-create 不校验 template_ids(垃圾字符串也 success)→step-list 500
  ✅ 实操成功的顺序(2026-08-30): ①收集旧模板id+步骤wait配置 → ②step-delete 删到剩1步(记录最后1步id) → ③gen_templates 用新后缀(如-RT2)避免重名 → ④删全部旧模板 → ⑤step-save 最后1步指向新id → ⑥step-create 其余步骤 → ⑦删残留旧模板 → ⑧verify_sequence+check_template_diff
用法:
  python3 rebuild_templates.py ... --profile runs/<operator_key>/<product_key>/product-profile.md --plan <plan.json> \
      --record runs/<operator_key>/<product_key>/operation-record.md --gen-approval <建模板凭证> --approval <重建序列凭证> --project <operator_key>/<product_key>
前置(★静态红队P0修复):
  - 序列回读 status 必须 inactive, 回读失败/未命中/非 inactive → 直接退出(active 序列改步骤=立即真发)
  - 审批凭证须绑定本次实际参数(哈希由本工具按实际参数重算, 不信CLI传入), schema:
      {"project":"<operator_key>/<product_key>","seq":"<序列id>",
       "profile":{"sha256":"<档案文件sha256>","status":"confirmed|declined","version":"<profile_version>"},
       "plan":{"sha256":"<plan文件sha256>"},"suffix":"<-RT等新后缀>"}
    铸造: python3 tools/approval.py grant --project <项目键> --state S7_模板重建 --quote "<用户确认原话>" --params-file <实际参数.json>
  - 每个 step-save 失败立即中止, 绝不删除旧模板; 全部12步回读验证均指向新模板ID后才删旧模板
本脚本只重建模板与步骤, 不 contact-add 不激活。
"""
import json, subprocess, time, sys, argparse, re, hashlib, shutil
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KB / "tools"))
from approval import require_approval, stable_params_hash
from profile_utils import ensure_same_project_paths, profile_gate
from project_lock import acquire_project_lock
from update_run_state import read_status, update_frontmatter

ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True); ap.add_argument("--org", required=True)
ap.add_argument("--product", required=True); ap.add_argument("--prefix", required=True)
ap.add_argument("--suffix", default="-RT"); ap.add_argument("--seq", required=True)
ap.add_argument("--name", required=True, help="签名昵称(纯个人昵称)"); ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--profile", required=True, help="已确认/declined 产品档案路径")
ap.add_argument("--plan", required=True, help="绑定当前 profile hash 的模板计划 JSON")
ap.add_argument("--gen-approval", required=True, help="S7/S8建新模板凭证(绑定project+profile+plan)")
ap.add_argument("--approval", required=True, help="模板重建凭证(绑定seq+profile+plan+suffix)")
ap.add_argument("--record", required=True, help="项目operation-record；gen_templates创建成功后推进S8")
ap.add_argument("--project", required=True, help="稳定项目键=<operator_key>/<product_key>，与profile一致")
ap.add_argument("--out", default="", help="name→id 映射落盘路径(默认 db/tmap-<产品>.json; 建议 runs/<运营方>/<产品>/tmap.json)")
args = ap.parse_args()
if not args.prefix.strip() or not args.suffix.strip():
    print("❌ --prefix/--suffix 不能为空（空prefix会匹配全部模板，禁止）"); sys.exit(2)

def api(path, p, t=60):
    cmd = ["curl","-sSL","-X","POST",f"https://web.laifaxin.com/api/{path}?uid={args.org}",
           "-H","Content-Type: application/json","-H",f"accesstoken: {args.token}","-d",json.dumps(p)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=t)
    try: return json.loads(r.stdout)
    except: return {"success": False}

def sha_file(path):
    """文件整体 sha256(64hex); 不存在/读不了返回空串。"""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except Exception:
        return ""

def collect_old():
    ids = []
    for pg in range(1, 30):
        d = api("mailbox/templates-list", {"current":pg,"pageSize":20,"filter":{},"sort":{}})
        lst = d.get("data", {}).get("list", [])
        if not lst: break
        for t in lst:
            if t.get("folder"): continue
            if (t.get("name") or "").startswith(args.prefix):
                ids.append((t.get("name"), t.get("_id")))
    return ids

def find_seq():
    """翻页查 --seq 对应序列(sequence-list, 与 build_sequence 同口径)。
    返回 (seq_item|None, authoritative|None): None=接口取不到(重试后仍失败), True=列表权威可判定, False=翻页中断列表不全。"""
    page = 1
    while page <= 5:
        d = api("sequences/sequence-list", {"current": page, "pageSize": 100, "filter": {}, "sort": {}})
        data = d.get("data")
        lst = data if isinstance(data, list) else (data.get("list") if isinstance(data, dict) else None)
        if not isinstance(lst, list):
            return None, (None if page == 1 else False)
        for it in lst:
            if isinstance(it, dict) and str(it.get("id") or it.get("_id") or "") == args.seq:
                return it, True
        if len(lst) < 100:
            break
        page += 1
    return None, True

def readback_seq_inactive(enforce=True):
    """★前置回读: 序列必须存在且 status=inactive。回读失败/未命中/非inactive → (enforce时)退出。
    返回 (ok, seq_item|None)。"""
    item, auth = None, None
    for _attempt in range(3):  # 平台接口间歇空(已知): 重试3次
        item, auth = find_seq()
        if auth is not None:
            break
    if auth is None or auth is False:
        print("❌ 序列回读失败(sequences/sequence-list 多次无返回/翻页中断,平台接口间歇空——已知问题)——fail-closed, 拒绝重建")
        if enforce: sys.exit(1)
        return False, None
    if item is None:
        print(f"❌ 序列不存在/不可见: --seq {args.seq}——拒绝重建")
        if enforce: sys.exit(1)
        return False, None
    status = str(item.get("status") or "").strip().lower()
    if item.get("active") is True or str(item.get("active")) == "1": status = "active"
    if status != "inactive":
        print(f"❌ 前置回读: 序列 {item.get('name')} status={item.get('status')!r}≠inactive——活动/未知状态序列改步骤=立即真发, 拒绝重建(红队P0)")
        if enforce: sys.exit(1)
        return False, item
    print(f"✅ 前置回读: 序列 {item.get('name')} (status=inactive)")
    return True, item

# ---------- 前置校验: 档案闸门 + plan 存在 + 审批参数绑定 ----------
PROFILE_PATH = Path(args.profile)
if not PROFILE_PATH.is_absolute():
    PROFILE_PATH = KB / PROFILE_PATH
PROFILE_STATUS, PROFILE_ISSUES, PROFILE_META, PROFILE_SHA = profile_gate(PROFILE_PATH)
if not ensure_same_project_paths(args.record, PROFILE_PATH):
    PROFILE_ISSUES.append("--record 与 --profile 不在同一项目目录")
PREVIOUS_RUN_STATE = read_status(args.record) if Path(args.record).is_file() else ""
if PREVIOUS_RUN_STATE not in ("S9", "S10", "S11"):
    PROFILE_ISSUES.append(f"operation-record 当前={PREVIOUS_RUN_STATE or '(缺)'}；模板重建只允许已建序列阶段S9/S10/S11")
EXPECTED_PROJECT = f"{PROFILE_META.get('operator_key', '').strip()}/{PROFILE_META.get('product_key', '').strip()}"
if not PROFILE_ISSUES and args.project != EXPECTED_PROJECT:
    PROFILE_ISSUES.append(f"--project={args.project!r} 与档案稳定项目键 {EXPECTED_PROJECT!r} 不一致——拒绝跨运营方/产品复用审批")
if PROFILE_ISSUES:
    print(f"❌ 产品档案闸门未过: {PROFILE_PATH}")
    for _i in PROFILE_ISSUES:
        print(f"   - {_i}")
    sys.exit(4)
PLAN_SHA = sha_file(args.plan)
if not PLAN_SHA:
    print(f"❌ --plan 文件不存在/不可读: {args.plan}——审批哈希须绑定实际plan, 拒绝重建")
    sys.exit(2)
OUT_PATH = Path(args.out) if args.out else PROFILE_PATH.parent / "tmap.json"
if not OUT_PATH.is_absolute(): OUT_PATH = KB / OUT_PATH
binding = {
    "project": args.project, "org_sha256": hashlib.sha256(str(args.org).encode()).hexdigest(),
    "seq": args.seq, "prefix": args.prefix, "suffix": args.suffix, "name": args.name,
    "out": str(OUT_PATH.resolve()),
    "profile": {"sha256": PROFILE_SHA, "status": PROFILE_STATUS, "version": PROFILE_META.get("profile_version", "")},
    "plan": {"sha256": PLAN_SHA},
    "suffix": args.suffix,
}

def mark_rebuild_error(message):
    recovery_target = "S10" if PREVIOUS_RUN_STATE == "S11" else PREVIOUS_RUN_STATE
    update_frontmatter(args.record, {"status": "ERROR_BLOCKED", "next_state": recovery_target}, expected_states=(PREVIOUS_RUN_STATE,))
    print("❌ " + message + "；已标ERROR_BLOCKED")


try: acquire_project_lock(args.record, "rebuild_templates")
except RuntimeError as exc: print(f"❌ {exc}"); sys.exit(4)

old = collect_old()
print(f"[0/4] 旧模板(prefix={args.prefix}): {len(old)}")
if args.dry_run:
    for n, i in old[:3]: print(f"   (dry) {n} {i}")
    print("   (dry) 序列回读预览: ", end="")
    readback_seq_inactive(enforce=False)
    print("dry-run 结束(不建/不改/不删)"); sys.exit(0)

# ★审批硬闸门+参数绑定: 按本次实际参数(seq/profile/plan/suffix)重算哈希, 凭证memo须逐字一致
require_approval(args.approval, args.project, ("S7", "S8"), what="重建模板+序列步骤",
                 expected_hash=stable_params_hash(binding))

# ★前置回读: 序列必须 inactive(失败/未命中/非inactive 退出)
readback_seq_inactive(enforce=True)

# 1) 生成新模板(差异达标) + 落盘 name→id（★先建新, 旧模板仍被序列引用不能删）
outf = str(OUT_PATH)
temp_record = Path(args.record).with_name(".rebuild-operation-record.tmp")
shutil.copy2(args.record, temp_record)
temp_text = re.sub(r"(?m)^status:.*$", "status: S8", temp_record.read_text(encoding="utf-8"), count=1)
temp_text = re.sub(r"(?m)^next_state:.*$", "next_state: S9", temp_text, count=1)
temp_record.write_text(temp_text, encoding="utf-8")
try:
    child_env = dict(__import__('os').environ); child_env["LFX_PARENT_LOCK"] = str(Path(args.record).resolve().parent / ".operation.lock")
    subprocess.run([sys.executable, str(KB/"tools"/"gen_templates.py"), "--token", args.token, "--org", args.org,
                    "--product", args.product, "--prefix", args.prefix, f"--suffix={args.suffix}",
                    "--name", args.name, "--profile", args.profile, "--plan", args.plan,
                    "--out", outf, "--record", str(temp_record), "--approval", args.gen_approval, "--project", args.project],
                   check=True, env=child_env)
except subprocess.CalledProcessError:
    recovery_target = "S10" if PREVIOUS_RUN_STATE == "S11" else PREVIOUS_RUN_STATE
    update_frontmatter(args.record, {"status": "ERROR_BLOCKED", "next_state": recovery_target}, expected_states=(PREVIOUS_RUN_STATE,))
    print("❌ 新模板生成部分失败，真实record已标ERROR_BLOCKED；不得继续重建/激活")
    sys.exit(1)
finally:
    temp_record.unlink(missing_ok=True)
mapping = json.load(open(outf))
all_ids = list(mapping.values())
assert len(all_ids) == 120, f"期望120新模板, 实得 {len(all_ids)}"
groups = [all_ids[i*10:(i+1)*10] for i in range(12)]
print(f"[1/4] 生成新模板 {len(all_ids)} 个 (差异达标, 待 check_template_diff 实测)")

# 危险步骤写入前再次回读inactive，堵住创建120模板期间被激活的竞态
ok_inactive, _ = readback_seq_inactive(enforce=False)
if not ok_inactive:
    mark_rebuild_error("创建新模板后序列不再明确inactive，禁止修改步骤")
    sys.exit(1)
# 2) 序列12步 step-save 指向新模板（★先改引用, 旧模板才可删; ★任一步失败立即中止, 绝不删除旧模板）
d = api("sequences/step-list", {"seqId": args.seq, "current":1, "pageSize":20})
data = d.get("data")
lst = data if isinstance(data, list) else (data.get("list", []) if isinstance(data, dict) else [])
if not isinstance(lst, list) or not lst:
    mark_rebuild_error("step-list首次回读失败/为空（新模板已生成，序列未改）")
    sys.exit(1)
lst = sorted(lst, key=lambda s: s.get("step", 0))
if len(lst) != 12:
    mark_rebuild_error(f"step-list首次回读步数={len(lst)}≠12")
    sys.exit(1)
print(f"[2/4] 序列 {len(lst)} 步 → 逐个 step-save 指向新模板")
for s in lst:
    ok_now, _ = readback_seq_inactive(enforce=False)
    if not ok_now:
        mark_rebuild_error("逐步写入前序列不再inactive")
        sys.exit(1)
    step = s.get("step")
    payload = {"seqId": args.seq, "id": s.get("_id"), "step": step,
               "template_ids": groups[step-1],
               "wait_mode": s.get("wait_mode"), "wait_time": s.get("wait_time"),
               "senders": s.get("senders", [])}
    r = api("sequences/step-save", payload)
    if not r.get("success"):
        print(f"   step{step}: ❌ {str(r)[:80]}")
        recovery_target = "S10" if PREVIOUS_RUN_STATE == "S11" else PREVIOUS_RUN_STATE
        update_frontmatter(args.record, {"status": "ERROR_BLOCKED", "next_state": recovery_target}, expected_states=(PREVIOUS_RUN_STATE,))
        print("  ❌ step-save 失败——已标ERROR_BLOCKED，旧模板一律未删；修复/核对后从记录目标恢复")
        sys.exit(1)
    print(f"   step{step}: ✅")

def mark_rebuild_error(message):
    recovery_target = "S10" if PREVIOUS_RUN_STATE == "S11" else PREVIOUS_RUN_STATE
    update_frontmatter(args.record, {"status": "ERROR_BLOCKED", "next_state": recovery_target}, expected_states=(PREVIOUS_RUN_STATE,))
    print("❌ " + message + "；已标ERROR_BLOCKED")


# 2.5) ★全部12步回读验证均指向新模板ID, 否则绝不删除旧模板
new_id_set = set(all_ids)
d2 = api("sequences/step-list", {"seqId": args.seq, "current":1, "pageSize":20})
data2 = d2.get("data")
lst2 = data2 if isinstance(data2, list) else (data2.get("list", []) if isinstance(data2, dict) else [])
if not isinstance(lst2, list) or len(lst2) != 12:
    mark_rebuild_error(f"step-list回读失败/步数错误(实得 {len(lst2) if isinstance(lst2, list) else '非列表'})")
    sys.exit(1)
bad_steps = []
for s in sorted(lst2, key=lambda x: x.get("step", 0)):
    tids = [str(t) for t in (s.get("template_ids") or [])]
    if not tids or not all(t in new_id_set for t in tids):
        bad_steps.append((s.get("step"), tids[:3]))
if bad_steps:
    mark_rebuild_error("回读发现部分步骤未指向本次新模板ID")
    for st, tids in bad_steps:
        print(f"   - step{st}: template_ids={tids}…")
    sys.exit(1)
print("✅ 回读验证: 全部12步 template_ids 均指向本次新生成模板ID——可以删除旧模板")

# 3) 删旧模板（现在已不被引用, 且12步回读验证通过）
fails = []
for n, i in old:
    r = api("mailbox/template-delete", {"id": i})
    if not r.get("success"): fails.append(n)
print(f"[3/4] 删除旧模板: {len(old)-len(fails)}/{len(old)} 成功" + (f"; 失败 {fails[:5]}" if fails else ""))
if fails:
    recovery_target = "S10" if PREVIOUS_RUN_STATE == "S11" else PREVIOUS_RUN_STATE
    update_frontmatter(args.record, {"status": "ERROR_BLOCKED", "next_state": recovery_target}, expected_states=(PREVIOUS_RUN_STATE,))
    print("❌ 旧模板未全部清理，已标ERROR_BLOCKED；完成清理并提交已解决+放行证据后恢复")
    sys.exit(1)
resume_state = "S9" if PREVIOUS_RUN_STATE == "S9" else "S10"
next_state = "S10" if resume_state == "S9" else "S11"
update_frontmatter(args.record, {"status": resume_state, "next_state": next_state,
                                  "profile_version": f'"{PROFILE_META.get("profile_version", "")}"',
                                  "profile_sha256": f'"{PROFILE_SHA}"'}, expected_states=(PREVIOUS_RUN_STATE,))
print(f"✅ 重建后运行状态: {resume_state} (next={next_state}); 须重新跑模板差异/序列终检")

print("\n✅ 完成。请校验:")
print(f"   python3 tools/check_template_diff.py --token <T> --org {args.org} --prefix '{args.prefix}' --limit 120")
print(f"   python3 tools/verify_sequence.py --token <T> --org {args.org} --seq {args.seq}")
