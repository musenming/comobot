# Comobot 安装指南

本文档分两部分：
- **用户安装**：面向普通用户的三种安装方式
- **打包发布**：面向开发者的打包命令与发布流程

---

## 用户安装

### 方式一：脚本一键安装（Mac / Linux）

脚本自动检测网络环境，国内用户自动切换至 `dl.comindx.com` 镜像下载，无需手动选择。

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.sh)"
```

**国内用户**（GitHub 不可达时可直接使用镜像）：

```bash
/bin/bash -c "$(curl -fsSL https://dl.comindx.com/scripts/install.sh)"
```

**系统要求**：macOS 12+（Monterey）或 Ubuntu 20.04+ / Debian 11+，需要联网

脚本会自动完成：
1. 检测平台（linux-x64 / linux-arm64 / macos-arm64）
2. 从 GitHub Releases 或国内镜像下载对应预编译二进制包
3. 安装到 `~/.comobot/bin/comobot`，并写入 PATH
4. 首次运行 `comobot onboard` 完成初始化配置

安装完成后启动服务：

```bash
comobot gateway
```

---

### 方式二：脚本一键安装（Windows）

以管理员身份打开 PowerShell，粘贴以下命令：

```powershell
irm https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.ps1 | iex
```

**国内用户**：

```powershell
irm https://dl.comindx.com/scripts/install.ps1 | iex
```

**系统要求**：Windows 10 1903+ / Windows 11，PowerShell 5.1+

脚本会自动完成：
1. 检测平台（windows-x64）
2. 从 GitHub Releases 或国内镜像下载预编译二进制包
3. 安装到 `%LOCALAPPDATA%\comobot\bin\comobot.exe`，并写入用户 PATH
4. 首次运行 `comobot onboard` 完成初始化配置

安装完成后启动服务：

```powershell
comobot gateway
```

---

### 方式三：Docker（本地 Docker 环境）

**前提**：已安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)

从 GitHub Releases 下载 `comobot-docker.zip`，解压后：

- **macOS**：双击 `start.command`
- **Windows**：双击 `start.bat`

或者手动执行：

```bash
curl -fsSL https://github.com/musenming/comobot/releases/latest/download/comobot-docker.zip -o comobot-docker.zip
unzip comobot-docker.zip && cd comobot-docker

# 启动服务（首次会拉取镜像，约 1-2 分钟）
docker compose up -d

# 查看运行状态
docker compose ps
```

打开浏览器访问 `http://localhost:18790` 完成向导。

数据持久化在 Docker Volume `comobot-data`，重启/升级均不丢失。

停止服务：

```bash
docker compose down
```

---

### 方式四：源码安装（开发者）

```bash
git clone https://github.com/musenming/comobot.git
cd comobot

python3.11 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"

# 构建前端
cd web && npm install && npm run build && cd ..

# 启动
comobot gateway
```

---


