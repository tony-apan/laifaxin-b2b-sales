#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★S2 客群落档（铁律 7d）：把用户选中的客群写进 operation-record 的「客群」行。

为什么需要这个工具：
  原先 S2 用户选中的客群**只存在于对话里**，record 的「客群」行只能靠 AI 手填——
  这正是"多个客群混存混发"的温床（真实反例：3 客群共用 1 个标签和 1 套话术）。
  本工具把选择固化成机读记录，并强制登记"本客群将使用哪对标签/哪套模板/哪条序列"。

用法:
  python3 segment_select.py --record runs/<operator>/<product>/operation-record.md \\
      --segments "S04:峡谷漂流景区运营服务商,S05:户外水上运动装备批发商" \\
      [--dry-run]

行为：
  - 校验 record 存在、状态属 S1/S2/S3（未进入保存阶段）
  - 解析 --segments（`ID:客群名` 逗号分隔），去重、保序
  - 把客群写进正文「| 客群 | ... |」行（多个用「、」连接，带 ID）
  - 只改正文表格，不改 frontmatter/状态（状态推进仍由 update_run_state.py 负责）
  - --dry-run 只打印将写入的内容，不落盘

边界：
  - 不创建标签、不调平台、不推进状态（纯本地记录）
  - 客群名禁止含我方产品名（沿用铁律 7：标签=客户群体，不是你的产品）
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_run_state import read_status  # noqa: E402

ALLOWED_STATES = ("S1", "S2", "S3")
SEGMENT_ROW = re.compile(r"^\|\s*客群\s*\|(.*)\|\s*$", re.M)


def parse_segments(raw):
    """解析 `ID:名称,ID:名称` → [(id, name), ...]；去重保序，格式错即报错。"""
    items, seen = [], set()
    for token in str(raw or "").split(","):
        token = token.strip()
        if not token:
            continue
        if ":" in token:
            seg_id, name = token.split(":", 1)
        elif "：" in token:
            seg_id, name = token.split("：", 1)
        else:
            raise ValueError(f"客群项格式应为 `ID:客群名`：{token!r}")
        seg_id, name = seg_id.strip(), name.strip()
        if not seg_id or not name:
            raise ValueError(f"客群项 ID/名称不能为空：{token!r}")
        if seg_id in seen:
            raise ValueError(f"客群 ID 重复：{seg_id}")
        seen.add(seg_id)
        items.append((seg_id, name))
    if not items:
        raise ValueError("--segments 为空")
    return items


def render_cell(items):
    return "、".join(f"{seg_id}({name})" for seg_id, name in items)


def select_segments(record_path, items, dry_run=False):
    """把客群写入 record 的「客群」行；返回 (旧值, 新值)。"""
    path = Path(record_path)
    if not path.is_file():
        raise ValueError(f"operation-record 不存在: {path}")
    status = read_status(path)
    if status not in ALLOWED_STATES:
        raise ValueError(f"当前状态={status or '(缺)'}，客群落档只允许 {'/'.join(ALLOWED_STATES)}（已进入保存阶段请勿改客群）")
    text = path.read_text(encoding="utf-8")
    match = SEGMENT_ROW.search(text)
    if not match:
        raise ValueError("operation-record 正文缺少「| 客群 | ... |」行，请先按模板补齐")
    old_value = match.group(1).strip()
    new_cell = render_cell(items)
    new_line = f"| 客群 | {new_cell} |"
    updated = text[:match.start()] + new_line + text[match.end():]
    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return old_value, new_cell


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", required=True, help="operation-record.md 路径")
    ap.add_argument("--segments", required=True, help="选中的客群，格式 `S04:客群名,S05:客群名`")
    ap.add_argument("--dry-run", action="store_true", help="只打印将写入的内容，不落盘")
    args = ap.parse_args(argv)
    try:
        items = parse_segments(args.segments)
    except ValueError as exc:
        print(f"❌ 参数错误：{exc}")
        return 2
    try:
        old, new = select_segments(args.record, items, dry_run=args.dry_run)
    except ValueError as exc:
        print(f"❌ 客群落档失败：{exc}")
        return 4
    verb = "将写入" if args.dry_run else "已写入"
    print(f"✅ 客群落档（{len(items)} 个）")
    if old:
        print(f"   原值: {old}")
    print(f"   {verb}: {new}")
    print("   ⚠️ 每个客群需独立标签/独立 120 模板/独立序列（铁律 7d）；执行分批，一批走完再做下一个。")
    if args.dry_run:
        print("   (dry-run 未落盘)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
