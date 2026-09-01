#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动化找70%临界点（三页滑动平均 + 50页跳 + 逐页精确 + 跌破往前）
用法:
  python3 find_critical.py --query <seed-domain> --token $TOKEN --org <orgId> \
    --match-words "水上/户外/..." [--exclude-words "摩托/服装/..."] \
    --start 1 --end 1000 --threshold 70 --step 50

逻辑（固化自 threshold-method.md）:
  1. 阶段1: 50页跳全局初筛 (工具)
  2. 阶段2: 三页滑动平均判定每页达标(<70%破)
  3. 阶段3: 临界附近逐页精确 (从粗到细)
  4. 跌破 70% 就往前找, 不看后面
"""
import json, subprocess, argparse, time

def fetch(page, keyword, token, org):
    p = {"keyword": keyword, "current": page, "pageSize": 10, "filters": [], "logic": "and"}
    cmd = ["curl","-sSL","-X","POST",f"https://web.laifaxin.com/api/refine/company-list?uid={org}",
           "-H","Content-Type: application/json","-H",f"accesstoken: {token}","-d",json.dumps(p)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return json.loads(r.stdout).get("data", {})
    except Exception:
        return {"list": []}

def hit(text, words):
    t = text.lower()
    return any(w in t for w in words)

def page_ratio(page, keyword, token, org, match_words, exclude_words):
    d = fetch(page, keyword, token, org)
    lst = d.get("list", [])
    if not lst:
        return None
    match = 0
    for c in lst:
        name = c.get("company_name","") or ""
        zh = c.get("summary_zh","") or ""
        en = c.get("summary_en","") or ""
        text = f"{name} {zh} {en}"
        # 排除词一票否决（若命中且无匹配词则不算；命中排除词的即使有匹配词也谨慎——按人工标准）
        if hit(text.lower(), exclude_words):
            continue
        if hit(text.lower(), match_words):
            match += 1
    return (match, len(lst), round(match/len(lst)*100))

def sliding_avg(values, window=3):
    """三页滑动平均"""
    avg = []
    for i in range(len(values)):
        lo = max(0, i-window//2)
        hi = min(len(values), i+window//2+1)
        seg = [v for v in values[lo:hi] if v is not None]
        avg.append(round(sum(seg)/len(seg)) if seg else None)
    return avg

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--token", required=True)
    ap.add_argument("--org", required=True)
    ap.add_argument("--match-words", required=True, help="可能采购的宽词")
    ap.add_argument("--exclude-words", default="摩托,moto,服装,枪械,马术,家居,器械,媒体,杂志,评论,餐厅,餐饮,战术,water treatment,安全设备,医学")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=1000)
    ap.add_argument("--step", type=int, default=50)
    ap.add_argument("--threshold", type=int, default=70)
    args = ap.parse_args()
    mw = [w.strip().lower() for w in args.match_words.split(",") if w.strip()]
    ew = [w.strip().lower() for w in args.exclude_words.split(",") if w.strip()]

    print(f"# 种子:{args.query} | 找{args.threshold}%临界 | 50页跳({args.step})")

    # 阶段1: 50页跳
    pages = list(range(args.start, args.end+1, args.step))
    if pages[-1] != args.end: pages.append(args.end)
    ratios = {}
    for p in pages:
        r = page_ratio(p, args.query, args.token, args.org, mw, ew)
        if r:
            ratios[p] = r
            print(f"  {p}页: {r[0]}/{r[1]} = {r[2]}%")

    # 阶段2: 三页平均，找首跌破
    ordered = sorted(ratios.keys())
    print("\n# 三页滑动平均:")
    first_break = None
    for i, p in enumerate(ordered):
        window = []
        for j in range(max(0,i-1), min(len(ordered), i+2)):
            window.append(ratios[ordered[j]][2])
        avg = round(sum(window)/len(window))
        print(f"  {p}页 平均={avg}%")
        if avg < args.threshold and first_break is None:
            first_break = p

    # 阶段3: 临界附近逐页精确（从first_break往前）
    print(f"\n# 首跌破(3页平均): 第{first_break}页")
    print("# 往前逐页精确（1页精调）:")
    if first_break:
        # 从 first_break-1 往前找，逐页
        for p in range(first_break-1, max(args.start, first_break-8), -1):
            r = page_ratio(p, args.query, args.token, args.org, mw, ew)
            if r:
                print(f"  {p}页: {r[0]}/{r[1]} = {r[2]}%")

if __name__ == "__main__":
    main()
