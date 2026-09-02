#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 时序守卫：等联系人保存任务 status:finished + 校验标签联系人>0，才可 contact-add 加序列。
用法: python3 wait_save_done.py --token <TOKEN> --org <orgId> --task <保存任务id> --tag <联系人标签id> --timeout 900
"""
import json, subprocess, sys, time, argparse

ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True)
ap.add_argument("--org", required=True)
ap.add_argument("--task", required=True, help="refine/company-save 返回的任务id")
ap.add_argument("--tag", required=True, help="联系人标签id（contact tag）")
ap.add_argument("--timeout", type=int, default=900, help="最大等待秒数")
args = ap.parse_args()

def api(path, payload, timeout=40):
    cmd = ["curl","-sSL","-X","POST",f"https://web.laifaxin.com/api/{path}?uid={args.org}",
           "-H","Content-Type: application/json","-H",f"accesstoken: {args.token}","-d",json.dumps(payload)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    try: return json.loads(r.stdout)
    except: return {}

start = time.time()
status = ""
while time.time() - start < args.timeout:
    d = api("operation/backend-task-status", {"type":"cluesSave","id":args.task}).get("data",{})
    status = d.get("status","")
    contact_save = d.get("contactSaveCount")
    if status == "finished":
        print(f"✅ 保存任务 finished: contactSaveCount={contact_save}")
        break
    print(f"⏳ 等待保存任务... status:{status} fin:{d.get('finished')}/{d.get('total')} contactSave:{contact_save}", flush=True)
    time.sleep(10)
else:
    print(f"❌ 超时({args.timeout}s)仍 {status}，禁止 contact-add"); sys.exit(1)

# 校验标签联系人>0（★ISS-52: 按标签过滤须 filters 数组, filter.tags 返全库假通过）
for i in range(6):
    d = api("contacts/contacts/show", {"current":1,"pageSize":10,"filters":[{"property":"tags","operator":"include","value":args.tag,"values":[args.tag],"valueType":"select"}],"sort":{}})
    data = d.get("data")
    if data is not None:
        try: n = int(data.get("total")) if isinstance(data, dict) else int(data)
        except: n = data
        if n and n > 0:
            print(f"✅ 标签 {args.tag} 联系人={n} >0 → 可以 contact-add")
            sys.exit(0)
        print(f"⚠️ 标签 {args.tag} 联系人={n}，仍为空（可能去重无新增），重试中...")
    time.sleep(8)
print("❌ 无法确认标签联系人>0（这是已知问题: 接口偶发抽风 平台接口间歇空(已知)——等 5-10 分钟重跑本命令即可,无需改动任何东西）; 禁止 contact-add"); sys.exit(1)
