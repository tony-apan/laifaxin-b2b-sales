#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 时序守卫：等联系人保存任务 status:finished + 校验标签联系人>0，才可 contact-add 加序列。
用法: python3 wait_save_done.py --token <TOKEN> --org <orgId> --task <保存任务id> --tag <联系人标签id> --record runs/<operator_key>/<product_key>/operation-record.md --timeout 900
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
import json, subprocess, sys, time, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_run_state import read_meta, require_state, update_frontmatter

ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True)
ap.add_argument("--org", required=True)
ap.add_argument("--task", required=True, help="refine/company-save 返回的任务id")
ap.add_argument("--tag", required=True, help="联系人标签id（contact tag）")
ap.add_argument("--record", required=True, help="项目operation-record；finished+标签>0后推进S6,next=S7")
ap.add_argument("--timeout", type=int, default=900, help="最大等待秒数")
args = ap.parse_args()
# ★旧脚本物理封条（save_guard.require，2026-10-23）：--help 已在 parse_args 内提前返回；
# 其余任何写/推进路径（含 dry-run）一律 SystemExit，无环境变量可绕过。
# 仅防误触/防走神，仍非安全边界（可被删封条/伪造模块绕过）——见 RULES 边界声明。
try:
    from save_guard import require as _save_guard_require
    _save_guard_require()
except ImportError:
    raise SystemExit("DEPRECATED: use save_guard")
try: require_state(args.record, ("S5",))
except ValueError as exc: print(f"❌ {exc}"); sys.exit(4)
rec = read_meta(args.record)
if rec.get("save_task_id", "") != args.task or rec.get("contact_tag_id", "") != args.tag:
    print("❌ --task/--tag 与 operation-record 中本次保存任务/联系人标签不一致——拒绝用历史任务或其他标签推进S6")
    sys.exit(4)

def api(path, payload, timeout=40):
# LFX_GATE_WRITE
    try:
        from startup_gate import enforce_cli_startup as _lfx_gate
        _lfx_gate()
    except ImportError:
        pass
    except Exception as _lfx_gate_exc:
        __import__("sys").stderr.write("还差一步：请先告诉我怎么称呼您、主要卖什么产品，登记后我马上继续（不是你的账号问题）。\n")
        raise SystemExit(2)
    cmd = ["curl","-sSL","-X","POST",f"https://web.laifaxin.com/api/{path}",
           "-H","Content-Type: application/json","-H",f"accesstoken: {args.token}",
           "-H", f"uid: {args.org}","-d",json.dumps(payload)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    try: return json.loads(r.stdout)
    except: return {}

start = time.time()
status = ""
while time.time() - start < args.timeout:
    d = api("operation/backend-task-status", {"type":"cluesSave","id":args.task}).get("data",{})
    status = d.get("status","")
    contact_save = d.get("contactSaveCount")
    if status == "finished":
        print(f"✅ 保存任务 finished: contactSaveCount={contact_save}")
        break
    print(f"⏳ 等待保存任务... status:{status} fin:{d.get('finished')}/{d.get('total')} contactSave:{contact_save}", flush=True)
    time.sleep(10)
else:
    print(f"❌ 超时({args.timeout}s)仍 {status}，禁止 contact-add"); sys.exit(1)

# 校验标签联系人>0（★ISS-52: 按标签过滤须 filters 数组, filter.tags 返全库假通过）
for i in range(6):
    d = api("contacts/contacts/show", {"current":1,"pageSize":10,"filters":[{"property":"tags","operator":"include","value":args.tag,"values":[args.tag],"valueType":"select"}],"sort":{}})
    data = d.get("data")
    if data is not None:
        try: n = int(data.get("total")) if isinstance(data, dict) else int(data)
        except (TypeError, ValueError, AttributeError): n = None  # ★形状异常(间歇空)→重试,勿裸崩(对齐 contact_add)
        if n and n > 0:
            print(f"✅ 标签 {args.tag} 联系人={n} >0 → 可以 contact-add")
            update_frontmatter(args.record, {"status": "S6", "next_state": "S7", "updated": time.strftime("%Y-%m-%d")}, expected_states=("S5",))
            print(f"✅ 运行状态已推进: {args.record} → S6 (next=S7)")
            sys.exit(0)
        print(f"⚠️ 标签 {args.tag} 联系人={n}，仍为空（可能去重无新增），重试中...")
    time.sleep(8)
print("❌ 无法确认标签联系人>0（这是已知问题: 接口偶发抽风 平台接口间歇空(已知)——等 5-10 分钟重跑本命令即可,无需改动任何东西）; 禁止 contact-add"); sys.exit(1)
