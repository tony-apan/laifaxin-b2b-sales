#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""序列+联系人 联合确认：prepare → present(出卡) → confirm(引用卡) → execute。

一个人类回复（1/确认，且必须引用本卡）批准两个分别参数绑定的动作：建序列(现役 build_sequence.py 的 S9 审批)
与加人(现役 contact_add_authorized.py 的 S10 审批 + 写票据)。不调用已封死的 contact_add.py；不激活、不发信、不铸 S12。
- plan 绑定：配置 + 依赖文件(tmap/meta/档案/S5 计划)真实 sha + S5 binding/任务/标签/人数；execute 前逐项重验。
- 加人的序列 id 只取自建序列的机器回执 + 平台 inactive 回读；票据由 auth_guard.authorize_bundle_contact 内部验证后铸造。
- 凭据只走 stdin，经子进程 stdin 传递。作用域锁(flock)+原子落盘；成功子步骤不重放。
"""
def _utf8_stdout():
    import sys as _sys
    for _s in (_sys.stdout, _sys.stderr):
        try: _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError): pass
_utf8_stdout()
import argparse, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KB / "tools"))
import approval, auth_guard, save_plan  # noqa: E402
from profile_utils import profile_gate  # noqa: E402

SYMBOL = "@bundle-created-seq"
BASE = "https://web.laifaxin.com/marketing/sequences"


def die(msg, code=2):
    print("❌ " + msg); raise SystemExit(code)


def _fsha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def _abs(p): p = Path(p); return str(p if p.is_absolute() else (KB / p))
def _dir(): d = KB / ".local" / "bundle"; d.mkdir(parents=True, exist_ok=True); return d
def _load(p):
    try: return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc: die(f"读不了 {p}: {exc}")
def _save(p, doc):
    tmp = Path(str(p) + ".tmp"); tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8"); os.replace(tmp, p)


def s9_binding(d):
    s = d["s9"]
    return {"project": d["project"], "org_sha256": d["org_sha256"], "name": s["name"], "from_name": s["from_name"],
            "profile": s["profile"], "tmap": {"sha256": s["tmap_sha256"]}, "rules": s["rules"]}


def s10_binding(d, seq):
    s = d["s10"]
    return {"project": d["project"], "org_sha256": d["org_sha256"], "seq": seq, "tags": s["tags"], "task": s["task"]}


def check_plan(d):
    if d.get("kind") != "sequence_contact_bundle" or auth_guard.bundle_plan_hash(d) != d.get("plan_hash"):
        die("联合计划已被改动或不是有效计划；写 0")


def check_deps(d):
    """重验全部影响执行的依赖文件（真实 sha）+ 当前 S5 计划 binding/标签/任务。"""
    dp = d["deps"]
    for k in ("tmap", "tmap_meta", "profile", "s5_plan"):
        try: cur = _fsha(dp[k]["path"])
        except OSError: die(f"依赖文件缺失: {k}；写 0")
        if cur != dp[k]["sha256"]: die(f"依赖文件已变化（{k}）：配置/批次已不是确认时的样子，须重新出卡确认；写 0")
    plan = save_plan.load_plan(dp["s5_plan"]["path"]); wire = plan.get("wire_payload") or {}
    if plan.get("status") != "confirmed" or plan.get("binding_sha256") != save_plan.binding_hash(plan) \
            or plan.get("binding_sha256") != dp["s5_plan"]["binding_sha256"] or sorted(wire.get("contactTags") or []) != d["s10"]["tags"]:
        die("当前保存计划与确认时的批次不一致；写 0")


def prepare(a):
    prof = _abs(a.profile); status, issues, meta, sha = profile_gate(Path(prof))
    if issues: die("产品档案闸门未过: " + "; ".join(map(str, issues)))
    tmap, s5 = _abs(a.tmap), _abs(a.s5_plan); tmeta = _load(tmap + ".meta.json"); plan = save_plan.load_plan(s5)
    tags = sorted((plan.get("wire_payload") or {}).get("contactTags") or [])
    if plan.get("status") != "confirmed" or plan.get("project") != a.project: die("S5 计划未 confirmed 或项目不符")
    if len(tags) != 1 or not a.task or a.expected_contacts <= 0: die("加人需恰好一个联系人标签、保存任务id、预计人数>0")
    d = {"kind": "sequence_contact_bundle", "project": a.project, "org_sha256": hashlib.sha256(a.org.encode()).hexdigest(), "status": "prepared",
         "deps": {"record": {"path": _abs(a.record)}, "tmap": {"path": tmap, "sha256": _fsha(tmap)},
                  "tmap_meta": {"path": tmap + ".meta.json", "sha256": _fsha(tmap + ".meta.json")},
                  "profile": {"path": prof, "sha256": _fsha(prof)},
                  "s5_plan": {"path": s5, "sha256": _fsha(s5), "binding_sha256": plan.get("binding_sha256")}},
         "s9": {"name": a.name, "from_name": a.from_name, "tz": a.tz, "max_per_day": a.max_per_day, "per_domain": a.per_domain,
                "tmap_sha256": tmeta.get("tmap_sha256"), "profile": {"sha256": sha, "status": status, "version": meta.get("profile_version", "")},
                "rules": {"steps": 12, "waits": "step1=30分,step2=5天,step3=15天,step4-12=30天", "tz": a.tz,
                          "daily_limit": f"{a.max_per_day}/{a.per_domain}", "not_sent_tags": "询盘/不发"}},
         "s10": {"tags": tags, "task": a.task, "expected_contacts": a.expected_contacts, "seq": SYMBOL}, "steps": {}}
    d["plan_hash"] = auth_guard.bundle_plan_hash(d); path = _dir() / f"bundle-{d['plan_hash'][:12]}.json"; _save(path, d)
    print(f"✅ 联合计划已生成（仅准备，未写平台）: {path}"); return path


def card_text(d):
    s, n = d["s9"], d["s10"]["expected_contacts"]
    return (f"这次一并确认两件事（只做这两件，不会激活、不会发信）：\n"
            f"① 新建一条发信序列「{s['name']}」：发件昵称 {s['from_name']}，时区 {s['tz']}，共 12 步（第 1 步 30 分钟后，第 2 步隔 5 天，第 3 步隔 15 天，之后每步隔 30 天），共 48 个邮件模板；"
            f"每天最多 {s['max_per_day']} 封，同一家公司最多 {s['per_domain']} 封；带「询盘」「不发」标签的客户不发。\n"
            f"② 把已确认保存批次的联系人加入这条新序列，预计 {n} 人（以平台实际回读为准）。\n"
            f"风险：建好后序列是未启动状态，只有您另行回复「确认激活」才会真正发信；配置或批次一变，需要重新出卡。\n"
            f"回「1」或「确认」= 同意以上两件事。")


def present(a):
    d = _load(a.bundle); check_plan(d); check_deps(d); text = card_text(d); now = int(time.time())
    card = {"kind": "bundle_card", "plan_hash": d["plan_hash"], "deps": d["deps"], "created_at": now, "expires_at": now + a.ttl_seconds,
            "risk": "未激活不发信；配置/批次变更须重新出卡", "card_text_sha256": hashlib.sha256(text.encode()).hexdigest()}
    cp = _dir() / f"card-{d['plan_hash'][:12]}-{now}.json"; _save(cp, card)
    print(text); print(f"卡文件: {cp}")


def confirm(a):
    d = _load(a.bundle); check_plan(d); check_deps(d)
    card = _load(a.card)
    if card.get("kind") != "bundle_card" or card.get("plan_hash") != d["plan_hash"] or card.get("deps") != d["deps"]: die("确认卡与当前联合计划不符；未铸审批")
    if card_sha_text(d) != card.get("card_text_sha256"): die("确认卡展示内容与计划不符；未铸审批")
    if time.time() > card.get("expires_at", 0): die("确认卡已过期，请重新出卡；未铸审批")
    q = str(a.quote or "").strip()
    if any(w in q for w in ("激活", "发送", "发信", "启动")): die("这句话涉及激活/发信，不能当作本卡的确认；未铸审批")
    if not (approval.numeric_confirm_quote(q, "S9") or approval.confirm_quote_ok(q)): die("不是明确同意（含否定/疑问/等待）；未铸审批")
    if d.get("status") != "prepared": die("该联合计划已确认过")
    ap9 = approval.record(d["project"], "S9_序列配置", "confirm", q, approval.stable_params_hash(s9_binding(d)))
    d.update(status="confirmed", s9_approval=ap9, confirmation={"quote": q, "card_path": _abs(a.card), "card_sha256": _fsha(a.card), "at": int(time.time())})
    _save(a.bundle, d); print("✅ 已记录您的确认；建序列审批已铸，加人审批将在序列建成并回读后按本计划铸造")


def card_sha_text(d): return hashlib.sha256(card_text(d).encode()).hexdigest()


def run(cmd, blob, env=None):
    # 显式以 os.environ 为底合并调用方 env（与不传 env 的继承语义等价）；凭据只走 stdin，不进 argv/env
    e = dict(os.environ); e.update(env or {})
    r = subprocess.run(cmd, input=blob, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1900, env=e)
    return r.returncode, r.stdout + r.stderr


def acquire_scope_lock(bundle):
    """跨平台作用域锁：O_EXCL 原子创建，进程退出自动消失；存在即拒（fail-closed，不删锁不重进）。"""
    lk = Path(str(bundle) + ".lock")
    try:
        fd = os.open(str(lk), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, json.dumps({"pid": os.getpid(), "at": int(time.time())}).encode()); os.close(fd)
    except FileExistsError:
        return False
    return True


def release_scope_lock(bundle):
    Path(str(bundle) + ".lock").unlink(missing_ok=True)


def execute(a):
    d = _load(a.bundle); check_plan(d)
    if not acquire_scope_lock(a.bundle): die("存在执行锁（另一执行进行中或上次崩溃残留）：fail-closed，不删锁；确认无并发后人工移除该锁文件再试；写 0", 3)
    try:
        _execute_locked(a, d)
    finally:
        release_scope_lock(a.bundle)


def _execute_locked(a, d):
    check_deps(d)
    from credential_input import parse_credentials
    blob = sys.stdin.buffer.read(8193).decode("utf-8"); token, org = parse_credentials(blob.encode())
    if hashlib.sha256(org.encode()).hexdigest() != d["org_sha256"]: die("org 与联合计划不一致；写 0")
    import platform_http
    def api(p, pl, t=50):
        try: return json.loads(platform_http.post(p, pl, token, org, t) or "{}")
        except ValueError: return {}
    st, s9, s10, py = d["steps"], d["s9"], d["s10"], sys.executable
    sv = lambda: _save(a.bundle, d)
    if st.get("create") != "done":
        if st.get("create_attempted") and not st.get("seq_id"): die("建序列此前已发起但没有回执：先到平台序列列表按计划名核对，不盲重放", 3)
        if st.get("seq_id"): die(f"建序列此前未完整完成（已有序列 {st['seq_id']}）：不重新创建，请先核对该序列", 3)
        rp = _dir() / f"receipt-create-{d['plan_hash'][:12]}.json"; rp.unlink(missing_ok=True); st["create_attempted"] = int(time.time()); sv()
        rc, out = run([py, str(KB / "tools/build_sequence.py"), "--credentials-stdin", "--name", s9["name"], "--tmap", d["deps"]["tmap"]["path"],
                       "--profile", d["deps"]["profile"]["path"], "--from-name", s9["from_name"], "--tz", s9["tz"], "--max-per-day", str(s9["max_per_day"]),
                       "--per-domain", str(s9["per_domain"]), "--record", d["deps"]["record"]["path"], "--approval", d["s9_approval"],
                       "--project", d["project"], "--receipt-file", str(rp)], blob)
        rc_doc = _load(rp) if rp.exists() else {}
        if re.fullmatch(r"[0-9a-f]{24}", str(rc_doc.get("seq_id"))) and rc_doc.get("name") == s9["name"]: st["seq_id"] = rc_doc["seq_id"]
        if rc != 0:
            d["status"] = "partial"; st["create_error"] = out[-500:]; sv(); print(out[-700:])
            die(f"建序列未完成(exit {rc})；已建序列={st.get('seq_id', '无回执')}。部分完成：不加人、不激活、不自动删除", rc or 1)
        item = next((x for x in ((api("sequences/sequence-list", {"current": 1, "pageSize": 100, "filter": {}, "sort": {}}).get("data") or {}).get("list") or [])
                     if isinstance(x, dict) and str(x.get("id")) == st.get("seq_id")), None)
        if not item or str(item.get("status")) != "inactive": die("建序列后回读不是未启动状态；部分完成，不加人", 3)
        st["create"] = "done"; d["receipt"] = {"seq_id": st["seq_id"], "plan_hash": d["plan_hash"], "readback_status": "inactive", "name": s9["name"]}; sv()
    seq = st["seq_id"]; pay = {"seqId": seq, "tags": s10["tags"], "views": []}
    sent_marker = _dir() / f"contact-sent-{d['plan_hash'][:12]}.json"
    if (d.get("receipt") or {}).get("seq_id") != seq: die("建序列回执与记录的序列不一致；写 0", 3)
    def count():
        # ★R2-AC2：按公开前端契约 POST sequences/sequence-summary {id} 取 data.contactsCount；
        # 缺失/类型非法/身份矛盾一律 None（unknown），绝不假 0。
        r = api("sequences/sequence-summary", {"id": seq})
        d = r.get("data") if isinstance(r.get("data"), dict) else {}
        v = d.get("contactsCount")
        if not isinstance(v, int) or isinstance(v, bool): return None
        if d.get("id") not in (None, seq): return None
        return v
    if st.get("contact") != "done":
        if st.get("contact_state") in ("sending", "rejected"):  # 结果不确定/被拒：先只读回读，不盲重放
            n = count()
            st["contact_readback"] = {"seq": seq, "count": n, "at": int(time.time())}
            if n == s10["expected_contacts"]:
                st["contact"] = "done"; sv()
            elif st.get("contact_state") == "rejected" and not sent_marker.exists() and n == 0:
                # 仅"从未发出"(rejected：票据/对账在写前被拒，receipt 无 sending)且回读 0 才允许释放精确票续发
                sv()
                rel = auth_guard.release_bundle_payload_after_zero(d, pay)
                if not rel.get("ok"): die("续发释放被拒: " + str(rel.get("reason")), 3)
            else:
                d["status"] = "partial"; sv()
                die(f"加人结果不确定（回读联系人数={'未知' if n is None else n}，预计 {s10['expected_contacts']}；state={st.get('contact_state')}）：保持部分完成，不盲重放", 3)
    if st.get("contact") != "done":
        ap10 = approval.record(d["project"], "S10_加联系人", "confirm", d["confirmation"]["quote"], approval.stable_params_hash(s10_binding(d, seq)))
        au = auth_guard.authorize_bundle_contact(d, pay)
        if not au.get("ok"): die("加人票据未铸成: " + str(au.get("reason")))
        cr = _dir() / f"receipt-contact-{d['plan_hash'][:12]}.json"; cr.unlink(missing_ok=True)
        st.update(contact_ticket=au["ticket_path"], s10_approval=ap10, contact_state="pre_send"); sv()
        rc, out = run([py, str(KB / "tools/contact_add_authorized.py"), "--credentials-stdin", "--seq", seq, "--tags", ",".join(s10["tags"]), "--task", s10["task"],
                       "--plan", d["deps"]["s5_plan"]["path"], "--record", d["deps"]["record"]["path"], "--approval", ap10, "--project", d["project"],
                       "--auth-ticket", au["ticket_path"], "--receipt-file", str(cr)], blob)
        phases = [json.loads(l) for l in cr.read_text(encoding="utf-8").splitlines() if l.strip()] if cr.exists() else []
        rec = phases[-1] if phases else {}
        sent_any = any(x.get("phase") == "sending" for x in phases)
        # receipt 按 os.replace 覆盖写：若曾到 sending 再失败，文件只剩 result{success:false} → 须结合 pre-send 判定
        # 发出后结果不确定 = 曾记录 sending 阶段。为可靠区分，sending 阶段单独落一个 marker 文件。
        if sent_any:
            sent_marker.write_text(json.dumps({"seq": seq, "at": int(time.time())}), encoding="utf-8")
        st["contact_state"] = ("sending" if sent_marker.exists() else "rejected" if (rec.get("phase") == "result" and not rec.get("success")) else "pre_send" if not rec else "result")
        st["contact_receipt"] = {k: rec.get(k) for k in ("phase", "seq", "success", "add", "estimated", "contactSaveCount")}
        if rc != 0:
            d["status"] = "partial"; st["contact_error"] = out[-500:]; sv(); print(out[-700:])
            die(f"序列已建(序列={seq})但加人未完成(exit {rc})：部分完成（状态={st['contact_state']}）；重跑会先回读核对，不重新建序列", rc or 1)
        st["contact"] = "done"
    d["status"] = "executed"; d["simulation"] = bool(os.environ.get("LFX_BUNDLE_TEST_BASE_URL")); sv()  # 仅受控 loopback 替身才标 simulation
    add = (st.get("contact_receipt") or {}).get("add")
    n = count()
    report(d, api, n)  # 打印回读明细（含 summary 总人数）
    man = getattr(a, "manifest", None)
    if man and n == s10["expected_contacts"]:
        _finalize_core(a.bundle, d, man, blob.encode("utf-8"), org)  # 证据已备：真正调用现役 finalize_run
    report_pending(d, n, add, a.bundle, bool(man))


def report_pending(d, n, add, bundle, had_manifest=False):
    """R2-AC3：两动作完成但 S11 未收口——机读 pending、明确唯一下一步、非全完成退出态(4)。"""
    s9, s10 = d["s9"], d["s10"]
    reasons = ["S11 终检未收口（未提供 manifest，四份 live 证据未备齐/未运行 finalize_run）" if not had_manifest else "S11 终检未收口（联系人总数回读未知或与预计不吻合，不调用 finalize_run）"]
    if n != s10["expected_contacts"]: reasons.append("联系人总数回读" + ("未知" if n is None else f"={n}") + f"，预计 {s10['expected_contacts']}")
    d["s11"] = {"state": "pending", "reasons": reasons}; _save(bundle, d)
    print(f"""【联合结果（以平台回读为准；未知项如实标未知）】
序列「{s9['name']}」：本次新建成功（详见回读报告）
联系人：预计 {s10['expected_contacts']} 人；本次新增 add={'未知' if add is None else add}；当前总人数={'未知' if n is None else n}（{'吻合' if n == s10['expected_contacts'] else '不吻合/未知，需人工核对'}）
建计划/加人已完成，终检未完成。唯一下一步：用四份真实读取证据（序列验证/排除4区/模板差异/核实面板）生成 manifest 后运行 finalize 子命令收 S11；收口前不得激活。
machine: s11.state=pending; reasons={reasons}""")
    raise SystemExit(4)


def report(d, api, n):
    import verify_sequence, s11_closure
    seq = d["steps"]["seq_id"]; s9, s10 = d["s9"], d["s10"]
    rc = d["steps"].get("contact_receipt") or {}
    data = lambda p, pl: api(p, pl).get("data", {})
    ok, issues, info = verify_sequence.check_sequence(lambda p, pl, timeout=50: data(p, pl), seq)
    steps = data("sequences/step-list", {"seqId": seq, "current": 1, "pageSize": 50}); steps = steps if isinstance(steps, list) else []
    tpl = sum(len(x.get("template_ids") or []) for x in steps if isinstance(x, dict))
    waits = ",".join(f"{x.get('wait_mode')}/{x.get('wait_time')}" for x in steps if isinstance(x, dict))
    rules = (data("sequences/sequence-details", {"id": seq}) or {}).get("rules") or {}
    meta = {}
    try:
        for l in Path(d["deps"]["record"]["path"]).read_text(encoding="utf-8").split("---")[1].splitlines():
            if ":" in l: k, v = l.split(":", 1); meta[k.strip()] = v.strip()
    except (OSError, IndexError): pass
    s11 = s11_closure.check_s11_closure(meta)
    cnt_ok = n == s10["expected_contacts"]
    add = rc.get("add")
    print(f"""【联合结果（以平台回读为准；未知项如实标未知）】
序列「{s9['name']}」(id {seq})：状态={info.get('status') or '未知'}；步骤={info.get('steps', '未知')}；已绑定模板={tpl}（计划 48）；终检={'通过' if ok else '未通过: ' + '; '.join(issues)}
各步间隔(回读)：{waits or '未知'}；时区：计划值 {s9['tz']}（平台未回读该字段，未确认已生效）
回读规则：每日上限={rules.get('max_emails_per_day', '未知')}，每域上限={rules.get('domain_emails_per_day', '未知')}，保护标签={rules.get('notSentTags', '未知')}
联系人：预计 {s10['expected_contacts']} 人；保存任务 {s10['task']} contactSaveCount={rc.get('contactSaveCount', '未知')}；实际新增 add={'未知' if add is None else add}；平台回读该序列联系人数={'未知' if n is None else n}（{'吻合' if cnt_ok else '不吻合/未知'}）
仍未激活，未发信。核对入口：{BASE} （按计划名「{s9['name']}」定位；不拼详情路由）""")
    if not ok: print("⚠️ 未全绿：终检核心未过，请先核对。")


def _finalize_core(bundle, d, manifest, blob, org):
    """R2-AC3：调用现役 finalize_run（live 四证齐才落 S11）。证据缺/非 live → 机读 pending + 非全完成退出态 4，绝不伪造。"""
    st = d["steps"]; rec_path = d["deps"]["record"]["path"]; sim = d.get("simulation")
    if hashlib.sha256(org.encode()).hexdigest() != d["org_sha256"]: die("org 与联合计划不一致")
    def pend(reason):
        d["s11"] = {"state": "pending", "reasons": [reason]}; _save(bundle, d)
        print("建计划/加人已完成，终检未完成。\nmachine: s11.state=pending; reasons=" + str([reason])); raise SystemExit(4)
    man = _load(manifest)
    if man.get("evidence_mode") != "live":
        pend("evidence_mode 非 live（simulation 不得伪装生产 live）——不写 S11")
    cmd = [sys.executable, str(KB / "tools/finalize_run.py"), "--record", rec_path, "--profile", d["deps"]["profile"]["path"],
           "--project", d["project"], "--org", org, "--seq", st["seq_id"], "--manifest", str(Path(manifest).resolve())]
    rc, out = run(cmd, "")  # finalize_run 只读本地 record/manifest，不需要也不接收凭据
    print(out[-1500:])
    if rc != 0: pend("finalize_run exit " + str(rc))
    d["s11"] = {"state": "done", "finalized_with_manifest": str(Path(manifest).resolve()), "simulation": bool(sim)}
    _save(bundle, d)
    if sim: print("（终检在受控模拟环境完成：证据来自 loopback 替身，不声称线上 live。）")
    print("✅ S11 已按原 finalize_run 收口（next=S12，仍未激活）"); raise SystemExit(0)


def finalize(a):
    d = _load(a.bundle); check_plan(d)
    if d.get("status") != "executed" or d["steps"].get("contact") != "done":
        die("两动作尚未完成：先 execute 成功后再收终检")
    from credential_input import parse_credentials
    blob = sys.stdin.buffer.read(8193)
    token, org = parse_credentials(blob)
    if a.org and a.org != org: die("--org 与凭据不一致")
    _finalize_core(a.bundle, d, a.manifest, blob, org)


def main(argv=None):
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("prepare")
    for k in ("project", "org", "record", "tmap", "profile", "name", "from-name", "s5-plan", "task"): pr.add_argument("--" + k, required=True)
    pr.add_argument("--tz", default="America/New_York"); pr.add_argument("--max-per-day", type=int, default=30000)
    pr.add_argument("--per-domain", type=int, default=5); pr.add_argument("--expected-contacts", type=int, required=True)
    for n in ("present", "confirm", "execute"): sub.add_parser(n).add_argument("--bundle", required=True)
    sub.choices["execute"].add_argument("--manifest", default=None, help="可选：四份 live 证据 manifest；提供且总数吻合则自动调用 finalize_run 收 S11")
    fz = sub.add_parser("finalize"); fz.add_argument("--bundle", required=True); fz.add_argument("--manifest", required=True); fz.add_argument("--org", default=None)
    sub.choices["present"].add_argument("--ttl-seconds", type=int, default=1800)
    sub.choices["confirm"].add_argument("--card", required=True); sub.choices["confirm"].add_argument("--quote", required=True)
    a = p.parse_args(argv); {"prepare": prepare, "present": present, "confirm": confirm, "execute": execute, "finalize": finalize}[a.cmd](a)


if __name__ == "__main__":
    main()
