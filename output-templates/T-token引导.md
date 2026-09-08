# Token 获取引导（浏览器一键复制 → 当前聊天框直接粘贴）
```
【第一步：连接您的来发信账号】

需要两样东西，但您不用拆分、设置变量或执行工具命令，只要 1 分钟：

1. 用 Chrome 或 Edge 打开 web.laifaxin.com 并登录
2. 确认右上角头像里切换到**您要用的账号**（个人或企业）——切错空间=白干
3. 在页面按右键 → 点"检查"（Mac 是 ⌥Option+⌘I）
4. 顶部点「Console / 控制台」标签
5. 粘贴这一行并回车：
   var t=localStorage.getItem("accesstoken");t&&t!=="null"?(copy("accesstoken="+t+"\norgId="+localStorage.getItem("orgId")),"✅ 已复制到剪贴板！回到对话框 Ctrl+V（Mac按⌘V）粘贴发送给 AI"):(location.host.indexOf("laifaxin")<0&&location.host.indexOf("worldtradetool")<0?"❌ 你现在打开的网页（"+location.host+"）不是来发信——新开标签页访问 web.laifaxin.com 并登录，再按 F12 打开控制台重新粘贴本命令":"❌ 来发信页面上没取到登录凭证——先看右上角有没有你的账号头像：没有=先登录；有=按 F5 刷新后再运行一次（不用退出重登）");
   （成功回显 ✅ 已复制到剪贴板！；回显 ❌ 时命令会写明原因——多半是网页没开对，照提示做即可——不会再出现多余的 undefined）
6. 回到**当前 AI 聊天框**，直接粘贴并发送（Ctrl+V / ⌘V）

复制出来是带字段名的两行：`accesstoken=...` 和 `orgId=...`。整段直接发给我即可：**不用拆分、不用设置 TOKEN/ORG 变量、不用创建 `.env`、不用运行 Python 或 Shell 命令。**

⚠️ 小提示：
- 粘贴代码时浏览器可能提示 "Don't paste code"——按提示输入 allow pasting 再粘
- token 等同账号密码，只发给你信任的 AI，别发群里
- 拿到 null = 还没登录，先登录再试
- 🔴 切换过账号/企业后要重新复制（orgId 会变）
- 🔴 **token 单点有效**：在其他设备/浏览器登录，或网页重新登录 → 旧 token 立即作废（同一份反复贴没用，必须重取）
- ℹ️ token 开头域名可能是 web.laifaxin.com 或 web.worldtradetool.com 等——都正常，不影响
- 图文教程：https://www.laifa.xin/share/ai/laifaxin-ai-account-connection
```

## AI 执行要点与边界
- 用户在浏览器复制后，只需把 `accesstoken=` + `orgId=` 两行整段直接粘贴到当前聊天框；**禁止要求用户设置环境变量、创建 `.env`、执行工具命令、拆分或改写参数**
- 主 AI 收到后不回显完整 token、不写文件/日志/持久环境变量；通过宿主提供的**程序化 stdin**（如 subprocess `input=`/`communicate()`）原样交给 `check_login.py --credentials-stdin`。禁止用 heredoc、`printf |` 或把凭据拼进 Bash 工具调用文本，避免进入命令历史/工具日志
- accesstoken 或 orgId 任一缺失/null → 停止连接，不得回退 token 中段或默认个人空间；让用户回浏览器重新执行同一条一键复制命令后，再把新的两行整段发到聊天框
- **orgId=工作空间ID**（localStorage `orgId` 键）：个人账号=用户ID本身；**企业账号是独立数字ID**——API `?uid=` 一律用它
- token 中段=用户ID（切换 org 不变）；不能用 token 中段当企业 orgId
- 用户只发 token、没带 orgId → 必须停止并让用户重新一键双取；禁止按个人账号回退
- 切换账号/企业后：重新执行复制命令
- 主 AI 自己运行只读 `check_login.py --credentials-stdin`；网络失败、复制不全、接口间歇空、token失效四类原因按工具提示分流，不把内部命令交给用户
- 连接成功后按 S0-连接成功.md 展示账号状态（含 org 信息）
- token 等同账号密码：只直接粘贴到当前受信任、正在本机操作的主 AI 聊天框，不发群聊/子代理/工单/公开页面。仓库工具不主动回显或落盘原始凭据，也不写 `.env`/日志；仅在失效时于本机 `.local/` 保存不可还原的短哈希和重试次数。聊天服务是否保存对话取决于所用 AI 的隐私与数据保留政策

## 昵称边界
- 新获客项目通常已在 S0 获取纯个人昵称，连接账号后不要重复问
- 如果当前任务只是适配判断、网站提炼或流程了解，本来不需要昵称/token；不得为了套流程额外索取
- 真正生成邮件时，昵称只放个人称呼（Tony / Iris 等）；公司名、产品名、职位不进入昵称或签名
