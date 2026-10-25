#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""执行护栏 · save 唯一写入口（v3）。

定位声明：
  本护栏定位=防走神/跳步，不防恶意攻击。同一进程可以改写任意本地文件，
  因此 .local 下的 render/ticket/lock/ok **不是安全边界**，也不承诺防伪造；
  真正的边界是：任何拒绝路径都不得产生网络副作用（http_calls == 0）。

唯一写入口：
  * 所有真正调用 refine/company-save（以及 delete/purge）的新代码，必须走
    save_guard.save_company(...)，由它按顺序完成：
        1. auth_guard.verify / authorize（票据 + payload_hash）
        2. render_guard.check（node/task_id/params_hash/30min/fields/sha）
        3. auth_guard.begin（O_EXCL lock）
        4. 注入的 http(payload)（网络调用只在这里发生）
        5. auth_guard.commit（成功写 ok、删 lock）或 abort（失败删 lock）
  * 本模块不内置网络客户端；调用方必须把平台 HTTP 调用作为 http 注入。
    禁止在别处直接 curl/requests 调 refine/company-save；旧脚本的
    save_guard.require() 是无条件封条（无任何环境变量可绕过）。现役写工具
    （模板/序列/激活）必须用 authorize_write(action, payload, ticket) 校验并
    一次性消费 auth_guard 票据。

  两阶段消费的意义：HTTP 失败时 abort 只删 lock、不写 ok，同参数可以重试；
  HTTP 成功后才 commit 写 ok。这样既不会重复写，也不会把合法重试锁死。

CLI（只做 guard 预检，不发网络请求）：
  python3 tools/save_guard.py check --ticket-file .local/auth/ticket-<nonce>.json \
      --payload-json '{"tag_id":"12345","points_per_email":6200,"max_per_run":100}' \
      --node S5 --task <task_id> --render .local/renders/S5-<task_id>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import auth_guard  # noqa: E402
import count_guard  # noqa: E402
import render_guard  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
S5_FIELDS = render_guard.S5_FIELD_SPECS
SAVE_NODES = ("S5",)


def require(*, action: str = "save", payload: Any = None, quote: str = "",
            **_: Any) -> Dict[str, Any]:
    """旧脚本的物理封条：发送前必须调用，任何情况都 SystemExit。

    本函数没有“放行”语义，也不读取任何环境变量；它的唯一作用是让未接
    authorize_write / save_company 的旧入口在产生网络副作用之前退出。
    现役正路工具必须使用 authorize_write(action, payload, ticket)。
    """
    raise SystemExit("DEPRECATED: use save_guard")


def save_company_v2(*, payload: Any, http: Any, plan: Any = None,
                    ticket: Any = None, render_path: Optional[Any] = None,
                    root: Optional[Any] = None, auth_root: Optional[Any] = None,
                    render_root: Optional[Any] = None,
                    now: Any = None) -> Dict[str, Any]:
    """Guard V2 唯一 S5 写入口：plan/scope/uncertain 全链（§5.2/§5.3）。

    顺序固定：类型(rule_check) → 局部 alias(count) → plan 绑定 → auth 票据
    （authorize_save_plan 铸的票经 verify）→ render(S5V2) → scope O_EXCL 占位
    → auth.begin(nonce 锁) → 延迟 http factory → 持久化 attempt → 一次提交。
    拒绝路径 http_calls==0；uncertain 保留 scope+auth 锁（hold_unknown），不 abort。
    http_factory 参数名与契约一致：占位成功前不得调用。
    """
    import rule_check
    import save_plan as planlib

    auth_root = Path(auth_root if auth_root is not None else (root or ROOT))
    render_root = Path(render_root if render_root is not None else (root or ROOT))
    # B1：execute 重读 registry+audit manifest 重建依赖；伪造来源/篡改窗口或 filters
    # 必须在 auth/render/scope/transport 之前失败（E_SOURCE_STALE / E_PLAN_DEPENDENCY_CHANGED）。
    if not isinstance(plan, dict):
        return _reject("plan", "E_PLAN_REQUIRED", "S5 保存必须携带 confirmed plan")
    try:
        current_dependencies = planlib.build_dependencies(auth_root, plan)
        planlib.validate_dependencies(auth_root, plan, current_dependencies)
    except planlib.PlanError as exc:
        return _reject("plan", exc.code, exc.reason)
    try:
        count_guard.validate_plan(plan)
        if plan.get("budget_ledger") is not None:
            count_guard.verify_ledger_file(auth_root, plan)
    except count_guard.CountError as exc:
        return _reject("count", exc.code, exc.reason)
    try:
        checked = rule_check.check_save(payload, plan,
                                        dependencies=current_dependencies)
    except rule_check.RuleCheckError as exc:
        return _reject("plan", exc.code, exc.reason)

    verified = auth_guard.verify(ticket, payload, root=auth_root)
    if not verified["ok"]:
        return _reject("auth", verified.get("code", "E_AUTH_DENIED"),
                       verified.get("reason", ""), auth=verified)
    if verified.get("action") != "save":
        return _reject("auth", "E_AUTH_ACTION_MISMATCH",
                       "ticket.action=%r，需要 save" % verified.get("action"),
                       auth=verified)
    ticket = verified["ticket"]

    # render（S5V2）：params_hash 绑 wire；预算点数只从 plan 注入比对。
    params_hash = rule_check.canonical_hash(payload)
    render_result = render_guard.check(
        "S5V2", None, render_path, params=payload,
        count=checked["selectTotal"], root=render_root, now=now,
        extra_candidates={"预算点数": (plan.get("computed") or {}).get("estimated_points")})
    if not render_result["ok"]:
        return _reject("render", render_result.get("code", "E_RENDER_DENIED"),
                       render_result.get("reason", ""), render=render_result)
    effective_task = render_result["task_id"]

    scope = plan.get("query_scope") or {}
    stored_key = scope.get("query_scope_key") if isinstance(scope, dict) else None
    # 不信任 plan 自报 key：每次从实际 wire + 来源重算；排序/过滤变化必须换锁。
    canonical = rule_check.canonical_scope(
        workspace_ref=str(plan.get("project", "")),
        product_id=str(plan.get("platform_product_id", "")),
        generation_id=str(plan.get("generation_id", "")),
        selection_id=str(plan.get("selection_id", "")),
        keyword=str(payload.get("keyword", "")),
        filters=payload.get("filters", []), logic=payload.get("logic", "and"),
        sort=payload.get("selectSort", {}))
    scope_key = rule_check.scope_key(canonical)
    if stored_key and stored_key != scope_key:
        return _reject("scope", "E_SCOPE_KEY_MISMATCH",
                       "plan.query_scope_key 与实际 wire 重算值不一致，拒绝复用旧锁")
    try:
        reserved = planlib.reserve_scope(
            auth_root, query_scope_key=scope_key,
            plan_id=str(plan.get("plan_id")), revision=int(plan.get("revision") or 1))
    except planlib.PlanError as exc:
        return _reject("scope", exc.code, exc.reason)

    handle = auth_guard.begin(ticket, payload, task=effective_task, root=auth_root)
    if not handle["ok"]:
        return _reject("auth", handle.get("code", "E_AUTH_DENIED"),
                       handle.get("reason", ""), auth=handle)

    try:
        planlib.mark_attempt(
            auth_root, query_scope_key=scope_key, owner=reserved["owner"],
            attempt_id=reserved["attempt_id"], plan_id=str(plan.get("plan_id")),
            revision=int(plan.get("revision") or 1))
    except planlib.PlanError as exc:
        return _reject("scope", exc.code, exc.reason)

    if not callable(http):
        return _reject("transport", "E_NO_HTTP",
                       "save_company_v2 必须注入可调用的 http(payload)")

    try:
        http_result = http(payload)
    except Exception as exc:  # noqa: BLE001 - 提交后未知 = uncertain，保留锁
        auth_guard.hold_unknown(handle, reason=repr(exc))
        planlib.mark_uncertain(auth_root, query_scope_key=scope_key,
                               owner=reserved["owner"],
                               attempt_id=reserved["attempt_id"], reason=repr(exc))
        return {"ok": False, "stage": "http", "code": "E_SAVE_UNCERTAIN",
                "reason": repr(exc), "http_calls": 1, "scope": scope_key}

    if not isinstance(http_result, dict) or http_result.get("success") is not True:
        reason = "响应非 success"
        auth_guard.hold_unknown(handle, reason=reason)
        planlib.mark_uncertain(auth_root, query_scope_key=scope_key,
                               owner=reserved["owner"],
                               attempt_id=reserved["attempt_id"], reason=reason)
        return {"ok": False, "stage": "http", "code": "E_SAVE_UNCERTAIN",
                "reason": reason, "http_calls": 1, "scope": scope_key,
                "http_result": http_result}

    data = http_result.get("data") if isinstance(http_result.get("data"), dict) else {}
    task_id = data.get("task_id") or data.get("id") or http_result.get("task_id")
    if not task_id:
        reason = "success:true 但无任务ID → uncertain"
        auth_guard.hold_unknown(handle, reason=reason)
        planlib.mark_uncertain(auth_root, query_scope_key=scope_key,
                               owner=reserved["owner"],
                               attempt_id=reserved["attempt_id"], reason=reason)
        return {"ok": False, "stage": "http", "code": "E_SAVE_UNCERTAIN",
                "reason": reason, "http_calls": 1, "scope": scope_key,
                "http_result": http_result}

    committed = auth_guard.commit(handle)
    if not committed["ok"]:
        planlib.mark_uncertain(auth_root, query_scope_key=scope_key,
                               owner=reserved["owner"],
                               attempt_id=reserved["attempt_id"],
                               reason="commit_failed")
        return {"ok": False, "stage": "commit",
                "code": committed.get("code", "E_AUTH_COMMIT_FAILED"),
                "reason": committed.get("reason", ""), "http_calls": 1,
                "scope": scope_key, "auth": committed}

    planlib.record_accepted(auth_root, query_scope_key=scope_key,
                            owner=reserved["owner"],
                            attempt_id=reserved["attempt_id"],
                            task_id=str(task_id), response=http_result)
    return {
        "ok": True, "stage": "sent", "code": None, "reason": "",
        "http_calls": 1, "http_result": http_result, "task_id": str(task_id),
        "render_sha256": render_result["render_sha256"],
        "render_path": render_result["render_path"],
        "fields": render_result.get("fields", {}),
        "report_text": (render_result.get("output") or "") + chr(10) +
                       render_guard.report_suffix(render_result["render_sha256"]),
        "scope": scope_key, "auth": committed,
    }


def _reject(stage: str, code: str, reason: str, **extra: Any) -> Dict[str, Any]:
    result = {
        "ok": False,
        "stage": stage,
        "code": code,
        "reason": reason,
        "http_calls": 0,
    }
    result.update(extra)
    return result


def ticket_from_argv(argv: Optional[Sequence[str]] = None) -> Optional[str]:
    """从命令行读取 --auth-ticket（无 argparse 的旧创建脚本共用）。"""
    values = list(sys.argv if argv is None else argv)
    for index, value in enumerate(values):
        if value == "--auth-ticket" and index + 1 < len(values):
            return values[index + 1]
        if value.startswith("--auth-ticket="):
            return value.split("=", 1)[1]
    return None


def authorize_write(*, action: str, payload: Any, ticket: Any = None,
                    root: Optional[Any] = None) -> Dict[str, Any]:
    """现役写操作的真实授权闸门（与旧脚本封条 require 语义分离）。

    复用 auth_guard 票据：ticket.action 必须与 action 一致、payload_hash 必须与
    payload 一致、O_EXCL 只消费一次。不读取任何环境变量，无票/票不符/二次消费
    一律拒绝；拒绝路径不产生网络副作用（本函数根本不发网络请求）。
    """
    if ticket is None:
        return _reject("auth", "E_AUTH_NO_TICKET", "缺少授权票据（--auth-ticket）")
    if isinstance(ticket, str) and ticket.lstrip().startswith("{"):
        try:
            ticket = json.loads(ticket)
        except (TypeError, ValueError) as exc:
            return _reject("auth", "E_AUTH_BAD_TICKET",
                           "ticket JSON 解析失败: " + str(exc))
    verified = auth_guard.verify(ticket, payload, root=root)
    if not verified["ok"]:
        return _reject("auth", verified.get("code", "E_AUTH_DENIED"),
                       verified.get("reason", ""), auth=verified)
    if verified.get("action") != action:
        return _reject("auth", "E_AUTH_ACTION_MISMATCH",
                       "ticket.action={0!r}，本次 action={1!r}".format(
                           verified.get("action"), action), auth=verified)
    handle = auth_guard.begin(ticket, payload, root=root)
    if not handle["ok"]:
        return _reject("auth", handle.get("code", "E_AUTH_DENIED"),
                       handle.get("reason", ""), auth=handle)
    committed = auth_guard.commit(handle)
    if not committed["ok"]:
        return _reject("auth", committed.get("code", "E_AUTH_COMMIT_FAILED"),
                       committed.get("reason", ""), auth=committed)
    return {
        "ok": True,
        "stage": "authorized",
        "code": None,
        "reason": "",
        "http_calls": 0,
        "action": action,
        "payload_hash": verified["payload_hash"],
        "nonce": verified["ticket"]["nonce"],
        "ticket_path": verified["ticket_path"],
        "auth": committed,
    }


def save_company(*, payload: Any, http: Any, ticket: Any = None,
                 action: str = "save", quote: str = "", task: Optional[str] = None,
                 node: str = "S5", render_path: Optional[Any] = None,
                 require: Optional[Any] = None, fields: Any = None,
                 operator: Optional[str] = None, product: Optional[str] = None,
                 seed: Optional[str] = None,
                 root: Optional[Any] = None, auth_root: Optional[Any] = None,
                 render_root: Optional[Any] = None,
                 now: Any = None) -> Dict[str, Any]:
    """唯一允许触发平台写操作的函数；HTTP 由调用方以 http(payload) 注入。

    count 不再由调用方传入：必须从 payload["count"] 派生，避免同一 payload
    换 count 伪造出新 task_id 后重复保存。
    """
    auth_root = auth_root if auth_root is not None else root
    render_root = render_root if render_root is not None else root
    effective_task = task
    payload_count = payload.get("count") if isinstance(payload, dict) else None
    if node not in SAVE_NODES:
        return _reject("render", "E_RENDER_NO_SPECS",
                       "save_company 只允许 node=S5，收到 {0!r}".format(node))
    pre_render = None

    # 1) 授权：有票先验票；无票则先 authorize（真正消费留到 HTTP 之前）。
    if ticket is None:
        if not action or not quote:
            return _reject("auth", "E_AUTH_NO_ACTION", "缺少 action/quote")
        # 只有代词（这批/全部…）的 quote 需要 render 里的明确对象。此时先做一次
        # 纯本地 render 预读（无网络副作用），把 fields 交给 authorize，避免误拒。
        if (fields is None and render_path is not None
                and auth_guard.needs_render_fields(quote)):
            pre_render = render_guard.check(
                node, require, render_path, params=payload, task=effective_task,
                operator=operator, product=product, seed=seed,
                count=payload_count, root=render_root, now=now)
            if not pre_render["ok"]:
                return _reject("render", pre_render.get("code", "E_RENDER_DENIED"),
                               pre_render.get("reason", ""), render=pre_render)
            fields = pre_render.get("fields", {})
        issued = auth_guard.authorize(action, quote, payload, task=task,
                                      fields=fields, root=auth_root)
        if not issued["ok"]:
            return _reject("auth", issued.get("code", "E_AUTH_DENIED"),
                           issued.get("reason", ""), auth=issued)
        ticket = issued["ticket"]
        if effective_task is None:
            effective_task = issued.get("task")
    else:
        verified = auth_guard.verify(ticket, payload, task=task, root=auth_root)
        if not verified["ok"]:
            return _reject("auth", verified.get("code", "E_AUTH_DENIED"),
                           verified.get("reason", ""), auth=verified)
        if verified.get("action") != action:
            return _reject("auth", "E_AUTH_ACTION_MISMATCH",
                           "ticket.action={0!r}，本次 action={1!r}".format(
                               verified.get("action"), action), auth=verified)
        if effective_task is None:
            effective_task = verified.get("task")

    # 2) render：结构化校验 + task_id 派生 + 双新鲜度 + 字段值与 payload 比对。
    #    代词场景已在上方预读通过，直接复用，避免重复校验。
    render_result = pre_render if pre_render is not None else render_guard.check(
        node, require, render_path, params=payload, task=effective_task,
        operator=operator, product=product, seed=seed,
        count=payload_count, root=render_root, now=now)
    if not render_result["ok"]:
        return _reject("render", render_result.get("code", "E_RENDER_DENIED"),
                       render_result.get("reason", ""), render=render_result)

    # render 派生出的 task_id 是本次操作唯一合法的一次性键。
    if effective_task is None:
        effective_task = render_result["task_id"]

    if not callable(http):
        return _reject("transport", "E_NO_HTTP",
                       "save_company 必须注入可调用的 http(payload)")

    # 3) 原子占位：同 nonce/同 task 只能有一个进入 HTTP。
    handle = auth_guard.begin(ticket, payload, task=effective_task,
                              root=auth_root)
    if not handle["ok"]:
        return _reject("auth", handle.get("code", "E_AUTH_DENIED"),
                       handle.get("reason", ""), auth=handle)

    # 4) 唯一网络副作用。
    try:
        http_result = http(payload)
    except Exception as exc:  # noqa: BLE001 - 必须 abort 后才能让调用方重试
        aborted = auth_guard.abort(handle, reason=repr(exc))
        return {
            "ok": False,
            "stage": "http",
            "code": "E_HTTP_FAILED",
            "reason": repr(exc),
            "http_calls": 1,
            "aborted": aborted,
        }

    # 5) HTTP 成功才写 ok 并删 lock。
    committed = auth_guard.commit(handle)
    if not committed["ok"]:
        return {
            "ok": False,
            "stage": "commit",
            "code": committed.get("code", "E_AUTH_COMMIT_FAILED"),
            "reason": committed.get("reason", ""),
            "http_calls": 1,
            "http_result": http_result,
            "auth": committed,
        }
    output = render_result.get("output")
    report_text = None
    if isinstance(output, str) and output:
        report_text = output + "\n" + render_guard.report_suffix(
            render_result["render_sha256"])
    return {
        "ok": True,
        "stage": "sent",
        "code": None,
        "reason": "",
        "http_calls": 1,
        "http_result": http_result,
        "task_id": effective_task,
        "render_sha256": render_result["render_sha256"],
        "render_path": render_result["render_path"],
        "fields": render_result.get("fields", {}),
        "report_text": report_text,
        "auth": committed,
    }


def _load_json_arg(json_text: Optional[str], file_path: Optional[str],
                   default: Any = None) -> Any:
    if json_text is not None and file_path is not None:
        raise ValueError("--json 与 --file 只能二选一")
    if file_path is not None:
        return json.loads(Path(file_path).read_text(encoding="utf-8"))
    if json_text is not None:
        return json.loads(json_text)
    return default


def _deny(result: Dict[str, Any]) -> int:
    code = result.get("code")
    print("DENY " + str(code) + ": " + str(result.get("reason")), file=sys.stderr)
    return 3 if code == "E_AUTH_REUSED" else 2


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="save 唯一写入口 guard 预检（v3）")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check", help="只预检 guard，不发送 HTTP")
    p.add_argument("--ticket-json", default=None)
    p.add_argument("--ticket-file", default=None)
    p.add_argument("--payload-json", default=None)
    p.add_argument("--payload-file", default=None)
    p.add_argument("--action", default="save")
    p.add_argument("--quote", default="")
    p.add_argument("--fields-json", default=None)
    p.add_argument("--fields-file", default=None)
    p.add_argument("--task", default=None)
    p.add_argument("--node", default="S5")
    p.add_argument("--render", default=None)
    p.add_argument("--require", default="")
    p.add_argument("--operator", default=None)
    p.add_argument("--product", default=None)
    p.add_argument("--seed", default=None)
    p.add_argument("--count", type=int, default=None)
    p.add_argument("--root", default=None)
    p.add_argument("--consume", action="store_true",
                   help="预检通过后消费 ticket（仍不发 HTTP）")
    args = parser.parse_args(argv)

    try:
        payload = _load_json_arg(args.payload_json, args.payload_file, default={})
        fields = _load_json_arg(args.fields_json, args.fields_file, default=None)
    except Exception as exc:
        print("DENY E_BAD_JSON: " + str(exc), file=sys.stderr)
        return 2

    ticket = None
    if args.ticket_json is not None or args.ticket_file is not None:
        try:
            ticket = _load_json_arg(args.ticket_json, args.ticket_file, default=None)
        except Exception as exc:
            print("DENY E_AUTH_BAD_TICKET: " + str(exc), file=sys.stderr)
            return 2
    if ticket is None:
        result = auth_guard.authorize(args.action, args.quote, payload,
                                      task=args.task, fields=fields,
                                      root=args.root)
        if not result["ok"]:
            return _deny(result)
        ticket = result["ticket"]
    else:
        verified = auth_guard.verify(ticket, payload, task=args.task,
                                     root=args.root)
        if not verified["ok"]:
            return _deny(verified)
        if not args.task:
            args.task = verified.get("task")

    render = render_guard.check(
        args.node, args.require or None, args.render, params=payload,
        task=args.task, operator=args.operator, product=args.product,
        seed=args.seed, count=args.count, root=args.root)
    if not render["ok"]:
        return _deny(render)
    if not args.task:
        args.task = render["task_id"]

    if args.consume:
        handle = auth_guard.begin(ticket, payload, task=args.task, root=args.root)
        if not handle["ok"]:
            return _deny(handle)
        committed = auth_guard.commit(handle)
        if not committed["ok"]:
            return _deny(committed)
    print("OK task_id={0} render_sha={1} http_calls=0".format(
        args.task, render["sha12"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
