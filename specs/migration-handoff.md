---
title: "换机续接 SOP（AI 执行·备份/恢复/节点定位）"
description: "换电脑续接获客项目的完整 AI SOP：旧机只备份 .local/、runs/<运营方>/（排除 _template/INDEX.md）、db/ 中本地未跟踪文件；新机先装同版/最新仓库并按 environment-setup 就绪环境；恢复先解到临时目录、只按白名单复制允许路径（不覆盖新仓规则/_template/db 跟踪索引），再逐项校验（项目/状态/profile 版本/序列 inactive）；token 不迁移新机重取；审批凭证仅作审计，高风险写节点必须新机对话原话重新确认；按 operation-record.md 标准状态定位节点续跑，禁止从 S0 重跑。附可直接复制给 AI 的用户指令块。"
created: 2026-09-04
updated: 2026-09-04
author: "AI Agent"
source: "RULES.md 迁移/持久性 + 审批闸门边界 + onboard_check.py 可续接扫描"
related: [RULES.md, environment-setup.md, ../tools/onboard_check.py, ../runs/_template/operation-record.md]
tags: [换机, 迁移, 续接, 断点, SOP, AI优先]
status: verified
audience: AI优先
---

# 🔄 换机续接 SOP（AI 执行）

> **一句话**：换电脑 = **旧机只打包本地数据（.local/、runs/<运营方>/、db 本地未跟踪文件）→ 新机装仓库+环境 → 临时目录解包+白名单恢复到原路径+逐项校验 → token 重取 → 从 operation-record.md 定位的节点续跑**。绝不从 S0 重跑，绝不信旧机审批凭证当授权，绝不用备份覆盖新仓规则/模板/跟踪索引。
> **给谁看**：AI（执行者）。用户只复制文末指令块和回答"确认/否/要改"。
> **前置阅读**：`RULES.md`（迁移/持久性 + 审批闸门边界）+ [environment-setup.md](environment-setup.md)（新机环境就绪）。

## 0. 边界（先读，安全红线）

- `.local/`（含审批凭证）与 `runs/<运营方>/` 含账号活动痕迹与运营数据：**只在本机/用户指定移动盘之间复制**；不上传网盘/网站/聊天工具，不打包进任何要发布的东西（README 隐私与脱敏节同款要求）。
- **token 永不迁移、永不落盘**：token 只存在于对话命令/环境变量；新机一律重取（旧机 token 可能已失效，且传递 token 本身就是风险）。
- **审批凭证迁移后必须技术降级**：恢复 `.local/approvals.tsv` 后立即执行 `python_cmd tools/approval.py demote-migrated --confirm MIGRATION-DEMOTE`，把所有旧 `confirmed` 改为 `backfilled`；backfilled 只审计、工具不会授权。未执行写节点与S12在新机当前对话重新确认。
- 恢复操作只写数据目录（`.local/`、`runs/<运营方>/`、`db/` 中新机未跟踪文件），**不覆盖新装的规则/工具/模板文件**（RULES/SKILL/specs/tools 与 `runs/_template/`、`db/docs.tsv`、`db/tools.tsv` 等以新机仓库版本为准）；恢复一律先解到临时目录、按白名单复制，禁止把备份整包解压覆盖到仓库根。

## 1. 阶段一：旧机备份（AI 执行）

备份对象（★静态红队P1收窄: 只备份本地数据，**不打整个 runs/ 与 db/**——仓库自带的 `runs/_template/`、`runs/INDEX.md`、`db/docs.tsv`、`db/tools.tsv` 等以新机仓库为准，混进备份会在恢复时覆盖新版规则文件）：

| 目录 | 内容 | 是否必备 |
|---|---|---|
| `.local/`（整目录） | 审批凭证 approvals.tsv、运营方档案（新版 `.local/operators/<operator_key>.md` 多公司各一份；旧版 `operator-profile.md` 兼容）等本地状态 | 必备 |
| `runs/<运营方>/`（只备份运营方目录；**排除 `runs/_template/` 与 `runs/INDEX.md` 等仓库自带文件**） | 各产品 operation-record.md / product-profile.md / evidence.json / tmap.json / verify-* 等 | 必备 |
| `db/` 中**本地未跟踪文件**（`db/issues.tsv` 等运行期新增表；`db/docs.tsv`、`db/tools.tsv` 等仓库自带跟踪文件**不带**） | 本地数据表（用于审计与 runs 登记） | 可选（有就带上） |

bash（macOS/Linux/Git Bash/WSL）：

```bash
# 在旧机仓库根目录执行；日期换成当天
STAMP=$(date +%Y%m%d)
STAGE=$(mktemp -d) && mkdir -p "$STAGE/runs" "$STAGE/db"

# 1) runs：只拷运营方目录（排除 _template；INDEX.md 等仓库自带文件不拷）
find runs -mindepth 1 -maxdepth 1 -type d ! -name '_template' -exec cp -R {} "$STAGE/runs/" \;

# 2) .local：整目录（审批凭证+运营方档案）
cp -R .local "$STAGE/.local"

# 3) db：只备份本地未跟踪文件（git 仓库按跟踪清单过滤；非 git 安装=ZIP 解压, 无跟踪文件, 全部带上）
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  for f in db/*; do
    [ -f "$f" ] && ! git ls-files --error-unmatch "$f" >/dev/null 2>&1 && cp "$f" "$STAGE/db/"
  done
else
  for f in db/*; do
    [ -f "$f" ] || continue
    case "$(basename "$f")" in docs.tsv|tools.tsv) continue;; esac
    cp "$f" "$STAGE/db/"
  done
fi

# 打包（放仓库外）并核对（应只含 .local/、runs/<运营方>/、db/ 三类路径, 不含 _template/INDEX.md/docs.tsv/tools.tsv）
tar -czf ../laifaxin-backup-$STAMP.tar.gz -C "$STAGE" .local runs db
tar -tzf ../laifaxin-backup-$STAMP.tar.gz | head -50
tar -tzf ../laifaxin-backup-$STAMP.tar.gz | wc -l
```

Windows PowerShell（旧机）：

```powershell
# 只备份 .local、runs\<运营方>(排除 _template/INDEX.md)、db 中本地新增文件
$stamp = Get-Date -Format yyyyMMdd
$stage = Join-Path $env:TEMP "lfx-backup-$stamp"
New-Item -ItemType Directory -Force "$stage\runs", "$stage\db" | Out-Null
Copy-Item .local "$stage\.local" -Recurse -Force
Get-ChildItem runs -Directory | Where-Object Name -ne '_template' |
  ForEach-Object { Copy-Item $_.FullName "$stage\runs\" -Recurse -Force }
# db：git 跟踪文件跳过；无git时至少硬排仓库自带docs.tsv/tools.tsv
$tracked = @('db/docs.tsv','db/tools.tsv'); $git = Get-Command git -ErrorAction SilentlyContinue
if ($git) {
  $null = git rev-parse --is-inside-work-tree 2>$null
  if ($LASTEXITCODE -eq 0) { $tracked = @(git ls-files db) }
}
if (Test-Path db) {
  Get-ChildItem db -File | Where-Object { $tracked -notcontains ("db/" + $_.Name) } |
    ForEach-Object { Copy-Item $_.FullName "$stage\db\" -Force }
}
Compress-Archive -Path "$stage\.local", "$stage\runs", "$stage\db" -DestinationPath "..\laifaxin-backup-$stamp.zip"
# 核对
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::OpenRead("$PWD\..\laifaxin-backup-$stamp.zip").Entries.Count
```

核对标准：包内含 `.local/approvals.tsv` 与运营方档案；`runs/` 下每个 `<运营方>/<产品>/` 都在；**不含** `runs/_template/`、`runs/INDEX.md`、`db/docs.tsv`、`db/tools.tsv` 等仓库自带文件；条目数与 `find`/`dir` 清单一致。备份包放仓库外（桌面/上级目录/移动盘），**路径记录下来交给用户**。

## 2. 阶段二：新机就绪（先装仓库，再环境，最后恢复数据）

1. **装仓库**：优先与旧机**同版本**（旧机可看 `CHANGELOG.md` 顶部记录的版本/日期）；拿不到同版就装**最新版**。
   - git：`git clone https://github.com/tony-apan/laifaxin-b2b-sales.git`
   - ZIP：https://github.com/tony-apan/laifaxin-b2b-sales/releases/latest 下载解压
   - 装完读 `CHANGELOG.md` 顶部，把跨版本差异（流程/话术/工具变化）用通俗中文讲给用户听。
2. **环境就绪**：严格按 [environment-setup.md](environment-setup.md)（Windows PowerShell → `bootstrap.ps1`；macOS/Linux/WSL/Git Bash → `bootstrap.sh`；先 check-only，缺则 install，装后复查，用 `python_cmd` 跑 `onboard_check.py`）。
3. **恢复数据到同名路径**（此时才恢复，避免旧数据被新装流程误读为当前会话产物）。
   ★静态红队P1: **先解到临时目录核对，再按白名单复制**——只恢复 `.local/`、`runs/<运营方>/`、db 中(新机)未跟踪文件；
   **绝不解压/复制覆盖新仓的规则与模板文件**（README/RULES/SKILL/specs/tools、`runs/_template/`、`runs/INDEX.md`、db 已跟踪索引 `db/docs.tsv`/`db/tools.tsv` 一律以新机仓库为准）：

```bash
# bash：在【新机仓库根目录】执行；先解到临时目录并列表给用户确认
STAGE=$(mktemp -d)
tar -xzf /path/to/laifaxin-backup-YYYYMMDD.tar.gz -C "$STAGE"
tar -tzf /path/to/laifaxin-backup-YYYYMMDD.tar.gz        # 只应含 .local/ runs/<运营方>/ db/ 三类路径

# 白名单恢复(逐条执行, 拒绝整包覆盖):
# 1) .local：整目录覆盖合并
cp -R "$STAGE/.local" ./
# 2) runs：只复制运营方目录, 绝不触碰 runs/_template 与 runs/INDEX.md
for d in "$STAGE"/runs/*/; do
  name=$(basename "$d"); [ "$name" = "_template" ] && continue
  mkdir -p "runs/$name" && cp -R "$d/." "runs/$name/"
done
# 3) db：只恢复新机仓库未跟踪的文件(仓库自带 db/docs.tsv、db/tools.tsv 不覆盖)
for f in "$STAGE"/db/*; do
  [ -f "$f" ] || continue
  rel="db/$(basename "$f")"
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git ls-files --error-unmatch "$rel" >/dev/null 2>&1 || cp "$f" db/
  else
    case "$rel" in db/docs.tsv|db/tools.tsv) continue;; *) cp "$f" db/;; esac
  fi
done
```

```powershell
# PowerShell：先 Expand-Archive 到临时目录, 再只复制 .local、runs\<运营方>(跳过 _template/INDEX.md)、db 中未跟踪文件
Expand-Archive -Path C:\path\to\laifaxin-backup-YYYYMMDD.zip -DestinationPath $env:TEMP\lfx-restore -Force
Copy-Item "$env:TEMP\lfx-restore\.local" .\.local -Recurse -Force
Get-ChildItem "$env:TEMP\lfx-restore\runs" -Directory | Where-Object Name -ne '_template' |
  ForEach-Object { New-Item -ItemType Directory -Force ("runs\" + $_.Name) | Out-Null;
                  Copy-Item $_.FullName ("runs\" + $_.Name) -Recurse -Force }
$tracked = @('db/docs.tsv','db/tools.tsv'); $git = Get-Command git -ErrorAction SilentlyContinue
if ($git) {
  $null = git rev-parse --is-inside-work-tree 2>$null
  if ($LASTEXITCODE -eq 0) { $tracked = @(git ls-files db) }
}
Get-ChildItem "$env:TEMP\lfx-restore\db" -File -ErrorAction SilentlyContinue |
  Where-Object { $tracked -notcontains ("db/" + $_.Name) } |
  ForEach-Object { Copy-Item $_.FullName .\db\ -Force }
```

4. **恢复后核对**：本地数据行数/目录与备份一致；仓库自带文件保持新机版本——git安装用 `git status/git diff`，ZIP安装用新下载包清单/hash对比（无 `.git` 时不要执行 git status）。

## 3. 阶段三：续接校验（逐项过，全绿才续跑）

先跑扫描，再逐项核对（扫描输出只含状态元数据，不含 token/审批原话/邮箱）：

```bash
python3 tools/onboard_check.py     # Windows 用 bootstrap 给出的 python_cmd（如 py）
```

| # | 校验项 | 方法 | 通过标准 | 不通过时 |
|---|---|---|---|---|
| 1 | 项目清单 | `onboard_check.py` 可续接扫描 + 目录对比 | 与旧机备份的 `runs/<运营方>/<产品>/` 完全一致 | 缺目录→从备份补拷；多目录→问用户是否旧项目再定 |
| 2 | 流程状态节点 | 读 `runs/<运营方>/<产品>/operation-record.md` frontmatter `status/updated` + 正文『✅ 本轮最终记录』表 | 能唯一定位 S0-S12 某节点（或 done/active） | 定位不到→AI 读表+向用户确认最后做到哪，**不猜、不从 S0 重来** |
| 3 | product-profile 版本 | 同目录 `product-profile.md` 的 `status/profile_version/updated_at/confirmed_at`（缺字段按无版本元数据处理） | 与旧机一致；`confirmed` 档案才可直接复用 | 未确认/更旧版本→续接涉及客群/文案节点前先请用户重新确认 |
| 4 | 序列状态（S9 之后的项目） | token 重取后 `tools/verify_sequence.py --seq <id>` / sequence-details 线上核对 | S11 及之前：序列 **inactive**；S12 已激活：状态=active 且与档案记录一致 | 线上与档案不一致→列差异问用户，禁止盲目再激活/再加联系人 |
| 5 | 审批流水 | `.local/approvals.tsv` 行数与关键行存在 | 历史可追溯（审计用） | 仅记录，不作为任何写操作的授权 |
| 6 | 环境 | `bootstrap --check-only` 全绿 | `all_ok=1` | 回 environment-setup.md 错误分级处理 |
| 7 | token | 引导用户按教程重取（https://www.laifa.xin/share/ai/laifaxin-ai-account-connection ）→ `check_login.py` 复验 → `gate_check.sh` 过闸 | 登录检查通过+闸门全绿 | 失效→再重取；不跳闸门 |

## 4. 阶段四：定位续跑（禁止从 S0 重跑）

- **唯一合法定位方式**：`runs/<运营方>/<产品>/operation-record.md` 的标准状态（frontmatter `status` + 『✅ 本轮最终记录』表 + 各步骤①-⑧记录）。`onboard_check.py` 会自动解析 `status/updated` 并给出该节点的下一步提示。
- **为什么禁止从 S0 重跑**：S0 重来会重复建产品档案/客群/标签/保存任务——重复保存浪费点数且系统虽去重但任务流水会脏（RULES 防重复保存）；token 失效 SOP 同款原则："从当前节点继续，勿从 S0 重跑重复建产品档案"。
- **续跑时的高风险写节点授权**：历史 approvals 只审计；每个未执行写操作都按工具docstring的实际参数JSON在新机当前对话重新确认，用 `approval.py grant` 铸造绑定hash的 confirm+confirmed 凭证。flow参数不全时只记pending，不授权。
- **S12 特别提醒**：旧机上"待激活"≠新机上可以激活；激活前自查清单（市场规则/名单来源/发送主体/退订入口/拒收机制）在新机重新过一遍，激活命令必须带新机原话与 S12 凭证（`activate_sequence.py --confirm "<用户原话>"`）。

## 5. 用户指令块（直接复制给 AI）

**旧机（备份）——把下面整段复制发给旧电脑上的 AI：**

```text
请帮我备份这台电脑上的获客系统数据，准备换电脑：

1. 找到获客系统文件夹（我把仓库路径发你；找不到就问我，不要猜路径）。
2. 只备份本地数据，打包到系统文件夹外面（桌面或上级目录），命名含今天日期：
   .local/（审批凭证与运营方档案, 整目录）
   runs/ 下我自己的运营方目录（★排除 runs/_template 和 runs/INDEX.md 等仓库自带文件）
   db/ 里本地新增的数据表（★仓库自带的 db/docs.tsv、db/tools.tsv 不带）
3. 备份完做核对：列出备份包里 .local/approvals.tsv 的行数和 runs/ 下的产品目录清单，
   和原目录对得上才算成功；备份包里不应出现 _template/INDEX.md/docs.tsv/tools.tsv；
   对不上就停下告诉我。
4. 备份包只放本机或我指定的移动盘，不要上传任何网盘/网站/聊天工具；
   里面含我的账号活动痕迹，等同敏感文件。
5. 完成后告诉我备份包的完整路径，并给我一段能直接复制到新电脑 AI 的话（续接指令）。
```

**新机（恢复+续接）——把下面整段复制发给新电脑上的 AI（连同备份包路径）：**

```text
我在新电脑上续接之前的获客项目，数据备份包在：<备份包路径>（没发你的话先问我要，不要猜）。

1. 先装系统仓库：优先装和我旧机相同的版本，拿不到就装最新版——
   git clone https://github.com/tony-apan/laifaxin-b2b-sales.git
   或到 https://github.com/tony-apan/laifaxin-b2b-sales/releases/latest 下载 ZIP 解压；
   装完对照 CHANGELOG.md 顶部，把版本差异用通俗中文讲给我听。

2. 环境就绪：按 specs/environment-setup.md 执行——
   Windows PowerShell：powershell -NoProfile -ExecutionPolicy Bypass -File tools\bootstrap.ps1 -CheckOnly
     （有缺失就换 -Install 装，装完再 -CheckOnly 复查）
   macOS/Linux：bash tools/bootstrap.sh --check-only（有缺失就 --install）

3. 恢复数据到和新机仓库的同名路径（先解到临时目录、列清单给我确认再写入）：
   .local/、runs/<运营方>/、db/ 里的本地数据表（若有）；
   ★只按白名单恢复这三类数据路径，不覆盖新装的规则和工具文件，
     不碰 runs/_template、runs/INDEX.md 和 db 已跟踪的 docs.tsv/tools.tsv；
   恢复后核对行数和目录；git安装用 git status，ZIP安装与新下载包清单/hash对比，确认仓库自带文件没被动过。

4. 用 bootstrap 输出的 python_cmd 运行 tools/onboard_check.py，把“可续接项目”扫描结果讲给我听。

5. 立即用 python_cmd 运行 `tools/approval.py demote-migrated --confirm MIGRATION-DEMOTE`，把旧机confirmed凭证全部降为backfilled（仅审计）。

6. 逐项校验并汇报：项目目录、operation-record状态、product-profile版本、序列是否inactive。

7. 带我重新取token（不迁移），通过登录检查和gate；只从当前节点继续。所有未执行写操作/S12都要新机当前对话重新确认。
```

## 6. 常见坑

| 坑 | 正解 |
|---|---|
| 恢复后直接把旧 `.local` 当授权继续写 | 立即执行 `approval.py demote-migrated --confirm MIGRATION-DEMOTE`，旧confirmed→backfilled；写节点再取新机原话/新凭证 |
| 新机没跑 bootstrap 就想跑 onboard_check.py | onboard_check 是 Python 脚本，Python 没就绪它跑不起来（bootstrap 悖论）；先走 environment-setup.md |
| 备份/恢复把整个 `runs/`、`db/` 打包带走 | 只备 `.local/`、`runs/<运营方>/`（排除 `_template`/`INDEX.md`）、db 本地未跟踪文件；整包会把仓库自带规则文件一起带回并在恢复时覆盖新版 |
| 恢复时把备份整包解压到仓库根"图省事" | 必须先解到临时目录再按白名单复制；整包解压会覆盖 `runs/_template/`、`db/docs.tsv`、`db/tools.tsv` 等新仓版本 |
| 恢复时把新仓库 `runs/_template/` 覆盖/删除 | `_template` 是仓库自带模板，保留新版本；只恢复 `<运营方>` 目录 |
| ZIP 装新版解压成新目录另起炉灶 | 必须恢复到**同名路径**；另起新目录会找不到历史档案（README 更新 SOP 同款硬规则） |
| S12 状态的项目在新机"顺手再激活一次" | 先线上核对序列状态与档案一致；已 active 不重复激活；未激活按新机原话+S12 自查清单走 |
| 把备份包发到聊天工具"图省事" | 违反安全红线：`.local/` 与 `runs/` 只在本机/指定移动盘之间复制 |
