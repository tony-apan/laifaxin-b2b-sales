#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★清空基础产品档案（product-list 全量 + product-delete id逐个）——用户界面"产品档案"= product-* 不是 inference-product-*
⚠️防呆（对齐 delete_all_contacts/tags/templates）: 默认 --dry-run 仅预览; 必须 --execute + --confirm "DELETE-ALL" 才真删。
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
import hashlib, json, subprocess, time, argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from approval import require_approval, stable_params_hash
from workspace_guard import preflight

CONFIRM_PHRASE = "DELETE-ALL"
ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True)
ap.add_argument("--org", required=True)
ap.add_argument("--dry-run", action="store_true", default=True, help="仅预览待删产品(★默认启用; 加 --execute 才真删)")
ap.add_argument("--execute", action="store_true", help="⚠️ 真正执行删除——必须同时提供 --org(已必填) 与 --confirm \"DELETE-ALL\"")
ap.add_argument("--approval", default="", help="账号级清空审批凭证(SX_DELETE_PRODUCTS)")
ap.add_argument("--backup-manifest", default="", help="dry-run输出/execute输入的待删ID manifest")
ap.add_argument("--user-quote", default="", help="用户当前对话明确清空原话（审批凭证中须一致）")
ap.add_argument("--confirm", default="", help=f"机器防误触短语，必须等于{CONFIRM_PHRASE}")
args = ap.parse_args()
# ★旧脚本物理封条（save_guard.require，2026-10-23）：--help 已在 parse_args 内提前返回；
# 其余任何写/推进路径（含 dry-run）一律 SystemExit，无环境变量可绕过。
# 仅防误触/防走神，仍非安全边界（可被删封条/伪造模块绕过）——见 RULES 边界声明。
try:
    from save_guard import require as _save_guard_require
    _save_guard_require()
except ImportError:
    raise SystemExit("DEPRECATED: use save_guard")

# ★P0-3 修正: store_true+default=True 会让 dry_run 恒 True → 删除分支死代码。改以 --execute 为执行闸。
if args.execute and args.confirm != CONFIRM_PHRASE:
    print(f"❌ --confirm 须等于 \"{CONFIRM_PHRASE}\"(防误删)——你给的是 {args.confirm!r}"); raise SystemExit(1)
executing = args.execute and args.confirm == CONFIRM_PHRASE

def api(path, p, t=40):
# LFX_GATE_WRITE
    try:
        from startup_gate import enforce_cli_startup as _lfx_gate
        _lfx_gate()
    except ImportError:
        pass
    except Exception as _lfx_gate_exc:
        __import__("sys").stderr.write("还差一步：请先告诉我怎么称呼您、主要卖什么产品，登记后我马上继续（不是你的账号问题）。\n")
        raise SystemExit(2)
    cmd = ["curl", "-sSL", "-X", "POST", f"https://web.laifaxin.com/api/{path}",
           "-H", "Content-Type: application/json", "-H", f"accesstoken: {args.token}",
 "-H", f"uid: {args.org}",
                          "-d", json.dumps(p)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=t, encoding="utf-8", errors="replace")
    try: return json.loads(r.stdout)
    except: return {}

allp = []
for page in range(1, 8):
    d = api("profile/product-list", {"current": page, "pageSize": 10, "filter": {}, "sort": {"create_time": -1}, "keyword": ""}).get("data", {})
    lst = d.get("list", []) if isinstance(d, dict) else []
    if not lst: break
    allp += lst
    if len(lst) < 10: break

ids = sorted(str(p.get("_id") or "") for p in allp if p.get("_id"))
org_sha = hashlib.sha256(str(args.org).encode()).hexdigest()
manifest_doc = {"org_sha256": org_sha, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "product_ids": ids,
                "snapshot_sha256": hashlib.sha256(json.dumps(ids,separators=(",",":")).encode()).hexdigest()}
if not executing and args.backup_manifest:
    Path(args.backup_manifest).write_text(json.dumps(manifest_doc,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"✅ 已输出待删manifest: {args.backup_manifest}")
if executing:
    if not args.backup_manifest or not Path(args.backup_manifest).is_file():
        print("❌ execute须带dry-run生成的 --backup-manifest"); raise SystemExit(2)
    try: supplied=json.loads(Path(args.backup_manifest).read_text(encoding="utf-8"))
    except Exception as exc: print(f"❌ manifest无效: {exc}"); raise SystemExit(2)
    if supplied != manifest_doc:
        print("❌ 当前待删产品ID与manifest不一致（清单已变化），重新dry-run确认"); raise SystemExit(2)
    project = "account:" + org_sha[:16]
    binding = {"project":project,"org_sha256":org_sha,"product_ids":ids,"snapshot_sha256":manifest_doc["snapshot_sha256"]}
    row=require_approval(args.approval,project,("SX_DELETE_PRODUCTS",),what="清空全部产品档案",expected_hash=stable_params_hash(binding))
    if " ".join(str(row.get("user_quote","")).split()) != " ".join(args.user_quote.split()):
        print("❌ --user-quote须与审批凭证原话一致"); raise SystemExit(2)
    # ★工作空间落点校验(删除前): 防"给了企业 orgId 却删掉个人空间的档案"
    preflight(args.token, args.org, what="清空全部产品档案")

print(f"产品档案: {len(allp)}")
if not allp:
    print("(无产品档案可删)"); raise SystemExit(0)
if args.dry_run and not executing:
    print("[dry-run] 待删(不删除):")
    for p in allp: print("  ", p.get("_id"), (p.get("product_name") or "")[:20])
    print(f'[dry-run] 未加 --execute,不删除。确认后请: --execute --confirm "{CONFIRM_PHRASE}"')
else:
    for p in allp:
        r = api("profile/product-delete", {"id": p.get("_id")})
        print("  删", (p.get("product_name") or "")[:16], r.get("success"))
        time.sleep(0.3)
    time.sleep(1)
    d = api("profile/product-list", {"current": 1, "pageSize": 10, "filter": {}, "sort": {"create_time": -1}, "keyword": ""}).get("data", {})
    print("剩余:", d.get("total") if isinstance(d, dict) else "?")
