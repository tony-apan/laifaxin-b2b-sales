#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★序列终检（激活前硬闸门）：断言序列存在且默认inactive + 12步 + 模板ID/时间正确。
用法: python3 verify_sequence.py --token <T> --org <orgId> --seq <序列id> [--allow-active]

★2026-10-23 加固（任务A-2）：
  1) 模板库按"全部模板"识别，**不再**用 `not t.get("folder")` 这类过滤——模板放进分组(folder)
     是正常用法，旧实现会把已分组模板当成不存在，导致正确序列被误判失败。
  2) 模板库为空/查询失败 → 中文报错 fail-closed（不再可能"没有模板也算通过"）。
  3) 每步必须真的绑定模板（template_ids 非空），缺绑定即失败。
  4) 校验核心抽成 `check_sequence(api, seq, allow_active=False)`，build_sequence 建完直接复用同一套逻辑。
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
import argparse
import json
import re
import subprocess
import sys

STEP_COUNT = 12
TEMPLATE_ID_RE = re.compile(r"[0-9a-f]{24}")


def _as_list(data, key="list"):
    """平台 data 可能是 list，也可能是 {list:[...]}；都不是则返回 None（=查询失败，不是"空"）。"""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        value = data.get(key)
        return value if isinstance(value, list) else None
    return None


def find_sequence(api, seq):
    """遍历 sequence-list 命中目标序列。返回 (item, error)。查询失败/不可见一律 fail-closed。"""
    for page in range(1, 6):
        data = api("sequences/sequence-list", {"current": page, "pageSize": 100, "filter": {}, "sort": {}})
        lst = _as_list(data)
        if lst is None:
            return None, "sequence-list 查询失败——无法确认序列状态，不得激活"
        for item in lst:
            if isinstance(item, dict) and str(item.get("id") or item.get("_id") or "") == seq:
                return item, None
        if len(lst) < 100:
            break
    return None, f"序列不存在/不可见: {seq}"


def sequence_status(item):
    """兼容 status(字符串启停态) 与 active 字段。"""
    status = str(item.get("status") or "").lower()
    if item.get("active") is True or str(item.get("active")) == "1":
        status = "active"
    return status


def fetch_steps(api, seq):
    """拉 step-list。返回 (steps, error)；空列表也算失败（12 步不可能为空）。"""
    data = api("sequences/step-list", {"seqId": seq, "current": 1, "pageSize": 50})
    steps = _as_list(data)
    if steps is None:
        return None, "step-list 查询失败（接口异常）——无法确认 12 步，终检不通过"
    return steps, None


def fetch_template_index(api):
    """拉邮件模板库，返回 (全部模板id集合, 页数, error)。

    ★不得按 folder 过滤：模板可以在分组里。只要平台返回了 `_id`/`id` 就计入。
    """
    template_ids = set()
    pages = 0
    for page in range(1, 9):
        data = api("mailbox/templates-list", {"current": page, "pageSize": 100, "filter": {}, "sort": {}})
        lst = _as_list(data)
        if lst is None:
            if pages == 0:
                return set(), 0, "邮件模板库查询失败（接口异常）——无法确认每步模板真实存在，终检不通过"
            break
        pages += 1
        for item in lst:
            if not isinstance(item, dict):
                continue
            tid = item.get("_id") or item.get("id") or ""
            if tid:
                template_ids.add(str(tid))
        if len(lst) < 100:
            break
    if not template_ids:
        return set(), pages, "邮件模板库为空/一个模板都没查到——无法确认每步模板真实存在，终检不通过（不得当作通过）"
    return template_ids, pages, None


def expected_wait(step_no):
    """步长铁律：step1=30分, step2=5天, step3=15天, step4-12=30天。"""
    return ("minute", 30) if step_no == 1 else ("day", 5) if step_no == 2 else ("day", 15) if step_no == 3 else ("day", 30)


def check_steps(steps, template_ids):
    """逐项校验步骤：12 步 / 每步绑定模板且 id 在模板库 / wait 正确。返回中文问题列表。"""
    issues = []
    if len(steps) != STEP_COUNT:
        issues.append(f"步骤数={len(steps)}≠{STEP_COUNT}——序列步数错乱，不得激活")
    for step in steps:
        if not isinstance(step, dict):
            issues.append(f"步骤结构异常: {step!r}")
            continue
        step_no = step.get("step")
        tids = step.get("template_ids") or []
        if not isinstance(tids, list) or not tids:
            issues.append(f"step{step_no}: 未绑定任何邮件模板（template_ids 为空）——不得激活")
        else:
            bad = [t for t in tids if not TEMPLATE_ID_RE.fullmatch(str(t)) or str(t) not in template_ids]
            if bad:
                issues.append(f"step{step_no}: 模板 id 非法或不在邮件模板库: {bad}")
        exp_mode, exp_time = expected_wait(step_no)
        if (step.get("wait_mode"), step.get("wait_time")) != (exp_mode, exp_time):
            issues.append(
                f"step{step_no}: wait配置={step.get('wait_mode')}/{step.get('wait_time')}，"
                f"应为 {exp_mode}/{exp_time}")
    return issues


def check_sequence(api, seq, allow_active=False):
    """序列终检核心（可被 build_sequence 复用）。

    api(path, payload) -> 平台响应的 data 字段（与 CLI 内 default_api 同口径）。
    返回 (ok, issues, info)；issues 全为中文；ok=False 时调用方必须 fail-closed。
    """
    item, err = find_sequence(api, seq)
    if err:
        return False, [err], {}
    status = sequence_status(item)
    if status != "inactive" and not (allow_active and status == "active"):
        return False, [f"序列 status={status or '未知'}，S11 终检默认必须 inactive"], {"status": status}
    steps, err = fetch_steps(api, seq)
    if err:
        return False, [err], {"status": status}
    template_ids, pages, err = fetch_template_index(api)
    if err:
        return False, [err], {"status": status, "steps": len(steps), "templates": 0}
    issues = check_steps(steps, template_ids)
    return (not issues), issues, {"status": status, "steps": len(steps),
                                  "templates": len(template_ids), "template_pages": pages}


def default_api(args):
    """CLI 平台调用（保持原 curl 形态：uid 必须进 header）。"""
    def api(path, payload, timeout=50):
        # LFX_GATE_WRITE
        try:
            from startup_gate import enforce_cli_startup as _lfx_gate
            _lfx_gate()
        except ImportError:
            pass
        except Exception:
            sys.stderr.write("还差一步：请先告诉我怎么称呼您、主要卖什么产品，登记后我马上继续（不是你的账号问题）。\n")
            raise SystemExit(2)
        cmd = ["curl", "-sSL", "-X", "POST", f"https://web.laifaxin.com/api/{path}",
               "-H", "Content-Type: application/json", "-H", f"accesstoken: {args.token}",
               "-H", f"uid: {args.org}", "-d", json.dumps(payload)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError):
            return {}
        try:
            return json.loads(result.stdout).get("data", {})
        except (ValueError, TypeError):
            return {}
    return api


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--org", required=True)
    ap.add_argument("--seq", required=True)
    ap.add_argument("--allow-active", action="store_true",
                    help="仅激活后复核时允许active；S11默认必须inactive")
    args = ap.parse_args(argv)

    ok, issues, info = check_sequence(default_api(args), args.seq, args.allow_active)
    for issue in issues:
        print(f"❌ {issue}")
    if not ok:
        print("❌ 终检失败——不得激活")
        return 1
    # ★保持 finalize_run 证据契约的类型化标记逐行可读（勿合并成一行）：
    #   - 「状态=inactive」用于核对未激活；「步骤数: 12」/「全部12步」用于核对步数与模板绑定
    #   - finalize_run.evidence_ok 会做 步骤数=/步骤数: 归一化，两种写法都兼容
    print(f"✅ 序列 {args.seq} 状态={info['status']}")
    print(f"步骤数: {info['steps']}")
    print(f"✅ 全部{info['steps']}步: template_ids均24hex+在邮件模板库"
          f"（模板库{info['templates']}个，含分组模板）+wait(step1=30分/step2=5天/step3=15天/step4+=30天)正确")
    return 0


if __name__ == "__main__":
    sys.exit(main())
