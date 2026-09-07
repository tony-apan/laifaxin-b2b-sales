# Token 获取引导（一条命令：账号钥匙+工作空间ID 一次全拿）
```
【第一步：连接您的来发信账号】

需要两样东西（一条命令一次全拿到），只要 1 分钟：

1. 用 Chrome 或 Edge 打开 web.laifaxin.com 并登录
2. 确认右上角头像里切换到**您要用的账号**（个人或企业）——切错空间=白干
3. 在页面按右键 → 点"检查"（Mac 是 ⌥Option+⌘I）
4. 顶部点「Console / 控制台」标签
5. 粘贴这一行并回车：
   var t=localStorage.getItem("accesstoken");t&&t!=="null"?(copy("accesstoken="+t+"\norgId="+localStorage.getItem("orgId")),"✅ 已复制到剪贴板！回到对话框 Ctrl+V（Mac按⌘V）粘贴发送给 AI"):(location.host.indexOf("laifaxin")<0&&location.host.indexOf("worldtradetool")<0?"❌ 你现在打开的网页（"+location.host+"）不是来发信——新开标签页访问 web.laifaxin.com 并登录，再按 F12 打开控制台重新粘贴本命令":"❌ 来发信页面上没取到登录凭证——先看右上角有没有你的账号头像：没有=先登录；有=按 F5 刷新后再运行一次（不用退出重登）");
   （成功回显 ✅ 已复制到剪贴板！；回显 ❌ 时命令会写明原因——多半是网页没开对，照提示做即可——不会再出现多余的 undefined）
6. 回到这里整段粘贴给我（Ctrl+V / ⌘V）——不用拆分，我能自动识别

复制出来的两行字段名（accesstoken= / orgId=）与页面存储键名一一对应，AI 拿到就知道哪个是哪个。

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
- 用户粘贴的整段含 `accesstoken=` 和 `orgId=` 两行（字段名=页面存储键名，AI 直接对应）——**原样传给 `check_login.py --token '<整段>'`**，工具自动拆分，**不要自己转述拆解**（防转述出错）
- accesstoken/orgId 任一为 null → 网页没开对或未登录（命令 ❌ 会区分提示）：先按 ❌ 提示把网页开对/刷新，**别一上来就让用户退出重登**——单点有效机制下多余的重登会把还能用的 token 作废
- **orgId=工作空间ID**（localStorage `orgId` 键）：个人账号=用户ID本身；**企业账号是独立数字ID**——API `?uid=` 一律用它
- token 中段=用户ID（切换 org 不变）；不能用 token 中段当企业 orgId
- 用户只发 token 没带 ORG → 先确认是个人账号再回退 token 中段；有企业org嫌疑一律补问
- 切换账号/企业后：重新执行复制命令
- 检查用 check_login.py（只读）；三类失败分流：网络不通≠token 失效、复制不全、接口间歇空
- 连接成功后按 S0-连接成功.md 展示账号状态（含 org 信息）
- token 等同账号密码：只发信任 AI、不发群聊、不写入文件

## 昵称规范提示（拿到 token 后问昵称时一并说）
- 昵称只放**个人称呼**（如 Tony / Iris）；公司名、产品名、职位不放昵称里——会显得像群发
- 含公司/产品的昵称（如 "Iris | XX Textiles"）→ 请用户改成纯人名，一句话说明即可
