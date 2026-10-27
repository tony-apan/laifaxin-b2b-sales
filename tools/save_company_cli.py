#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""现役唯一真实保存通道（Guard V2：prepare → confirm → execute → status/reconcile）。

旧脚本（save_first_n / lfx_mass_save* / wait_save_done / contact_add / 删库 5 个）
仍被 save_guard.require() 无条件封条退役。合法 S5 保存必须：

  1. prepare  纯本地推导 draft（规则原文摘录/来源/预算/18 字段 wire）；
             不取凭据、不构造 transport、不签 auth、可写 --out。
  2. confirm 用 draft + 用户原话产出 confirmed plan，并由
             auth_guard.authorize_save_plan 唯一铸票（一次）+ 生成 S5V2 render。
  3. execute 先 workspace_guard.preflight() 核验工作空间落点（fail-closed：被阻断时
              不构造 transport、不调保存接口）→ 重验 payload/plan/依赖 → scope 占位 →
              auth.begin → 一次提交；
             uncertain 保留锁，不 abort。
  4. status  唯一自动对账生产者：按账簿只读查保存任务（type=cluesSave）。
  5. reconcile 只消费本 CLI status 的登记记录；外部 JSON 一律 E_RECONCILE_SOURCE。

旧无子命令参数形式保留为 execute 别名，但同样必须给 confirmed plan；缺计划直接拒。
"""
from __future__ import annotations

def _utf8_stdout():
    """Windows 控制台/管道默认 GBK：输出 emoji 会抛 UnicodeEncodeError；显式改 UTF-8。"""
    import sys as _sys
    for _s in (_sys.stdout, _sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
_utf8_stdout()

import argparse
import json
import math
import os
import time

import save_progress
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import api_base_url
import auth_guard
import render_guard
import rule_check
import save_guard
import save_plan as planlib
import segment_registry as registry
import step_gate
import workspace_guard
from search_company import rule_excerpts

SAVE_ENDPOINT = "refine/company-save"


def _load_json(text: Optional[str], path: Optional[str]) -> Any:
    if text is not None and path is not None:
        raise ValueError("--json 与 --file 只能二选一")
    if path is not None:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    if text is not None:
        return json.loads(text)
    raise ValueError("必须提供 JSON 文本或文件路径")


def _http(token: str, org: str, timeout: int, endpoint: str = SAVE_ENDPOINT):
    """真实平台写 transport；只应被 execute 在全部本地闸门之后调用。"""
    def call(payload: Dict[str, Any]) -> Dict[str, Any]:
        cmd = ["curl", "-sSL", "-X", "POST", api_base_url.api_url(endpoint),
               "-H", "Content-Type: application/json",
               "-H", "accesstoken: " + token, "-H", "uid: " + org,
               "-d", json.dumps(payload, ensure_ascii=False)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        try:
            return json.loads(result.stdout)
        except Exception:
            return {"success": False, "message": (result.stdout or result.stderr)[:300]}
    return call


def _print_result(result: Dict[str, Any]) -> int:
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    if result.get("ok"):
        text = result.get("report_text")
        if text:
            print(text)
        return 0
    code = result.get("code") or ""
    if code in ("E_AUTH_REUSED",):
        return 3
    return 2


def _cmd_prepare(args: Any) -> int:
    """纯本地：凭据零读、零 transport、零 auth。输出来源/规则/预算/推导。"""
    root = Path(args.root) if args.root else TOOLS_DIR.parent
    offline = _load_json(args.request_json, args.request_file)
    # 铁律7 标签闸门最先执行：坏标签直接 exit 2，不进入来源/预算推导。
    planlib.validate_offline_tags(root, str(offline.get("project", "")), offline)
    source = offline.get("source") or {}
    if not source.get("query_scope_key"):
        scope = rule_check.canonical_scope(
            workspace_ref=str(offline.get("project", "")),
            product_id=str(source.get("platform_product_id", "")),
            generation_id=str(source.get("generation_id", "")),
            selection_id=str(source.get("selection_id", "")),
            keyword=str((offline.get("wire_payload") or {}).get("keyword", "")),
            filters=(offline.get("wire_payload") or {}).get("filters", []),
            logic=(offline.get("wire_payload") or {}).get("logic", "and"),
            sort=(offline.get("wire_payload") or {}).get("selectSort", {}))
        source = dict(source)
        source["query_scope"] = {**scope, "query_scope_key": rule_check.scope_key(scope)}
    # B1：prepare 先经 registry 校验当前来源（旧 generation/跨产品/未登记 → E_SOURCE_STALE）。
    registry.validate_source(
        root, project=str(offline.get("project")),
        platform_product_id=str(source.get("platform_product_id", "")),
        generation_id=str(source.get("generation_id", "")),
        segment_id=str(source.get("segment_id", "")))
    draft = planlib.prepare_save(
        root, project=str(offline.get("project")),
        source=source, audit=offline.get("audit") or {},
        budget=offline.get("budget") or {},
        coefficients=offline.get("coefficients") or {},
        rule_excerpts=rule_excerpts(root), offline_input=offline,
        audit_manifest_path=str(offline.get("audit_manifest", "")))
    out = planlib.write_draft(root, draft, args.out)
    payload = {"ok": True, "stage": "prepare", "draft_path": out,
               "draft": draft, "credentials_read": 0, "transport_built": 0}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _make_render(root: Path, plan: Dict[str, Any], quote: str) -> Dict[str, Any]:
    wire = plan["wire_payload"]
    operator = str(plan.get("project", "operator"))
    product = str(plan.get("platform_product_id", "product"))
    seed = str(wire.get("keyword", "seed"))
    count = int(plan["selectTotal"])
    params_hash = rule_check.canonical_hash(wire)
    task = render_guard.derive_task_id(operator, product, seed, count, params_hash)
    points = (plan.get("computed") or {}).get("estimated_points")
    fields = {
        "标签ID": "标签: id = %s / %s" % (
            ",".join(str(t) for t in wire.get("companyTags", [])),
            ",".join(str(t) for t in wire.get("contactTags", []))),
        "保存家数": "保存家数: %d" % count,
        "预算点数": "预算点数: %s" % points,
    }
    data = {
        "node": "S5V2", "task": task, "task_id": task,
        "operator": operator, "product": product, "seed": seed, "count": count,
        "params_hash": params_hash, "user_quote": quote, "ts": plan.get("confirmed_at"),
        "fields": fields,
        "output": "S5 保存确认\n标签: %s\n保存家数: %d\n预算点数: %s\n客户: %d 家" % (
            fields["标签ID"], count, points, count),
    }
    render_dir = Path(root) / ".local" / "renders"
    render_dir.mkdir(parents=True, exist_ok=True)
    path = render_dir / ("S5V2-%s.json" % task)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)
    return {"path": str(path), "task": task}


def _cmd_confirm(args: Any) -> int:
    root = Path(args.root) if args.root else TOOLS_DIR.parent
    draft = planlib.load_plan(args.plan)
    try:
        confirmed = planlib.confirm_plan(root, draft, quote=args.quote,
                                         quote_ref=args.quote_ref)
    except planlib.PlanError as exc:
        print(json.dumps({"ok": False, "stage": "confirm", "code": exc.code,
                          "reason": exc.reason}, ensure_ascii=False))
        return 2
    render = _make_render(root, confirmed, args.quote)
    issued = auth_guard.authorize_save_plan(
        "save", args.quote, confirmed["wire_payload"], plan=confirmed,
        task=render["task"], root=root)
    if not issued["ok"]:
        print(json.dumps({"ok": False, "stage": "confirm", "code": issued["code"],
                          "reason": issued["reason"]}, ensure_ascii=False))
        return 2
    result = {"ok": True, "stage": "confirm",
              "plan_path": str(planlib.plan_path(root, confirmed["plan_id"], confirmed["revision"])),
              "render_path": render["path"],
              "ticket_path": issued["ticket_path"], "task_id": render["task"],
              "authorize_calls": 1}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_execute(args: Any) -> int:
    root = Path(args.root) if args.root else TOOLS_DIR.parent
    plan = planlib.load_plan(args.plan)
    ticket = _load_json(args.ticket_json, args.ticket_file)
    render_path = args.render
    # ★RULES 声称的 workspace_guard 预检在这里落地（2026-10-23 P0 修复）：
    #   真正构造 transport / 调保存接口之前，先只读核验"声明的空间"被平台采纳。
    #   fail-closed：确凿误路由 → SystemExit(1)；预检异常同样阻断。
    #   被阻断时不得构造 _http、不得调用 save_company_v2（平台写入 0 次）。
    try:
        workspace_guard.preflight(args.token, args.org, what="S5 保存")
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) and exc.code != 0 else 1
        print(json.dumps({"ok": False, "stage": "execute", "code": "E_WORKSPACE_GUARD",
                          "reason": "工作空间预检未通过：本次不向平台写入任何数据",
                          "preflight_exit": code}, ensure_ascii=False))
        return 2
    except Exception as exc:
        print(json.dumps({"ok": False, "stage": "execute", "code": "E_WORKSPACE_GUARD",
                          "reason": "工作空间预检异常：%s；本次不向平台写入任何数据" % exc},
                         ensure_ascii=False))
        return 2
    result = save_guard.save_company_v2(
        payload=plan["wire_payload"], http=_http(args.token, args.org, args.timeout),
        plan=plan, ticket=ticket, render_path=render_path, root=root)
    # save_company( 系列唯一执行入口在 save_guard；本 CLI 只经 v2 计划链调用。
    assert "save_company" in dir(save_guard)
    return _print_result(result)


def _cmd_status(args: Any) -> int:
    if getattr(args, "watch", False) and (not math.isfinite(args.interval) or
            not 5 <= args.interval <= 10 or args.max_polls <= 0):
        print("监视参数无效：interval 须为 5–10 秒，max-polls 须为正整数", file=sys.stderr)
        return 2
    root = Path(args.root) if args.root else TOOLS_DIR.parent
    plan = planlib.load_plan(args.plan)
    task_id = args.task_id
    attempt_id = str(args.attempt_id or "")
    if not task_id:
        # 保存成功后调用方不必知道 task_id：按 plan/revision 读已受理的 scope 账本。
        scope_doc = plan.get("query_scope") or {}
        key = scope_doc.get("query_scope_key")
        accepted = planlib.find_accepted_scope(
            root, plan_id=str(plan.get("plan_id")),
            revision=int(plan.get("revision") or 1),
            query_scope_key=str(key or ""))
        task_id = str(accepted.get("task_id")) if accepted.get("task_id") else None
        if not attempt_id:
            attempt_id = str(accepted.get("attempt_id") or "")
    if not task_id:
        print(json.dumps({"ok": False, "stage": "status",
                          "code": "E_RECONCILE_SOURCE",
                          "reason": "无 task_id：人工处置态，无自动回读证据"},
                         ensure_ascii=False))
        return 2
    watch = getattr(args, "watch", False)
    baseline = None
    for poll in range(args.max_polls if watch else 1):
        try:
            response = _http(args.token, args.org, args.timeout,
                             endpoint="operation/backend-task-status")(planlib.status_payload(task_id))
        except (OSError, subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
            if not watch:
                raise
            print("查询中断或失败：%s" % type(exc).__name__, file=sys.stderr, flush=True)
            return 2
        record_id = planlib.record_status(root, record={
            "project": plan.get("project"), "plan_id": plan.get("plan_id"),
            "revision": plan.get("revision"),
            "query_scope_key": (plan.get("query_scope") or {}).get("query_scope_key"),
            "attempt_id": attempt_id, "task_id": str(task_id),
            "response": response, "response_sha256": rule_check.canonical_hash(response),
            "result": "polled",
        })
        result = {"ok": True, "stage": "status", "record_id": record_id,
                  "task_id": task_id, "response": response}
        if not watch:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        data = response.get("data") if isinstance(response, dict) else None
        status = data.get("status") if isinstance(data, dict) else None
        if not isinstance(response, dict) or response.get("success") is not True or status not in ("running", "finished"):
            result["ok"] = False
            print("查询失败或平台状态未知，已停止；请核实。", file=sys.stderr, flush=True)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2
        saved, total = data.get("finished"), data.get("total")
        eta = None
        valid = (save_progress._count(saved) and save_progress._count(total)
                 and total > 0 and saved <= total)
        if status == "running" and valid:
            now = time.monotonic()
            if baseline is not None:
                previous, previous_total, previous_time = baseline
                elapsed = now - previous_time
                if (total == previous_total and saved > previous and saved < total
                        and math.isfinite(elapsed) and elapsed > 0):
                    try:
                        estimate = elapsed * ((total - saved) / (saved - previous))
                        if math.isfinite(estimate) and estimate > 0:
                            eta = estimate
                    except OverflowError:
                        pass
            baseline = (saved, total, now) if math.isfinite(now) else None
        else:
            baseline = None
        line = save_progress.format_progress(saved, total, eta_s=eta)
        print(line.replace("已存 ", "已处理 "), file=sys.stderr, flush=True)
        if status == "finished":
            print("平台报告完成，仍需对账。", file=sys.stderr, flush=True)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if (save_progress._count(data.get("finished")) and save_progress._count(data.get("total"))
                and data["total"] > 0 and data["finished"] >= data["total"]):
            print("等待平台完成并对账。", file=sys.stderr, flush=True)
        if poll + 1 < args.max_polls:
            try:
                time.sleep(args.interval)
            except KeyboardInterrupt:
                print("监视已中断。", file=sys.stderr, flush=True)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 2
    result["ok"] = False
    print("已达到轮询上限，平台尚未报告完成。", file=sys.stderr, flush=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2


def _cmd_reconcile(args: Any) -> int:
    root = Path(args.root) if args.root else TOOLS_DIR.parent
    plan = planlib.load_plan(args.plan)
    external = None
    if args.task_status_json:
        external = _load_json(args.task_status_json, args.task_status_file)
    try:
        outcome = planlib.reconcile(
            root, plan_id=str(plan.get("plan_id")),
            revision=int(plan.get("revision") or 1),
            query_scope_key=str((plan.get("query_scope") or {}).get("query_scope_key") or ""),
            attempt_id=str(args.attempt_id or ""), task_id=args.task_id,
            task_status_json=external, status_record_id=args.status_record)
    except planlib.PlanError as exc:
        print(json.dumps({"ok": False, "stage": "reconcile", "code": exc.code,
                          "reason": exc.reason}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "stage": "reconcile",
                      "scope": outcome["scope"], "record": outcome["record"]},
                     ensure_ascii=False, indent=2))
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="现役唯一真实保存通道（Guard V2）")
    sub = parser.add_subparsers(dest="cmd")

    prep = sub.add_parser("prepare", help="纯本地 draft：零凭据/零 transport/零 auth")
    prep.add_argument("--root", default=None)
    prep.add_argument("--request-file", default=None, dest="request_file")
    prep.add_argument("--request-json", default=None, dest="request_json")
    prep.add_argument("--out", default=None)
    prep.add_argument("--run", default=None,
                      help="执行卡运行标识；缺省读 DSH_RUN_ID，再缺省 default")
    prep.set_defaults(func=_cmd_prepare)

    conf = sub.add_parser("confirm", help="confirmed plan + 唯一铸票 + S5V2 render")
    conf.add_argument("--root", default=None)
    conf.add_argument("--plan", required=True)
    conf.add_argument("--quote", required=True)
    conf.add_argument("--quote-ref", required=True, dest="quote_ref")
    conf.set_defaults(func=_cmd_confirm)

    exe = sub.add_parser("execute", help="重验+scope+auth+一次提交")
    exe.add_argument("--token", default=os.environ.get("LFX_TOKEN", ""))
    exe.add_argument("--org", default=os.environ.get("LFX_ORG", ""))
    exe.add_argument("--plan", required=True)
    exe.add_argument("--ticket-file", default=None, dest="ticket_file")
    exe.add_argument("--ticket-json", default=None, dest="ticket_json")
    exe.add_argument("--render", required=True)
    exe.add_argument("--root", default=None)
    exe.add_argument("--timeout", type=int, default=180)
    exe.add_argument("--run", default=None,
                     help="执行卡运行标识；缺省读 DSH_RUN_ID，再缺省 default")
    exe.set_defaults(func=_cmd_execute)

    stat = sub.add_parser("status", help="唯一自动对账生产者（只读）")
    stat.add_argument("--token", default=os.environ.get("LFX_TOKEN", ""))
    stat.add_argument("--org", default=os.environ.get("LFX_ORG", ""))
    stat.add_argument("--plan", required=True)
    stat.add_argument("--task-id", default=None, dest="task_id")
    stat.add_argument("--attempt-id", default=None, dest="attempt_id")
    stat.add_argument("--root", default=None)
    stat.add_argument("--timeout", type=int, default=60)
    stat.add_argument("--watch", action="store_true", help="有界轮询并播报进度")
    stat.add_argument("--interval", type=float, default=5)
    stat.add_argument("--max-polls", type=int, default=120)
    stat.set_defaults(func=_cmd_status)

    rec = sub.add_parser("reconcile", help="只消费本 CLI status 记录")
    rec.add_argument("--plan", required=True)
    rec.add_argument("--task-id", default=None, dest="task_id")
    rec.add_argument("--attempt-id", default=None, dest="attempt_id")
    rec.add_argument("--task-status-json", default=None, dest="task_status_json")
    rec.add_argument("--task-status-file", default=None, dest="task_status_file")
    rec.add_argument("--status-record", default=None, dest="status_record")
    rec.add_argument("--root", default=None)
    rec.set_defaults(func=_cmd_reconcile)

    args = parser.parse_args(argv)
    if getattr(args, "func", None) is None:
        # 旧无子命令形式：一律要求 confirmed plan，缺计划直接拒绝。
        if "--plan" in (argv or []):
            rest = ["execute"] + list(argv or [])
            return main(rest)
        print("DENY E_PLAN_REQUIRED: 必须使用 prepare/confirm/execute/status/reconcile 子命令",
              file=sys.stderr)
        return 2
    # ★执行卡闸门（S5）：prepare/execute 都属于写通道入口，必须先 show+record 消费执行卡。
    # 只在 CLI dispatch 层校验，不进入 save_plan.prepare_save 等库函数；无 --skip-gate/环境变量绕过。
    if args.cmd in ("prepare", "execute"):
        try:
            step_gate.require_card("S5", getattr(args, "run", None))
        except step_gate.StepGateError as exc:
            print("❌ 执行卡闸门拒绝（S5）：%s" % exc, file=sys.stderr)
            return 2
    if getattr(args, "token", "") and not getattr(args, "org", ""):
        print("DENY E_CREDENTIAL: 缺少 --org", file=sys.stderr)
        return 2
    return args.func(args)


def _run_guarded(argv: Optional[list] = None) -> int:
    """统一错误出口：E_* 错误码 + 干净提示；不吞真实错误信息。"""
    try:
        return main(argv)
    except (rule_check.RuleCheckError, planlib.PlanError, ValueError) as exc:
        code = getattr(exc, "code", None) or "E_BAD_INPUT"
        print("❌ %s: %s" % (code, exc), file=sys.stderr)
        return 2
    except KeyError as exc:
        print("❌ E_BAD_INPUT: 缺少字段 %s" % exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print("❌ E_IO: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_run_guarded())
