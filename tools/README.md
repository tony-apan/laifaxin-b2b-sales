---
title: "工具目录（Tools）"
description: "知识库配套核心工具脚本：闸门/登录/编排/保存/模板/序列/验证，含固化规则说明"
created: 2026-08-21
updated: 2026-09-04
author: "AI Agent + 运营方"
source: "实战沉淀"
related: [lessons/fixation, specs/api-reference, docs/08-workflow-ops]
tags: [工具, 脚本, 自动化]
status: verified
audience: AI优先（人可参考）
---

# 🛠️ 工具目录（Tools）

## 📁 随库核心工具

> ★ 全量历史工具登记（含 deprecated/research 未随库分发条目）= `../db/tools.tsv`；本表仅列随库脚本。

| 工具 | 用途 | 固化规则 |
|------|------|---------|
| `gate_check.sh` | 流程开始前强制闸门（token 有效 + 必读文档 + 规则命中） | ✅ 未通过禁止写操作 |
| `check_login.py` | 流程第一步·登录检查（只读，三分类引导） | ✅ org 自动从 token 提取 |
| `bootstrap.sh` / `bootstrap.ps1` | 无 Python 前提的跨平台环境探测/自动安装/复查 | ✅ 环境入口；详见 environment-setup |
| `onboard_check.py` | Python 就绪后的自检 + 可续接项目/status/profile扫描 | ✅ 不输出 token/审批原话/邮箱 |
| `operator_profile.py` | 公司级资料档案（跨产品/换机复用） | ✅ 签名只读纯昵称；不含 token/第三方资料 |
| `product_profile.py` / `profile_utils.py` | 产品档案 init/confirm/validate/status + 版本/hash/昵称/第三方信息闸门 | ✅ draft阻断；confirmed/declined分流 |
| `update_run_state.py` | operation-record 状态推进（换机续接真源） | ✅ 节点成功后更新 status/next_state/profile版本hash |
| `finalize_audit.py` | S4审计收口（70%临界证据+独立放行review） | ✅ 证据过审才推进S4，之后才可保存 |
| `finalize_run.py` | S11终检收口（verification-manifest绑定4证据hash/project/seq/profile） | ✅ 当前S10且证据全过才推进S11 |
| `flow_orchestrator.py` | S0-S12 节点确认向导（原型，写操作须人工执行） | ✅ 必传profile；稳定项目键+hash入审批参数 |
| `approval.py` | 审批凭证模块（`require_approval` 硬闸门 + `record` 记账） | ✅ 凭证在 `.local/approvals.tsv`（不入 Git）|
| `save_first_n.py` | 保存前 N 条（front + exclude4区 + max3） | ✅ 默认 exclude CN,TW,HK,MO |
| `wait_save_done.py` | 时序守卫（等保存 finished + 标签联系人>0） | ✅ 双闸，否则禁 contact-add |
| `gen_templates.py` | 模板生成器（必须 plan+profile，12轮×10变体） | ✅ 签名纯昵称 + profile hash + claims来源 + 24hex |
| `check_template_diff.py` | 模板差异断言（Jaccard≤0.70，逐模板取真实 html） | ✅ 空 html 恒达标=假阴性 |
| `rebuild_templates.py` | 重建模板+序列步骤（原型，顺序见 L-43） | ✅ 先建新→改引用→再删旧 |
| `render_preview.py` | 模板渲染预览（收件人视图，非源码） | ✅ |
| `build_sequence.py` | S9 建序列一条龙（tz/notSentTags 运行时解析+12步） | ✅ --approval 硬闸门 |
| `contact_add.py` | S10 加联系人一条龙（时序守卫 + views:[] 铁律） | ✅ views 恒为空数组 |
| `tag_add.py` | S5 前置·建标签（中文名 + 同名复用） | ✅ 记录 id(名称) 成对 |
| `resolve_schedule.py` | 时区计划时间解析（schedule_id 运行时解析） | ✅ 各账号不同，禁止硬编码 |
| `audit_company.py` | 搜索页精准度审计（词匹配只做趋势初筛） | ✅ 临界须 AI 语义反思 |
| `find_threshold.py` | 二分找 70% 临界（参考） | ✅ 人工复核临界页 |
| `find_critical.py` | 三页平均找临界（参考） | ✅ 人工复核临界页 |
| `verify_exclude.py` | 4区排除抽验（抽样，proxy=company-list） | ✅ 保存结果以 backend-task-status 为准 |
| `verify_sequence.py` | 序列终检（inactive + 12步 + 24hex + 步长） | ✅ 激活前硬闸门 |
| `activate_sequence.py` | S12 激活/回滚 | ✅ TTY审批+profile+合规证据+回读状态 |
| `seed_resolve.py` | S3 结果id→真实域名 | ✅ 只读，禁止拿公司名当锚 |
| `delete_all_products.py` | 清空产品档案（高危） | ✅ 默认dry-run，显式确认才执行 |
| `segments_infer.py` | 推理N轮→客群落地（S2 产出机读落地） | ✅ --approval S2 |
| `check_rules.sh` | AI 自查（规则/本地问题/token） | ✅ |

## ⚠️ 固化规则（工具内置，防再犯）

### contact-add 铁律（L-01）
```python
# 必须 views:[]（空），绝不 ["all"]！
def add_contacts(seqId, tags):
    assert views == [], "⚠️ views 必须 []！['all'] 会加全部 139 万联系人！"
    resp = contact_add(seqId=seqId, tags=tags, views=[])
    if resp['data']['add'] > 10000:
        raise Warning(f"⚠️ add={resp['data']['add']} 过多，请确认 tags 正确")
    return resp
```

### 标签 ID 铁律（L-03/04）
```python
def get_tag_id(name, tag_type):  # tag_type: company/contacts
    # 查 tags-list，不存在则 tags-add，返回 ID（绝不传名称）
```

### pageSize 铁律（L-09）
```python
PAGE_SIZE = 20  # 统一 ≥10
```

## 📌 使用

```bash
# 无 Python 前提环境准备
bash bootstrap.sh --check-only       # macOS/Linux/Git Bash/WSL
bash bootstrap.sh --install
# Windows PowerShell: powershell -ExecutionPolicy Bypass -File bootstrap.ps1 -Install

# 公司级/产品级档案
python3 operator_profile.py init --operator-key <operator_key> --nickname <纯昵称>
python3 product_profile.py init --profile ../runs/<operator_key>/<product_key>/product-profile.md --operator-key <operator_key> --product-key <product_key>

# 登录检查（流程第一步）
python3 check_login.py --token '<accesstoken>' [--org <orgId>]

# 流程闸门（未通过禁止写操作）
bash gate_check.sh --token <TOKEN> [--org <orgId>]

# 保存前N（★--approval 硬闸门）
python3 save_first_n.py --token $TOKEN --org <orgId> --keyword <种子> --n <前N条数> \
  --company-tag <tagId> --contact-tag <tagId> --profile ../runs/<operator_key>/<product_key>/product-profile.md \
  --record ../runs/<operator_key>/<product_key>/operation-record.md --approval <绑定凭证> --project <operator_key>/<product_key>

# 建模板（profile/plan/稳定项目键为硬闸门）
python3 gen_templates.py --token <T> --org <orgId> --product <产品> \
  --profile ../runs/<operator_key>/<product_key>/product-profile.md --plan <plan.json> \
  --prefix "英-<产品>-" --name <纯昵称> --project <operator_key>/<product_key> --preview
```

## 🔗 相关

- 固化机制：[lessons/fixation.md](../lessons/fixation.md)
- 问题库：[lessons/lessons-learned.md](../lessons/lessons-learned.md)
- 全量工具登记：[../db/tools.tsv](../db/tools.tsv)
