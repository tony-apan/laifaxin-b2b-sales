# 来发信 B2B 批量获客系统

![status](https://img.shields.io/badge/status-active-success) ![version](https://img.shields.io/github/v/release/tony-apan/laifaxin-b2b-sales) ![license](https://img.shields.io/badge/license-GPL--3.0-green) ![python](https://img.shields.io/badge/python-3.9+-blue) ![platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows%20PowerShell-lightgrey)

> **批量触达相关买家，低成本筛出询盘；收到询盘后，再由业务员背调和精准跟进。**

这是一个给 AI 使用的操作说明书和工具箱。它不是自动成交工具，也不是逐家公司手工定制的精准开发服务。

**适合你，如果你：**

- 缺少客户基数，想先批量验证一个市场；
- 不想把大量人工时间花在没有回复的陌生公司上；
- 有能力承接询盘后的背调、报价、样品、谈判和长期跟进。

**它更适合「买家多、决策快、有渠道商」的产品**：保温杯、户外用品、标准工业组件这类——同行买家成千上万、习惯邮件询价、还有批发/分销/集成商可以打。

**它不太适合**：大宗原料、长周期项目制设备、需招标/认证/入库入围、好几年才采购一次、全市场买家屈指可数的品类——这类产品冷邮件回询盘通常以月甚至年计，广撒网只能帮你低成本摸底，不能替代展会、渠道或关键客户开发。判断口诀：**你的买家盘子里，能成批检索到多少家？他们多久采购一次？谁会用邮件回你？**（AI 会在开跑前帮你判三档并如实说明，不耽误你试）

```mermaid
flowchart TD
    U["你提供<br/>token + 昵称 + 一句话产品<br/>(可选: 官网/卖点/买家网址)"] --> A["选择客群"]
    A --> B["批量找买家"]
    B --> C["12轮邮件触达"]
    C --> D{"收到询盘?"}
    D -- "没有" --> B
    D -- "有" --> E["打标签停邮件"]
    E --> F["背调·分级·精准跟进"]
    F -. "询盘方网址=新种子<br/>继续扩量" .-> B
```

> **询盘只是信号，不等于订单。** 系统不会自动识别回复或自动打标签；人或 AI 助手发现回复后，必须实际打上“询盘”标签，邮件序列才会停止后续轮次。**优质询盘方的网址还是最好的新种子**——回流继续扩量，越滚越准。

| 快速入口 | |
|---|---|
| 🚀 [快速开始](#-第一步现在就把代码拿到手) | 下载仓库 → 准备 4 样 → 交给 AI |
| 📖 [完整方法：广撒网 + 精准跟进](docs/09-mass-outreach-to-precision-follow-up.md) | 成本账 / 询盘背调 / 分级 / 多渠道 |
| 📦 [最新版下载与版本说明](https://github.com/tony-apan/laifaxin-b2b-sales/releases/latest) | Releases |
| 🔄 [更新到新版本](#-更新到新版本老用户) | 同一台电脑升级（保留本地数据）|
| 💻 [换电脑继续干](#-换电脑继续干老用户) | 迁移本地状态，从当前节点接着跑 |

---

## 📦 第一步：现在就把代码拿到手

"代码"＝给电脑下的指令，这套系统就是写好的指令集合。**你不用碰命令行——把下面整段复制给 AI 就行。**

**办法 A（最简单）：把下面整段复制发给 AI**

```text
请帮我把这套外贸获客系统安装到我的电脑并完成学习：

1. 下载代码库（若我已发你本地文件夹/ZIP 路径，跳过这步，直接用那个文件夹）：
   git clone https://github.com/tony-apan/laifaxin-b2b-sales.git
   （如果 git 不可用，直接下载 https://github.com/tony-apan/laifaxin-b2b-sales/archive/refs/heads/master.zip 并解压）

2. 先把运行环境自动准备好（不要假设电脑已经有 Python）：
   · Windows PowerShell：powershell -NoProfile -ExecutionPolicy Bypass -File tools/bootstrap.ps1 -Install
   · macOS / Linux / Git Bash / WSL：bash tools/bootstrap.sh --install
   安装脚本会先探测 Python、curl、Git、bash/grep/awk，缺什么装什么，装完再复查；
   若系统没有可用包管理器，按输出给的官方下载地址处理，不要跳过环境复查。
   完整标准见 specs/environment-setup.md。

3. 通读仓库，重点按顺序学习：
   ① README.md（产品定位与流程）
   ② SKILL.md（你的执行入口：渐进引导图/路由表/状态机/铁律/话术模板索引）
   ③ RULES.md（唯一真源：完整状态机与铁律）
   ④ specs/environment-setup.md（环境准备）、specs/migration-handoff.md（换机续接）、
      specs/operator-profile-sop.md（公司级资料回落）与 specs/product-profile-sop.md（产品资料回落）
   ⑤ output-templates/README.md（之后每一步对用户说什么都照模板）
   ⑥ 执行到对应节点时再精读其他 specs/ 与 methodology/

4. 运行 python3 tools/onboard_check.py 自检；Windows 若 python3 不存在就用 py tools/onboard_check.py。

5. 学完后向我汇报（用通俗中文；token 现在不用催，到时带我去拿）：
   · 这套系统是干什么的、我的角色是什么
   · 你需要我提供什么（听说只要 token 和昵称+一句话产品，确认一下）
   · 整个流程分几步、哪些步骤会找我确认
   · 有什么风险或注意事项

6. 汇报完等我的产品介绍，然后按 SKILL.md 带我走完整个获客流程。
   注意：系统默认不发信；每一步都要我确认；最终激活发信必须我明确说"确认激活"。
```

**办法 B：点两下鼠标（不用 AI 代劳）**

在浏览器打开 https://github.com/tony-apan/laifaxin-b2b-sales（存代码的公开网站，用法和网盘差不多）→ 点网页**右上角 Code → Download ZIP**（ZIP＝压缩包，就是一个打包好的文件）→ 解压到桌面，然后把解压后的文件夹路径连同上面那段话一起发给 AI。

## 第二步：准备 4 样东西

- **① 一个来发信账号**。来发信（web.laifaxin.com）是帮你发邮箱、管跟进计划的平台，注册一个就行；账号的"钥匙"（token，一串字符）先不用管，第三步里 AI 会按官方教程（https://www.laifa.xin/share/ai/laifaxin-ai-account-connection）带你去拿。
- **② 你想卖的产品，一句话说清楚**。回答四个问题就行：卖什么？给谁用？卖到哪？凭什么买？比如"不锈钢保温杯，卖美国商超，工厂直供价格低"。
- **③ 一台电脑**。Mac 或 Windows 都行。
- **④ 一个会动手的 AI 助手**。这些都能用：**workbuddy / ZCode / DSH（＝DeepSeek Harness）/ Codex / Claude Code / Claude Desktop** 等（会自己动手的 AI 助手，任选其一，**免费可用版即可**；它们会直接读本仓库文件、执行命令、带你走完流程）。不确定用哪个 → 看文末二维码/联系作者。

这套系统说到底就是：**"给 AI 看的操作说明书 + 现成的工具箱"**。你只负责跟 AI 聊天，动手的事（存邮箱、写开发信、建跟进计划）都交给它。

## 第三步：交给 AI 开始干

把仓库交给它，两种方式任选：

1. **给位置**：把第一步解压后的文件夹（或 ZIP 文件）路径直接告诉它；
2. **发链接**：直接发 https://github.com/tony-apan/laifaxin-b2b-sales（这些助手能自己下载/读文件，不用你复制内容）。

然后对它说这一句：

> 「我卖的是 XXX（一句话产品说明），帮我找外国买家。」

比如：「我卖的是不锈钢保温杯，给海外商超供货，帮我找外国买家。」

AI 会先读 RULES.md（详细规则）和 SKILL.md（操作入口），你不用先读，它会一句句带你——包括带你把来发信账号的"钥匙"（token）拿到手。记住：token＝你的账号钥匙，只发给你信任的 AI，不要发到群里、工单或公开网页，也不要写进文件。

**它还会主动帮你建立两份本地档案（分两轮问，不在开局一次列清单）：**

| 档案 | AI 会主动问什么 | 存哪里 | 后续用途 |
|---|---|---|---|
| 公司级档案 | 公司名、官网/目录、你自己的联系邮箱、默认市场/语言（可跳过） | `.local/operators/<operator_key>.md`（多公司各一份；旧版 `.local/operator-profile.md` 兼容读取） | 换产品不用重复问；换机随 `.local/` 迁移 |
| 产品级档案 | 产品线、卖点、认证、产能、MOQ、交期、价格带（可跳过） | `runs/<operator_key>/<product_key>/product-profile.md` | S2客群、S4审计、S7正文卖点、S9钩子绑定版本/hash |

> 邮件末尾**签名区永远只有你的纯个人昵称**。公司名/官网/邮箱不进签名；经你确认且有来源的认证、产能、MOQ、交期等产品事实，可以用于邮件正文卖点。潜在客户/联系人第三方资料不会被要求写进上述档案。

## 它帮你做什么（思路）

一句话：你负责说卖什么，它负责把"谁可能买、怎么联系、怎么跟进"全部想到、做好、排好队。

1. **找相似客户**——你给它一家认得的买家网站（种子＝你认得的一家样板公司，系统照着它去找相似的），它顺着线索找出成百上千家"长得像"的外国买家。
2. **AI 做初筛审计**——它抽查公司资料，判断这批公司是否符合目标买家画像，并划出一条内部 70% 保存边界。这个数字是**名单筛选阈值，不是客户购买概率，也不是质量保证**；临界附近仍要逐条人工/AI 语义复核。
3. **保存他们的邮箱**——把合格公司的邮箱存进你的来发信账号（每家公司最多 3 个，特殊情况可升到 6/9）。
4. **自动写英文开发信 + 12 轮跟进**——每一轮 10 种不同写法（变体＝同一封邮件换个写法；序列＝按时间排好队的一组跟进邮件），10 变体 × 12 轮＝120 封，不用你憋英文。
5. **全部排进计划，等你确认**——这些信按时间排成 12 步跟进表，**不会自动发出去**，你看完点头它才动。

整个过程里，你只需要回答一句话：

> 你只需要回答：**确认 / 否 / 要改什么**

**它不会自动发信。** 另外说明：系统默认排除中国大陆、香港、澳门、台湾的客户——你要找的是外国买家。

## 📚 想看详细逻辑？在这几个文件里

| 文件 | 里面是什么 |
| --- | --- |
| [RULES.md](RULES.md) | 规则总纲——**唯一真源**：完整状态机 S0–S12、铁律、审批闸门（动手前必须你点头的手续） |
| [SKILL.md](SKILL.md) | 给 AI 的入口路由 |
| [specs/](specs/) | 环境准备、换机续接、产品知识档案、接口规范、70% 临界、序列配置、域名规模化 SOP |
| [methodology/](methodology/) | 决策树 / 最佳实践 / 检查清单 |
| [docs/](docs/) | 面向人的教程（第 03、08 篇带"过时横幅"，以 RULES/specs 为准；**第 09 篇讲广撒网成本账、询盘背调与多渠道精准跟进**） |
| [output-templates/](output-templates/) | 17 个输出话术模板（AI 照模板向你展示与确认） |
| [runs/_template/](runs/_template/) | 新案例起始模板 |

简单说：README 是门口指引，RULES.md 是详细逻辑，specs/ 是每条逻辑的技术细节——新手都不用先读，AI 会用。

## 常见问题

- **不会用命令行怎么办？** 完全不用学。走「第一步」的办法 B（Download ZIP），或者全程让 AI 替你做——你只管聊天和点头。
- **Windows 能用吗？** 能。选"ZIP 方式 + AI 代劳"最省事；想自己敲命令跑，需要先装 Git Bash 或 WSL（附录有说明）。
- **发了就能成单吗？** 不能保证。这是广撒网：量大 → 筛出询盘信号 → 询盘后的背调、精准跟进、谈判和成单靠业务员。系统不承诺回复率，也不保证询盘或订单。
- **支持卖什么？** 适用于合法且符合目标市场、平台规则和行业要求的 B2B 产品。医疗器械、金融、酒类、烟草、儿童产品、受制裁或受管制品类，开始前须做专项合规核查。**市场形状上的边界**：本系统适合**买家多、决策快、有渠道商**的产品；大宗原料/长周期项目制/需招标认证入围/全市场买家很少的品类，回询盘以月/年计，广撒网只能低成本摸底，不能替代渠道与展会（详见 [specs/product-fit.md](specs/product-fit.md)）。
- **会乱发信吗？** 不会：每一步都要你确认；最后一步默认停留在"测试待确认"状态——你不说"激活"，它就一个字都不发。
- **要另外花钱吗？** 工具和说明书完全免费（开源，GPL-3.0），你只需要付来发信账号的钱。
- **卡住了 / 看不懂？** 直接问 AI：「按 RULES.md 走」，它会按说明书带你走；也可以回来看本文件。

## 给技术朋友（附录）

### 🔧 运行

| 项 | 说明 |
|---|---|
| 主流程依赖 | **零第三方** —— Python 3 标准库 + curl + bash（macOS / Linux 开箱即用）|
| 运行命令 | macOS/Linux 用 `python3`；Windows（Git Bash 或 WSL 里）若 `python3` 没找到，多半有 `py`——用 `py` 代替 `python3`，装 Python 时勾选『Add python to PATH』最省事 |
| Windows | 用 **PowerShell + winget** 自动准备 Python/Git，或 Git Bash/WSL；⚠️ `bootstrap.ps1` 当前仅通过静态检查，尚未在全新 Windows 实机跑完，失败时按 environment-setup.md 的官方安装兜底 |
| 复现研究脚本 | 才需要 `pip install -r requirements.txt`（Playwright；相关研究脚本不随库分发）|

> 🔧 自行体检：跑 `python3 tools/onboard_check.py`（Windows 若无 python3 就用 `py tools/onboard_check.py`），它会自动探测 python/py/curl/bash 等，缺哪个就提示安装哪个（含 Windows 何时用 `py`）。

### 📁 目录导览

| 目录/文件 | 是什么 |
|---|---|
| [RULES.md](RULES.md) | 规则唯一真源 |
| [SKILL.md](SKILL.md) | AI 入口路由 |
| [specs/](specs/) | 接口规范 |
| [tools/](tools/) | 随库工具（工具＝规则）|
| [docs/](docs/) | 面向人的教程 |
| [runs/_template/](runs/_template/) | 新案例起始模板 |
| [glossary/](glossary/) · [wiki/](wiki/) · [lessons/](lessons/) | 术语表 · FAQ · 教训库（编号已脱敏抽象）|

### ⚖️ 发布与合规

- **许可证**：**GPL-3.0**，全文见 [LICENSE](LICENSE)。第三方教程原文与未授权截图不随库分发。
- **真实案例说明**：本库保留少量真实运行示例——种子域名（rivergear.com、nookie.co.uk、thermospromo.com、theboatpeople.org 等）与结果数量（6500 家、10211 邮箱、Jaccard 0.61 等，Jaccard 是衡量两篇文字相似程度的指标）为作者当时实际运行结果，**仅作方法演示，与读者业务无关**；其余租户/账号相关信息均以占位符出现。
- **隐私与脱敏**：不含真实租户 ID、客户/联系人邮箱、标签/序列/模板 ID、运营方姓名、审批编号——一律占位符；内部分析记录（dialogue/、runs/tony/、db/issues.tsv 等）不随库分发。**公开发布只允许使用 Git 已跟踪文件或 GitHub Release/Download ZIP，不要打包整个本地工作目录**；本地 `.local/` 与 `runs/<你的名字>/` 可能含真实运营数据。

### 🔒 安全边界

- **审批闸门防呆不防恶**：AI 自己写的"确认"不等于你的授权；高风险操作（保存 / 建序列 / 加联系人 / 激活）必须在对话中出示用户原话，AI 自行记录的凭证视为无效。
- **本地数据只在你电脑上**：`.local/`（审批流水）、`runs/`（你的运营档案）含你的账号活动痕迹，不要把这个文件夹整体发给他人或公开；分享/交付只走本公开仓库（无运营数据）。
- **平台与运营方责任分开**：来发信系统通道负责 SPF / DKIM / DMARC、发送基础设施和退订技术呈现；运营方仍须在激活前核验目标市场规则、名单来源、发送主体信息、实际退订入口、拒收名单和数据处理要求。平台提供技术能力，**不等于运营方免除合规责任**。
- **激活接口**：`sequence-active` 早期曾返回 500（2026-09-02 单次实测恢复）；激活一律走 `tools/activate_sequence.py` 并回读状态确认。

---

## 版本与下载

- [下载最新版 / 查看完整发布说明](https://github.com/tony-apan/laifaxin-b2b-sales/releases/latest)
- [查看所有历史版本](https://github.com/tony-apan/laifaxin-b2b-sales/releases)
- [查看开发者变更记录](CHANGELOG.md)

版本细节统一放在 GitHub Releases，README 不重复版本细节、只放入口链接。

## 🔄 更新到新版本（老用户）

> 更新**不会动你的本地数据**：`.local/`（审批凭证）和 `runs/` 里你的运营档案（`runs/<你的名字>/`）都不在仓库里——升级只替换规则和工具。

**办法 A（推荐，快又稳）：把下面整段复制发给 AI**

```text
请帮我把这套外贸获客系统更新到最新版，保留我本地所有数据。

第 1 步｜判断我的安装方式（你自己判断，判断不出再问我）：
· 我的系统文件夹里有 .git 文件夹（当初是 git 克隆安装的）→ 按 git 方式更新；
· 没有 .git（当初是下载 ZIP 解压安装的）→ 按 ZIP 方式更新。

第 2 步｜找到我的系统文件夹：
· 如果我已经把本地文件夹路径发给你了，就用那个路径；
· 找不到就问我，不要猜一个路径。

第 3 步｜更新前先备份本地数据（必做，最便宜的保险）：
· 把 .local/（审批凭证）和 runs/（客户档案）各复制一份到系统文件夹外面
  （比如桌面或上级目录），命名如 backup-20260903/；
· 复制完核对数量能对上，再继续；更新成功、数据完好后才可删备份。

第 4 步｜按安装方式更新：
· git 方式：在我的系统文件夹里执行 git pull，拉取最新版；
  如果提示本地有修改/冲突，不要强推、不要删任何文件，停下把情况告诉我；
· ZIP 方式：下载最新版 https://github.com/tony-apan/laifaxin-b2b-sales/releases/latest
  的 ZIP，解压后把里面的文件【覆盖】进我的原系统文件夹（用新版文件替换旧版同名文件）。
  ★硬规则：绝不能解压成一个新文件夹让我改用新的——那会让我找不到本地数据。

第 5 步｜ZIP 方式更新后检查残留（git 方式跳过）：
· 如果我的系统文件夹里有"新版里不存在"的旧文件（新版已删除的），先列出来问我，
  我确认后再清理；不要自己删任何我不认识的文件。

第 6 步｜更新完复查环境、体检并汇报：
· Windows PowerShell 跑 `powershell -NoProfile -ExecutionPolicy Bypass -File tools/bootstrap.ps1 -CheckOnly`；
  macOS/Linux/Git Bash/WSL 跑 `bash tools/bootstrap.sh --check-only`；有缺失先按 environment-setup.md 修复；
· 用 bootstrap 输出的 `python_cmd` 运行 `tools/onboard_check.py` 自检；
· 告诉我：更新到了哪个版本（对照 CHANGELOG.md 顶部）？这次更新了什么
  （读 CHANGELOG 最新几条，用通俗中文讲，重点讲流程/话术有没有变化）？
· 确认 .local/ 和 runs/ 都完好（对照第 3 步的备份数量）；
· 如果我隔了很多版本才更新，把中间几个大版本的变化也简单汇总给我。
```

**办法 B（想更省事）：只说一句也可以**
> 「帮我把这个获客系统更新到最新版，保留我的数据。」

剩下的 AI 会照办法 A 里的步骤自己做（判断 git/ZIP → 原目录覆盖 → 保数据 → 体检汇报）。你全程只需要回复「可以」或「继续」。

## 💻 换电脑继续干（老用户）

> **换电脑 ≠ 重新安装后从头跑。** GitHub 仓库只有规则和工具；你的当前节点、审批流水、产品档案与运行记录保存在旧电脑的 `.local/`、`runs/<operator_key>/` 和可选本地 `db/` 数据表，必须一并迁移。token 不迁移，在新电脑重新获取。备份与恢复都**只针对本地数据**（`.local/`、`runs/<运营方>/`、`db/` 中本地新增的表），不打整个 `runs/`、`db/`——仓库自带的模板与索引（`runs/_template/`、`db/docs.tsv` 等）以新机版本为准。

**旧电脑：把下面整段复制给 AI**

```text
请帮我为“来发信 B2B 获客系统”做换机备份：
1. 找到当前系统文件夹，先读 specs/migration-handoff.md；找不到路径就问我，不要猜。
2. 只备份本地数据：.local/（整目录）、runs/ 下我自己的运营方目录（★排除 runs/_template 和 runs/INDEX.md）、db/ 里本地新增未入库的数据表（★仓库自带的 db/docs.tsv、db/tools.tsv 不带）。
3. 不把 token、浏览器缓存、系统钥匙串或仓库规则文件混进备份；不要把备份上传到公开仓库。
4. 把备份包放到系统文件夹外，命名 `laifaxin-backup-<日期>.tar.gz`（Windows 为 `.zip`），逐项核对源/包内文件数和大小；备份包里不应出现 _template/INDEX.md/docs.tsv/tools.tsv。
5. 最后告诉我：备份路径、包含哪些目录、发现哪些可续接项目及其当前 status；不要改动原项目。
```

**新电脑：装好最新版后，把备份放到电脑上，再把下面整段复制给 AI**

```text
请按“换机续接”接手这套来发信 B2B 获客系统，不要从 S0 重跑已有项目：
1. 先读 README.md、SKILL.md、RULES.md、specs/environment-setup.md、specs/migration-handoff.md。
2. 自动准备环境：
   · Windows PowerShell：powershell -NoProfile -ExecutionPolicy Bypass -File tools/bootstrap.ps1 -Install
   · macOS/Linux/Git Bash/WSL：bash tools/bootstrap.sh --install
   安装后必须再跑 check-only，全部通过才继续。
3. 找到我从旧电脑带来的 `laifaxin-backup-<日期>.tar.gz/.zip` 备份包，先解到临时目录列出内容让我核对；确认后只按白名单恢复：
   .local/、runs/<运营方>/（不碰 runs/_template 和 runs/INDEX.md）、db/ 里本地新增的数据表（不覆盖 db/docs.tsv、db/tools.tsv 等已跟踪文件）。
   不要覆盖 README/RULES/SKILL/specs/tools；git安装用 git status 确认自带文件未变，ZIP安装则与新下载包清单/hash对比确认。
4. 用 bootstrap 输出的 python_cmd 运行 tools/onboard_check.py，列出全部可续接项目、operation-record status、product-profile 版本/确认状态/更新时间。
5. 让我选择项目；读取 `.local/operators/<operator_key>.md`（旧单文件兼容）和项目的 operation-record/product-profile/reflection/evidence/verify-*，报告“当前节点/已完成/未完成/下一步”。
6. token 不从旧机迁移，带我在新机浏览器重新获取，再跑 check_login.py 和 gate_check.sh。
7. 恢复后立即运行 `approval.py demote-migrated --confirm MIGRATION-DEMOTE`，把所有旧 confirmed 凭证降为 backfilled（只审计不可授权）；未执行的写操作与S12在新机当前对话重新确认。
8. 只从记录的当前节点继续；禁止重新建已有产品档案、重复保存、重复建模板或序列。任何记录不一致先进入 ERROR_BLOCKED，只读核对后再处理。
9. 最后汇报：环境结果、恢复目录、项目与状态、profile 版本/hash、token复验、下一步和仍需我确认的动作。
```

详细迁移标准见 [specs/migration-handoff.md](specs/migration-handoff.md)。

---

## 📮 联系与关注

<img src="https://cos.files.maozhishi.com/data/web/web-files/wx/tony-apan.png" width="160" alt="作者二维码">

扫码关注/联系作者（微信），使用中遇到问题可以来问。

---

许可证：GPL-3.0 · 反馈：[GitHub Issues](https://github.com/tony-apan/laifaxin-b2b-sales/issues)
