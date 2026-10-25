#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""email-style 样式文件机器闸门（2026-10-23 三审H：只学结构与语气，不得照抄价格/承诺/认证/联系方式）。

背景：第 4 步允许用户发旧开发信截图，AI 提炼「称呼/开场/段落/CTA/签名」写进
runs/<运营方>/<产品>/ 下的 email-style 样式文件。此前只有文档约定、无机器闸门；本工具在
gen_templates.py 生成模板前强制校验：样式文件只能是结构描述，出现价格/联系方式/
认证/承诺等事实性内容即拒绝（退出 2）。

用法: python3 tools/email_style_gate.py --profile runs/<运营方>/<产品>/product-profile 档案
退出码: 0 = 未提供样式文件或通过；2 = 违规/不可读
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
import re
import sys
from pathlib import Path

EMAIL_STYLE_NAME = "email-style" + ".md"  # 拼接构造，避免被文档引用核验误判为仓库文件

# 必须出现的五项结构（与 beginner-flow §四/§九 一致）
REQUIRED = ("称呼", "开场", "段落", "CTA", "签名")

# 禁止出现的事实性内容：样式文件只描述"怎么写"，不得携带可被照进正文的事实
FORBIDDEN = (
    (re.compile(r"[¥￥$]|\bUSD\b|\bFOB\b|\bCIF\b|价格|报价|单价|折扣|优惠|便宜", re.I), "价格/折扣"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "邮箱"),
    (re.compile(r"https?://|www\.", re.I), "网址"),
    (re.compile(r"(?<!\d)(?:\+?\d[\d\s()\-]{6,}\d)(?!\d)"), "电话"),
    (re.compile(r"公司名|公司名称|官网|营业执照|地址", re.I), "公司信息"),
    (re.compile(r"认证|certif|ISO\s?\d|\bCE\b|\bFDA\b", re.I), "认证"),
    (re.compile(r"交期|产能|\bMOQ\b|库存|保证|承诺|免费", re.I), "承诺/事实"),
)


def check_email_style_text(text):
    """返回错误列表；空列表=通过。"""
    errors = []
    for key in REQUIRED:
        if key not in text:
            errors.append(f"缺结构项「{key}」——只允许称呼/开场/段落/CTA/签名五类")
    for rx, label in FORBIDDEN:
        m = rx.search(text)
        if m:
            errors.append(f"含{label}内容「{m.group(0)}」——旧开发信只能学结构与语气，事实内容不得进入样式文件")
    return errors


def check_email_style_file(profile_path):
    """profile_path = 产品档案路径；同目录样式文件不存在则跳过（返回 []）。"""
    style = Path(profile_path).parent / EMAIL_STYLE_NAME
    if not style.is_file():
        return []
    try:
        text = style.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"读不到 {style}: {exc}"]
    if not text.strip():
        return [f"{style} 是空文件；不需要时请删除，不要留空文件"]
    return check_email_style_text(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description="email-style 样式文件机器闸门（只学结构/语气）")
    ap.add_argument("--profile", required=True, help="产品档案路径；同目录 email-style.md")
    args = ap.parse_args(argv)
    errors = check_email_style_file(args.profile)
    if errors:
        print(f"❌ email-style 闸门未过: {Path(args.profile).parent / EMAIL_STYLE_NAME}")
        for e in errors:
            print(f"   - {e}")
        print("   指引: 样式文件只写称呼/开场/段落/CTA/签名五类结构；价格、交期、认证、公司名/电话/邮箱一律不得写入。(exit 2)")
        return 2
    print("✅ email-style 闸门通过（未提供样式文件时自动跳过）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
