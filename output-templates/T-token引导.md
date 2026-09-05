# Token 获取引导（账号钥匙 + 工作空间ID）
```
【第一步：连接您的来发信账号】

需要您账号的"钥匙"（token）和工作空间ID（orgId），获取只要 1 分钟：

1. 用 Chrome 或 Edge 打开 web.laifaxin.com 并登录
2. 确认右上角头像里切换到**您要用的账号**（个人或企业）——多组织用户切错空间=白干
3. 在页面按右键 → 点"检查"（Mac 是 ⌥Option+⌘I）
4. 顶部点「Console / 控制台」标签
5. 依次粘贴这两行，每行回车：
   copy(localStorage.getItem("accesstoken"));   ← 账号钥匙（第一样）
   copy(localStorage.getItem("orgId"));         ← 工作空间ID（第二样）
   （每行显示 undefined = 已复制成功）
6. 回到这里把两样都粘贴给我（Ctrl+V / ⌘V）

⚠️ 小提示：
- 粘贴代码时浏览器可能提示 "Don't paste code"——按提示输入 allow pasting 再粘
- token 等同账号密码，只发给你信任的 AI，别发群里
- 拿到 null = 还没登录，先登录再试
- 🔴 切换过账号/企业后，两样都要重新复制（token 不变但 orgId 会变）
- 图文教程：https://www.laifa.xin/share/ai/laifaxin-ai-account-connection
```

## AI 执行要点与边界
- token 等同账号密码：只发信任 AI、不发群聊、不写入文件
- **orgId=工作空间ID**（localStorage `orgId` 键）：个人账号=用户ID本身；**企业账号是独立数字ID，必须显式获取**——API 的 `?uid=` 一律用它
- token 中段=用户ID（切换 org 不变）；**不能用 token 中段当企业 orgId**
- 用户只发 token 没发 orgId → 先确认是个人账号再回退 token 中段；有企业org嫌疑一律补问 orgId
- 切换账号/企业后：token+orgId 两样都重新复制
- 检查用 check_login.py（只读）；三类失败分流：网络不通≠token 失效、复制不全、接口间歇空
- 连接成功后按 S0-连接成功.md 展示账号状态（SVIP 映射/配额/充值/org 信息）
- 新账号引导照模板话术，含 Don't paste code 防骗提示

## 昵称规范提示（拿到 token 后问昵称时一并说）
- 昵称只放**个人称呼**（如 Tony / Iris）；公司名、产品名、职位不放昵称里——会显得像群发
- 含公司/产品的昵称（如 "Iris | XX Textiles"）→ 请用户改成纯人名，一句话说明即可
