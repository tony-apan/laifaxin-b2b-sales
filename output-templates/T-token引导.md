# Token 获取引导（一条命令：账号钥匙+工作空间ID 一次全拿）
```
【第一步：连接您的来发信账号】

需要两样东西（一条命令一次全拿到），只要 1 分钟：

1. 用 Chrome 或 Edge 打开 web.laifaxin.com 并登录
2. 确认右上角头像里切换到**您要用的账号**（个人或企业）——切错空间=白干
3. 在页面按右键 → 点"检查"（Mac 是 ⌥Option+⌘I）
4. 顶部点「Console / 控制台」标签
5. 粘贴这一行并回车：
   copy("TOKEN="+localStorage.getItem("accesstoken")+"\nORG="+localStorage.getItem("orgId"));
   （显示 undefined = 已复制成功，剪贴板里是两行：TOKEN=... 和 ORG=...）
6. 回到这里整段粘贴给我（Ctrl+V / ⌘V）——不用拆分，我能自动识别

⚠️ 小提示：
- 粘贴代码时浏览器可能提示 "Don't paste code"——按提示输入 allow pasting 再粘
- token 等同账号密码，只发给你信任的 AI，别发群里
- 拿到 null = 还没登录，先登录再试
- 🔴 切换过账号/企业后要重新复制（orgId 会变）
- 图文教程：https://www.laifa.xin/share/ai/laifaxin-ai-account-connection
```

## AI 执行要点与边界
- 用户粘贴的整段含 `TOKEN=` 和 `ORG=` 两行——**原样传给 `check_login.py --token '<整段>'`**，工具自动拆分，**不要自己转述拆解**（防转述出错）
- ORG=null → 未登录/页面不对，引导重登后重复制
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
