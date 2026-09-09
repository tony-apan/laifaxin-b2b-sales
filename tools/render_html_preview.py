#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★模板 HTML 预览（收件人视角）：把 plan 渲染成可在浏览器打开的邮件预览页。

用途：让用户直观看到"买家在邮箱里看到的样子"——钩子、加粗卖点、独立 CTA 段、
加粗回复关键词是否都到位。**纯本地渲染，不联网、不写平台**。

用法：
  python3 tools/render_html_preview.py --plan <template-plan.json> [--name Tony] [--out preview.html]
  python3 tools/render_html_preview.py --plan plan.json --rounds 1,2,4 --variants 1,3
输出：默认写到 <plan 同目录>/preview.html，并打印路径。
"""
import argparse
import html
import json
import re
from pathlib import Path

VAR_RE = re.compile(r'<code[^>]*>\{联系人:([^}]+)\}</code>')


def recipient_view(raw_html, name="John Smith"):
    """HTML → 收件人视角的段落列表（变量显示为【名称】；保留加粗位置供高亮渲染）。

    加粗标记用 \x01 ... \x02 包裹纯文本：\x01 表示"从这里开始加粗"，\x02 表示结束。
    """
    text = VAR_RE.sub(lambda m: "【" + m.group(1) + "】", raw_html or "")
    text = text.replace("【名称】", name)
    text = re.sub(r"<b>(.*?)</b>", lambda m: "\x01" + m.group(1) + "\x02", text, flags=re.S | re.I)
    text = re.sub(r"</?b>", "", text)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = html.unescape(text)
    lines = [re.sub(r"[ \t]+", " ", l).strip() for l in text.split("\n")]
    return [l for l in lines if l]


def to_paragraph_html(line):
    """把 \x01...\x02 加粗标记转成 <strong>，其余内容转义。"""
    parts = []
    bold = False
    buffer = []

    def flush():
        if buffer:
            content = html.escape("".join(buffer))
            parts.append(f"<strong>{content}</strong>" if bold else content)
            buffer.clear()

    for char in line:
        if char == "\x01":
            flush()
            bold = True
        elif char == "\x02":
            flush()
            bold = False
        else:
            buffer.append(char)
    flush()
    return "".join(parts)


PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>开发信模板预览 · 收件人视角</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 24px 16px 64px; background: #f4f5f7; color: #1c1e21;
         font: 15px/1.6 -apple-system, "Segoe UI", "Helvetica Neue", "PingFang SC", sans-serif; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .sub {{ color: #65676b; font-size: 13px; margin-bottom: 20px; }}
  .grid {{ display: grid; gap: 20px; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
           max-width: 1200px; margin: 0 auto; }}
  .card {{ background: #fff; border: 1px solid #dddfe2; border-radius: 10px; overflow: hidden;
           box-shadow: 0 1px 2px rgba(0,0,0,.06); }}
  .card-head {{ padding: 10px 14px; background: #f0f2f5; border-bottom: 1px solid #dddfe2;
                font-size: 12px; color: #606770; display: flex; justify-content: space-between; gap: 8px; }}
  .tag {{ background: #e7f3ff; color: #1877f2; border-radius: 10px; padding: 1px 8px; white-space: nowrap; }}
  .subject {{ padding: 12px 14px 0; font-weight: 600; font-size: 14px; color: #1c1e21; }}
  .body {{ padding: 10px 14px 16px; }}
  .body p {{ margin: 0 0 12px; }}
  .body p:last-child {{ margin-bottom: 0; color: #444950; }}
  .body strong {{ background: #fff3cd; padding: 0 2px; border-radius: 3px; }}
  .cta {{ border-left: 3px solid #1877f2; padding-left: 10px; }}
  .note {{ max-width: 1200px; margin: 24px auto 0; color: #65676b; font-size: 12px; }}
</style>
</head>
<body>
<h1>开发信模板预览 · 收件人视角</h1>
<div class="sub">黄色高亮 = 加粗卖点 / 回复关键词；蓝线 = 独立 CTA 段。这是买家在邮箱里看到的样子。</div>
<div class="grid">
{cards}
</div>
<div class="note">本地渲染，未连接平台；【名称】会被替换成真实客户名。</div>
</body>
</html>
"""

CARD = """  <div class="card">
    <div class="card-head"><span>{label}</span><span class="tag">{round_zh}</span></div>
    <div class="subject">{subject}</div>
    <div class="body">
{paragraphs}
    </div>
  </div>
"""


def build_card(rnd, zh, subject, angle, variant, name):
    lines = recipient_view(angle, name) + recipient_view(variant, name)
    paragraphs = []
    for index, line in enumerate(lines):
        cls = ' class="cta"' if index == len(lines) - 1 else ""
        paragraphs.append(f'      <p{cls}>{to_paragraph_html(line)}</p>')
    return CARD.format(label=html.escape(rnd), round_zh=html.escape(zh),
                       subject=html.escape(subject or ""), paragraphs="\n".join(paragraphs))


def parse_selection(value, total):
    if not value:
        return list(range(1, total + 1))
    picked = []
    for token in str(value).split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start, _, end = token.partition("-")
            picked.extend(range(int(start), int(end) + 1))
        else:
            picked.append(int(token))
    return [p for p in picked if 1 <= p <= total]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True, help="template-plan.json（含 directions/variants）")
    ap.add_argument("--name", default="John Smith", help="收件人示例名（替换【名称】）")
    ap.add_argument("--out", default="", help="输出 HTML 路径（默认 <plan目录>/preview.html）")
    ap.add_argument("--rounds", default="", help="只渲染指定轮次，如 1,2,4 或 1-3（默认全部）")
    ap.add_argument("--variants", default="", help="只渲染指定变体序号，如 1,3（默认每轮取第一个）")
    args = ap.parse_args(argv)

    plan_path = Path(args.plan)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    directions = plan.get("directions") or []
    variants = plan.get("variants") or []
    if not directions or not variants:
        print("❌ plan 缺 directions 或 variants")
        return 2

    round_idx = parse_selection(args.rounds, len(directions))
    variant_idx = parse_selection(args.variants, len(variants)) if args.variants else [1]

    cards = []
    for ri in round_idx:
        rnd, zh, subject, angle = directions[ri - 1][:4]
        for vi in variant_idx:
            cards.append(build_card(f"{rnd}-V{vi:02d}", zh, subject, angle, variants[vi - 1], args.name))

    out_path = Path(args.out) if args.out else plan_path.parent / "preview.html"
    out_path.write_text(PAGE.format(cards="\n".join(cards)), encoding="utf-8")
    print(f"✅ 已渲染 {len(cards)} 封模板预览: {out_path}")
    print(f"   浏览器打开即可查看收件人视角（本地文件，不联网）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
