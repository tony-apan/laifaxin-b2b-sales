#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""保存进度播报生成器（S6）：给用户看的一行进度，不联网、不写盘。

生成可信计数及显式提供的估时；点数仅在调用方提供可信数据时显示。
"""
import argparse
import math


def _count(value):
    """只接受平台真实返回的非负整数（bool 不算整数）。"""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def format_progress(saved, total, points=None, elapsed_s=None, eta_s=None):
    """返回一行进度；elapsed_s 仅为兼容保留，不用于估时。"""
    if not _count(saved) or not _count(total) or total == 0:
        return "进度：正在保存…（公司进度未知；您不用操作）"
    parts = ["已存 %d/%d 家" % (saved, total)]
    if saved <= total:
        parts[0] += "（%d%%）" % (saved * 100 // total)
    else:
        parts.append("平台计数超过总数，等待核实")
    if _count(points):
        parts.append("已用 %d 点" % points)
    try:
        if (not isinstance(eta_s, bool) and isinstance(eta_s, (int, float))
                and math.isfinite(eta_s) and eta_s > 0 and 0 < saved < total):
            parts.append("预计还要 %d 分钟" % max(1, math.ceil(eta_s / 60)))
    except OverflowError:
        pass
    return "进度：" + " · ".join(parts) + "（您不用操作）"

def main(argv=None):
    ap = argparse.ArgumentParser(description="生成一行保存进度")
    ap.add_argument("--saved", type=int, default=0)
    ap.add_argument("--total", type=int, default=0)
    ap.add_argument("--points", type=int, default=None)
    ap.add_argument("--elapsed", default=None, help="已停用；请改用 --eta-seconds")
    ap.add_argument("--eta-seconds", type=float, default=None,
                    help="剩余时间（秒），必须来自外部可信观测估算")
    args = ap.parse_args(argv)
    if args.elapsed is not None:
        ap.error("--elapsed 已停用；请使用 --eta-seconds 提供可信估算")
    if args.eta_seconds is not None and (not math.isfinite(args.eta_seconds) or args.eta_seconds < 0):
        ap.error("--eta-seconds 必须是有限非负秒数")
    print(format_progress(args.saved, args.total, args.points, eta_s=args.eta_seconds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
