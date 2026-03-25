---
name: comobot_remote
description: 连接/配置 Comobot Remote App。当用户说"连接remote"、"配置remote"、"connect remote"、"pair remote"等类似意图时触发。
metadata: {"comobot":{"emoji":"📱"}}
---

# Comobot Remote 连接

当用户表达以下意图时，立即触发此技能：
- 中文：**连接remote、配置remote、连接手机、手机连接、remote连接、远程连接、配对remote、配对手机、生成配对码、生成二维码连接**
- English: **connect remote, pair remote, setup remote, link remote, remote pairing, pair phone, connect phone, generate pairing qr**

## 执行步骤

### 生成配对二维码

在终端执行以下命令：

```bash
comobot connect remote
```

该命令会：
1. 生成一个包含服务器地址和临时密钥的配对令牌（有效期 5 分钟）
2. 在终端显示二维码（需安装 `qrcode` 库）
3. 自动等待手机扫码确认

**常用选项：**

- 指定服务器公网地址（默认自动检测局域网 IP）：
  ```bash
  comobot connect remote --url https://your-domain.com
  ```

- 指定 Gateway 端口（默认 18790）：
  ```bash
  comobot connect remote --port 8080
  ```

- 仅生成二维码，不等待扫码结果：
  ```bash
  comobot connect remote --no-poll
  ```

### 手机端操作

告知用户：
1. 打开 **Comobot Remote** App
2. 点击 **Scan to Connect**
3. 扫描终端中显示的二维码
4. 等待连接成功提示

### 管理已连接设备

- 查看已配对设备列表：
  ```bash
  comobot connect list
  ```

- 移除已配对设备：
  ```bash
  comobot connect remove <device_id>
  ```

## 注意事项

- 二维码有效期为 **5 分钟**，过期后需重新生成
- 手机和电脑需在**同一网络**下，或使用 `--url` 指定可访问的公网地址
- 配对成功后，手机通过加密 WebSocket 与 Comobot 通信，所有数据 NaCl 端对端加密
- 如果终端未显示二维码图案，请安装：`pip install qrcode`
- Gateway 必须处于运行状态（`comobot gateway`）才能让手机正常通信
