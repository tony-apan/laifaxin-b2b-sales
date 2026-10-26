# -*- coding: utf-8 -*-
"""模板批次选取（单一真源）：从 templates-list 的条目里挑出"本批模板"。

★2026-10-25 真机 S8 阻断：templates-list 会把「分组」本身也列出来，
  而 gen_templates.ensure_folder 用 --prefix 给分组命名（分组名 == 模板名前缀），
  旧逻辑只看 name.startswith(prefix)，把分组当成了第 49 个模板 → 数量校验恒失败。
  抓取到的真实字段（nuc 实测）：
    · 分组条目：name="英语-烘焙-", folder=True, foid="0"
    · 组内模板：name="英语-烘焙-R01-初次接触-V01-GL", folder=False, foid=<分组id>
    · 未分组模板：folder=False, foid="0"
  因此「分组容器」的判定必须是「folder=True 且 foid 为空/0 且 name 恰等于前缀」，
  不能粗暴跳过所有 folder=True（历史回归 test_template_folder_scope 已锁死：组内模板必须计入）。
"""


def is_folder_container(item, prefix):
    """templates-list 里的「分组」本身（不是模板）。"""
    if not isinstance(item, dict) or item.get("folder") is not True:
        return False
    foid = str(item.get("foid", "")).strip()
    if foid not in ("", "0"):
        return False
    return (item.get("name") or "").strip() == (prefix or "").strip()


def collect_batch(items, prefix, limit):
    """按名称前缀收集本批模板（分组/未分组都计入），排除分组容器本身。返回 [{name,id}]。"""
    out = []
    prefix = (prefix or "").strip()
    if not prefix or limit <= 0:
        return out
    for t in items or []:
        if not isinstance(t, dict) or is_folder_container(t, prefix):
            continue
        nm = t.get("name") or ""
        if not isinstance(nm, str) or not nm.startswith(prefix):
            continue
        out.append({"name": nm, "id": t.get("_id")})
        if len(out) >= limit:
            break
    return out
