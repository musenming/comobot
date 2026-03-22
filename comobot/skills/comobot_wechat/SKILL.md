---
name: comobot_wechat
description: 微信登录/连接。当用户说"连接微信"、"login wechat"、"connect wechat"等类似意图时触发。
metadata: {"comobot":{"emoji":"💬"}}
---

# 微信登录

当用户表达以下意图时，立即触发此技能：
- 中文：**连接微信、链接微信、登陆微信、登录微信、微信登录、微信连接、配置微信、微信配置**
- English: **login wechat, connect wechat, wechat login, setup wechat, link wechat**

## 执行步骤

### 第一步：获取二维码

调用 `wechat_login` 工具获取二维码：

```
wechat_login(action="qr")
```

工具返回二维码（图片链接或 ASCII 文本）+ `QRCODE_TOKEN=xxx` 和 `UIN=xxx`。
将**完整的二维码内容**原样发送给用户，提示"请用微信扫描二维码登录"。
记下 QRCODE_TOKEN 和 UIN 值。

### 第二步：轮询扫码状态

用户扫码后（或等待几秒），调用：

```
wechat_login(action="poll", qrcode_token="<上一步的token>", uin="<上一步的uin>")
```

根据返回结果告知用户：
- **已扫码** — 告诉用户在微信上确认，然后再调用一次 poll
- **登录成功** — 工具会自动重启 gateway，告知用户"登录成功，gateway 即将重启以使微信通道生效"
- **已过期/超时** — 提示用户重新发起登录

## 注意事项

- 二维码有效期约 2-3 分钟
- 不要省略或截断二维码内容（图片链接或 ASCII 文本）
- 登录成功后凭证自动保存，微信通道自动启用，gateway 自动重启
- 用户也可以通过终端执行 `comobot channels login wechat` 完成登录
