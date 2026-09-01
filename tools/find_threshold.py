#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
找 70% 临界点工具（★从前往后精确找"最后一张≥70%的页"）
用法:
  python3 find_threshold.py --query <seed-domain> --token $TOKEN --org <orgId> \
    --match-words "raft,inflatable,kayak,..." --start 100 --end 500 --threshold 70

逻辑（对抗审查完善）:
  1. 从 start 逐页往前/向后扫，记录每页匹配率
  2. 70% 临界点 = 最后一张 >= 70% 的页（之前全保存），即 high 侧不达标的前一张
  3. 用【二分】在"达标区(低页)"和"不达标区(高页)"之间逼近，再【线性微调】到精确临界页
  4. ⚠️ 只往前看，不看已经跌破70%的页后面
使用 classify 复用 audit 的语义匹配词库，但【必须人工读描述复核】（L-20/21/22）
"""
import json, subprocess, sys

def fetch(page, keyword, token, org, page_size=10):
    p = {"keyword": keyword, "current": page, "pageSize": page_size, "filters": [], "logic": "and"}
    cmd = ["curl","-sSL","-X","POST",f"https://web.laifaxin.com/api/refine/company-list?uid={org}",
           "-H","Content-Type: application/json","-H",f"accesstoken: {token}","-d",json.dumps(p)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return json.loads(r.stdout).get("data", {})
    except Exception:
        return {"list": []}

def keywords_in(text, words):
    t = (text or "").lower()
    return [w for w in words if w in t]

def page_ratio(page, keyword, token, org, words, rejects=None):
    """返回 (匹配数, 总数, 匹配率%)"""
    d = fetch(page, keyword, token, org)
    lst = d.get("list", [])
    if not lst:
        return (0, 0, 0)
    match = 0
    rejects = rejects or ["media","magazine","magazin","review","blog","news","杂志","媒体","评测","目录","content publisher"]
    for c in lst:
        name = c.get("company_name","") or ""
        zh = c.get("summary_zh","") or ""
        en = c.get("summary_en","") or ""
        text = f"{name} {zh} {en}".lower()
        # 命中产品词 = 匹配
        if keywords_in(text, words):
            # 但媒体/目录 排除
            if any(r in text for r in rejects):
                continue
            match += 1
    return (match, len(lst), round(match/len(lst)*100))

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--token", required=True)
    ap.add_argument("--org", required=True)
    ap.add_argument("--match-words", required=True)
    ap.add_argument("--start", type=int, default=100, help="从这开始（已知达标低页）")
    ap.add_argument("--end", type=int, default=500, help="到这结束（已知不达标高页）")
    ap.add_argument("--threshold", type=int, default=70)
    args = ap.parse_args()
    words = [w.strip().lower() for w in args.match_words.split(",") if w.strip()]

    print(f"# 种子:{args.query} | 找 {args.threshold}% 临界点（{args.start}→{args.end}）")
    print("# 二分逼近：达标区(低) vs 不达标区(高)")

    lo, hi = args.start, args.end
    # 先确保 lo 达标、hi 不达标
    rl = page_ratio(lo, args.query, args.token, args.org, words)
    rh = page_ratio(hi, args.query, args.token, args.org, words)
    print(f"  基准: {lo}页={rl[2]}% | {hi}页={rh[2]}%")
    if rl[2] < args.threshold:
        print(f"  ⚠️ 起始 {lo} 页已 <{args.threshold}%，往前找起点！"); return
    if rh[2] >= args.threshold:
        print(f"  ⚠️ 结束 {hi} 页仍 ≥{args.threshold}%，往后扩大！"); return

    # 二分找临界（保持 lo 达标，hi 不达标）
    while hi - lo > 2:
        mid = (lo + hi) // 2
        rm = page_ratio(mid, args.query, args.token, args.org, words)
        print(f"  二分[{mid}]页={rm[2]}%")
        if rm[2] >= args.threshold:
            lo = mid
        else:
            hi = mid

    # 线性微调：但要从上往下找最后达标页，且**从前往后**确认不遗漏
    # 最终临界 = lo（最后一张≥threshold的页）→ 保存到 lo 页
    print("\n=== 70% 临界点（最后一张≥70%的页）===")
    print(f"  ★ 临界页 = {lo}（{args.threshold}%={page_ratio(lo,args.query,args.token,args.org,words)[2]}%）")
    print(f"  → 保存范围：前 {lo} 页 = {lo*10} 家（这个临界之前全部≥{args.threshold}%）")
    print("  ⚠️ 保存前必须【人工读描述复核】临界页及其前后页（L-20/21/22）")

if __name__ == "__main__":
    main()
