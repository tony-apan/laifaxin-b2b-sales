#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★模板渲染预览：把 HTML 转成"收件人看到的邮件视图"（非源码）。
用法: python3 render_preview.py --html "<p>Hi <code...>{联系人:名称}</code>...</p>" [--示例名 John]
输出: 纯文本邮件视图（去掉标签, 变量显示在 {显示名}, 关键词高亮标记）
"""
import re, argparse, html as htmlmod
ap=argparse.ArgumentParser(); ap.add_argument("--html",required=True); ap.add_argument("--name",default="John Smith")
args=ap.parse_args()
# 1. 提取文本（去标签）
def textify(h):
    # 变量code → 占位符
    h=re.sub(r'<code[^>]*>\{联系人:([^}]+)\}</code>', lambda m:'【'+m.group(1)+'】', h)
    h=re.sub(r'<[^>]+>','\n',h)
    h=htmlmod.unescape(h)
    lines=[l.strip() for l in h.split("\n") if l.strip()]
    return lines
lines=textify(args.html)
print("📧 收件人视角预览（渲染效果）:")
print("─"*46)
for l in lines:
    l=l.replace("【名称】",args.name)
    # 高亮: 回复词/CTA 加 **
    if l.upper().isupper() and len(l)<20: l=f"🟡 {l}"
    print("  "+l)
print("─"*46)
print("注: 黄色=回复关键词; 【名称】=客户名会被真实替换")
