---
title: "域名近似规模化保存 SOP"
description: "一个网址搜上万相似客户 → 审计70%临界 → 保存前N条(selectTotal，不收集id) → 配额管理；纯API不用浏览器"
created: 2026-08-21
updated: 2026-09-03
author: "AI Agent + 运营方"
source: "实战验证（2026-08-21 电动自行车）"
related: [specs/api-reference, specs/operations-sop, lessons/lessons-learned]
tags: [SOP, 规模化, 域名搜索, 配额, selectKeys]
status: verified
audience: 人+AI
---

# 🚀 域名近似规模化保存 SOP（纯 API）

> **核心**：一个精准客户网址 → 搜出 **9999 条相似**（不是滚雪球！）→ 审计 70% 临界 → **保存前N条(selectTotal)**。

## 一、正确流程（★已验证）

```
① 找精准种子（AI推演客群→搜索前几页挑最准的）
      ↓
② refine/company-list 用【域名】做 keyword → 一次搜出上万条（total:9999）
      ↓
③ 审计找 70% 临界点（★find_threshold.py：**从前往后二分找"最后一张≥70%的页"**，保存到该页；一旦某页<70%就不看后面，往前精确找边界）
      ↓
④ **保存前 N 条（一个任务，不收集id！）**：`refine/company-save` + `selectTotal:N` + `selectKeys:[]` → 见 [save_first_n.py](../tools/save_first_n.py)
      用法: `python3 save_first_n.py --token $TOKEN --org <orgId> --keyword <种子> --n <前N条数(界面"选择前N",如8000)> --company-tag .. --contact-tag .. --approval <ap-id> --project <产品>`（★--approval 硬闸门必传，否则工具 exit 1 拒绝写入，审批闸门(工具级)）
      ↓
⑤ 验证（★backend-task-status type=cluesSave 的 contactSaveCount/companySaveCount，**非 company-save-list**）
```

**关键验证**（2026-08-21 电动自行车）：
```
keyword: <seed-domain> → total:9999
第1页 90% / 第500页 90% / 第950页 70%(临界) / 第990页 30%
批15(240家): validSave:195 + unkownSave:131 = 326 邮箱 ✅
```

## 二、三个铁律（踩坑教训）

### 1. ★ 保存"前 N 条" = selectOption:"front" + selectTotal（提邮箱，不收集id/分批）
```json
"selectKeys": [],        // ★ 空 = 保存前N
"selectTotal": 8000,     // ★ 前8000
"selectOption": "front", // ★ 关键！front才提邮箱（current=邮箱0！）
"contactMaxCount": 3     // ★ 默认3(每公司邮箱数裁决,阶梯3→6→9;界面默认显示5是误导)
```
- **实测**：`front + selectTotal:8000 + selectKeys:[]` → **contactSaveCount 持续增长**（提邮箱，不翻页）！
- ⚠️ **selectOption 必须 "front"**！用 "current" -> 邮箱0（大坑 L-29）
- ⚠️ **验证用 `backend-task-status`**（data.contactSaveCount=邮箱数），不是 company-save-list（误导）
- ⚠️ **不要**收集id翻页 + selectKeys 分批（那是勾选特定id，需翻页=封号）
- ⚠️ 页面**每页最多10条**——保存前N用 selectTotal（不翻页，安全）
- ⚠️ 早先用 `pageSize100翻页收集id+selectKeys分批` 是**多余且错**（L-28/29）

### 2. 权威 id（★ vs refine 搜索临时 id）
- ✅ **域名搜（refine/company-list + 域名keyword）返回的 id = 权威 id**（validSave 大量 >0）
- ❌ 泛关键词搜（electric bike dealer）返回的 id 是**搜索会话临时 id** → validSave=0（之前误判为"valid邮箱不保存"）
- **真相**：valid 邮箱能保存，关键是 **id 用域名搜的权威 id**

### ⭐ 0. 向量搜索机制（★排除4区 CN/TW/HK/MO）
> ★ 正确 exclude schema（实测有效 2026-08-29，用户修正）：
> `{"property":"country_code","operator":"exclude","value":"","values":["CN","TW","HK","MO"],"valueType":"select"}`
> ⚠️ **必须带 `value:""` + `valueType:"select"`**（缺失=无效）！
> ⚠️ **total 不变≠无效**（total=截断10000+后排补位）；**看列表内容**判断（含4区→种子公司自身仍显示）
> 实测：<seed-domain>+exclude 含4区 6→1（仅剩种子公司）；保存时CN公司无邮箱入contact（标准见 marketing-rules-2.0.md）（★用户核心认知）

**用网址搜 = 向量搜索**：系统取该网址公司的**英文描述向量**，在数据库中检索相似 → **按相似度排序，从前往后精准度有规律递减**（不是关键词混入无关）。

**★ 判定标准 = 产品匹配率（不是 _score！）**
- `_score` 只是"客户与搜索网址描述的相似度"（展示用）
- **要算**：**一页 10 个客户里有多少个和"你的产品"相似**（产品匹配率）
- **标准：≥70%** 才算可保存

**实测验证（<seed-domain>，电动自行车产品匹配率）**：
```
第1~950页:  100%（10/10 全部自行车/电动自行车行业客户）
第1000页:   89%（8/9，仅1条非）
→ 70% 临界点实际在 1000页后（9999条全达标）
```

**操作**：
1. 网址搜 → 结果按 _score 递减（规律性）
2. **每页完整看10条，算"产品匹配率"**（逐条问：这是电动自行车/自行车行业客户吗？配件算/媒体不算）
3. ≥70% 才保存；找到跌破 70% 的页 = 临界点
4. 50页粒度跳读（20次查看），选中页**完整看10条**

**结论**：
1. ✅ 网址向量搜索数据精准（1000页内 89-100%，有规律递减）
2. ✅ 按**产品匹配率 ≥70%** 定范围（不是 _score 阈值）
3. ✅ 已保存 9500 家正确（甚至可扩到 9999）

### 3. 每日查看配额（★ SVIP 驱动）
```
dailyLimit: 500 次/天（SVIP 日配额）
monthlyLimit: 10000 次/月
超额后：界面"继续查看"确认 → 1点/次扣点（monthlyChargeCount 记录）
⚠️ API 新查询受 daily 500 硬限制；解锁后仍可能限制新 keyword 查询
```
- **执行**：规模化前先查 `benefits/refine-data`（dailyUsed/dailyUsedUp）
- **遇 quota 用完**：界面确认扣点解锁 或 等次日重置

## 三、匹配度标准（语义判断，可配置 · 用户裁定）

> **★ 核心原则（用户反复纠正）**：**判断标准 = "这家客户有没有可能买我的产品"**
> 不是"它现在卖不卖这个产品"，而是**"有没有采购可能"**：
> - ✅ 钓鱼/户外/露营/划船/水上运动/户外租赁/休闲运动 → **可能采购**（算匹配）
> - ✅ 零售商/经销商/批发商/制造商/配件商/耗材商 → 匹配
> - ✅ 卖水上/户外/休闲的、配套的 —— 都算（客户群交叉购买可能）
> - ❌ 纯非户外（轮胎/拖车/动力运动/视听/皮革/器械）→ 不匹配
>
> **多读几页**：在临界附近**多读几页**（不是跳着读3页），精确定位70%临界。

> **★ 关键**：不是抠"字样"（含某词=匹配）！**要读描述语义**判断"是否潜在采购方"。

### 三档标准（默认中等，让用户选）

| 档位 | 定义 | 例（写真机/电动自行车）|
|------|------|----------------------|
| **严格** | 只算**明确经营/采购该产品的经销商/零售商** | 明确卖电动自行车/写真机的零售/经销商 |
| **中等（默认）** | 严格 + **配件商/制造商/服务商**（配套采购，海外制造商也是目标）| 卖配件、辅料、耗材、维修服务、自称制造商的 |

  > ★2026-08-31 互链：本档与 `specs/threshold-method.md` v2 客户线判定对齐——海外制造商=OEM 线、配件商=拓品线（按其计数规则分别记线，不混入直采池）
| **宽松** | 中等 + 目录/平台/边缘也凑 | 目录商、内容平台 |

### 语义判定要点
- ✅ **读完整描述**（中英文），逐条判断"会不会采购/配套"（不是词匹配）
- ✅ 零售商/经销商/批发商/制造商 → 匹配
- ✅ **配件商/耗材商** → 匹配（中等，配套采购；"海外自称制造商的也是目标"）
- ⚠️ 服务商（维修/租赁）→ 看是否采购
- ❌ **媒体/杂志/评测/内容平台/目录商** → 不匹配（不采购）
- ❌ 完全无关 → 不匹配

> ⚠️ 教训：**不能用"含某字样"判断**（L-21）——Bicis Camacho 含"自行车"但它是目录商（非采购）→ 应判不匹配。**读描述语义**。

### 人工抽查
工具只是初筛（词库），**结论必须人工读描述核对**（L-20）。每页完整10条读语义。

> 审计工具支持 `--match-words` 扩展产品词（中英文），但**最终判定以语义为准**。

## 四、执行要点

```bash
# 1. 审计（用域名搜的结果）
python3 audit_company.py --query "<seed-domain>" --pages 1,500,950,990,1000 \
  --token $TOKEN --org <orgId> --mode strict --product "电动自行车" \
  --match-words "e-bike,ebike,electric bike,电动自行车,电助力,自行车,cycle"

# 2. 查配额
curl -X POST /api/benefits/refine-data

# 3. 规模化保存（★现行=save_first_n.py front保存；旧版批量脚本已 deprecated 未随库分发——operator:"not"无效+翻页收集id=封号风险）
python3 tools/save_first_n.py --token $TOKEN --org <orgId> --keyword <种子> --n <前N> --company-tag <id> --contact-tag <id> --approval <ap-id> --project <产品>
```

## 五、实操结果（2026-08-21 电动自行车，纯 API）

```
种子: <seed-domain> → refine 搜出 9999 条
审计: 70% 临界 = 第950页（990页30%）
保存: 9500 家（38批×256，全部 OK；"按红队新规则应每公司5邮箱"=旧注，★已被 2.0 用户拍板覆盖=默认3邮箱/阶梯3→6→9，见 marketing-rules-2.0/每公司邮箱数裁决）
结果: 公司全部入库（联系人库 +3960），邮箱提取异步进行中
```

### ★ 邮箱提取是异步的（重要真相）
- **保存任务 = 公司入库 + 标签**（立即完成）
- **邮箱提取需时间**：refine 返回的 emailsCount 多为 0-2（相似客户邮箱少）→ validSave 分批增长
- **实测**：9500 家 → 邮箱 332+（批17 就 valid:178+unkown:103），持续提取增长
- **注意**：域名搜的相似客户**邮箱普遍偏少**，"30000 邮箱"取决于客户邮箱完备度，可能达不到——用邮箱更全的来源（domain-emails 主动提取）可加速

### ★ 配额重置真相
- daily 500 用完 → **次日自动重置**（实测 dailyUsed: 500→1）
- 重置后可继续翻页（规模化不中断）
- 规模化消耗：每翻页 1 次 = 1 查看（`refine-data` 监控 dailyUsed 增长）

## 六、实操结果（写真机，中等标准语义判断 · 完整示例）

```
产品: 写真机(大幅面打印)
种子: <seed-domain>（大幅面打印机）→ refine 搜出 9999 条
审计: 50页粒度 + 中等标准(读描述语义) → 全程 100%（1-1000页全印刷/大幅面行业）
保存: 9500+ 家（38批×256 OK），标签 <tagId>/<tagId>（历史,已删）
模板: 10 个英文写真机模板（R01-R06 策略递进）
序列: 写真机-英语-12轮10封-多轮开发（12步×10封，美国时间/30000/5/禁发询盘）
加人: contact-add → 6305（views:[] 铁律）
```

**★ 教训**：写真机数据**比电动自行车更干净**（全是印刷行业，无目录/媒体）——因为种子（大幅面打印机）方向准，向量搜的自然全是同行。**选对精准种子网址是前提**（写真机=大幅面打印领域，不要用家用打印机的种子）。

## 🔗 相关

- [specs/api-reference.md](api-reference.md)（refine/company-save 完整 payload）
- [lessons/lessons-learned.md](../lessons/lessons-learned.md)（L-02 已更新 id 真相）
- [tools/save_first_n.py](../tools/save_first_n.py)（★现行保存脚本；旧版批量脚本已 deprecated 未随库分发）

---

> **真实案例演示**：数字与域名为公开仓库作者当时实际运行结果，仅作方法演示，与读者业务无关。
