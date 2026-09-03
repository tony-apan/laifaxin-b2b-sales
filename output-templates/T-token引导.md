# Token 获取引导（账号钥匙）
```
【第一步：连接您的来发信账号】

需要您账号的"钥匙"（token），获取只要 1 分钟：

1. 用 Chrome 或 Edge 打开 web.laifaxin.com 并登录
2. 在页面按右键 → 点"检查"（Mac 是 ⌥Option+⌘I）
3. 顶部点「Console / 控制台」标签
4. 粘贴这一行并回车：
   copy(localStorage.getItem("accesstoken"));
   （显示 undefined = 已复制成功）
5. 回到这里直接粘贴给我（Ctrl+V / ⌘V）

⚠️ 小提示：
- 粘贴代码时浏览器可能提示 "Don't paste code"——按提示输入 allow pasting 再粘
- token 等同账号密码，只发给你信任的 AI，别发群里
- 拿到 null = 还没登录，先登录再试
```
