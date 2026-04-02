# Comobot 安装指南

本文档分两部分：
- **用户安装**：面向普通用户的三种安装方式
- **打包发布**：面向开发者的打包命令与发布流程

---

## 用户安装

### 方式一：脚本一键安装（Mac / Linux）

在终端粘贴一条命令，自动完成所有依赖安装、服务启动，并在浏览器打开配置向导：

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/musenming/comobot-install/main/scripts/install.sh | sh)"
```

**系统要求**：macOS 12+（Monterey）或 Ubuntu 20.04+ / CentOS 8+，需要联网

脚本会自动完成：
1. 安装 Homebrew（macOS）/ 使用 apt/yum（Linux）
2. 安装 Python 3.11 和 Node.js 18
3. 下载最新 Release 并解压到 `~/Applications/comobot/`（macOS）或 `~/.local/comobot/`（Linux）
4. 创建虚拟环境并安装 Python 依赖
5. 构建前端静态资源
6. 配置开机自启（macOS LaunchAgent / Linux systemd）
7. 在桌面创建快捷方式
8. 启动服务，打开浏览器 `http://localhost:18790`

---

### 方式二：脚本一键安装（Windows）

**方法 A**：PowerShell（推荐，Win10 1903+ / Win11）

```powershell
irm https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.ps1 | iex
```

**方法 B**：下载 `install.bat`，右键 → 以管理员身份运行

```
https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.bat
```

脚本会自动完成：
1. 用 `winget` 安装 Python 3.11 和 Node.js 20.19+ or 22.12+
2. 下载最新 Release 并解压到 `%APPDATA%\comobot\`
3. 创建虚拟环境并安装依赖
4. 构建前端静态资源
5. 注册开机启动项（注册表）
6. 在桌面创建快捷方式（`.lnk`）
7. 启动服务，打开浏览器 `http://localhost:18790`

---

### 方式三：Docker（本地 Docker 环境）

**前提**：已安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)

**macOS**：下载 `comobot-docker.zip`，解压后双击 `start.command`

**Windows**：下载 `comobot-docker.zip`，解压后双击 `start.bat`

或者手动执行：

```bash
# 下载编排文件
curl -fsSL https://github.com/musenming/comobot/releases/latest/download/comobot-docker.zip -o comobot-docker.zip
unzip comobot-docker.zip && cd comobot-docker

# 启动服务（首次会拉取镜像，约 1-2 分钟）
docker compose up -d

# 查看运行状态
docker compose ps

# 打开浏览器完成向导
open http://localhost:18790   # macOS
# 或手动访问 http://localhost:18790
```

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

# 重启
comobot gateway restart
```

---

