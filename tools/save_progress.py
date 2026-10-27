#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""保存进度播报生成器（S6）：给用户看的一行进度，不联网、不写盘。

用户实测反馈：保存期间平台只显示 running 0/9560，AI 没有自动报进度。
本工具把「已存/总数/已用点/预计剩余」压成一行中文，AI 每 5–10 秒调用一次即可。
"""
import argparse
import math


def format_progress(saved, total, points=None, elapsed_s=None):
    """返回一行用户可读进度；参数异常时退化为不编造数字。"""
    try:
        saved = max(0, int(saved))
        total = max(0, int(total))
    except (TypeError, ValueError):
        return "进度：正在保存…（平台暂未返回可读数字）"
    if total <= 0:
        return "进度：正在保存…（平台暂未返回可读数字）"
    saved = min(saved, total)
    pct = int(saved * 100 / total) if total else 0
    parts = ["已存 %d/%d 家（%d%%）" % (saved, total, pct)]
    if points is not None:
        try:
            parts.append("已用 %d 点" % max(0, int(points)))
        except (TypeError, ValueError):
            pass
    if elapsed_s and saved > 0:
        try:
            remaining = max(0.0, float(elapsed_s) * (total - saved) / saved)
            minutes = int(math.ceil(remaining / 60.0))
            parts.append("预计还要 %d 分钟" % minutes if minutes > 0 else "快好了")
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    return "进度：" + " · ".join(parts) + "（您不用操作）"


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成一行保存进度")
    ap.add_argument("--saved", type=int, default=0)
    ap.add_argument("--total", type=int, default=0)
    ap.add_argument("--points", type=int, default=None)
    ap.add_argument("--elapsed", type=float, default=None)
    args = ap.parse_args(argv)
    print(format_progress(args.saved, args.total, args.points, args.elapsed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
