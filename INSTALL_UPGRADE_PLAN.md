# Comobot 一键安装升级方案

## 背景与问题分析

### 当前安装痛点

| 步骤 | 技术门槛 | 非技术用户障碍 |
|------|----------|---------------|
| 安装 Python 3.11+ | 中 | 不知道版本区别，易装错 |
| 安装 Node.js 18+ | 中 | 不明白为什么需要两种运行时 |
| 克隆 Git 仓库 | 高 | 绝大多数非技术用户不会 Git |
| 创建虚拟环境 | 高 | 完全陌生的概念 |
| 手动编辑 JSON 配置文件 | 中 | 找不到文件，怕破坏格式 |
| 构建前端 (`npm run build`) | 高 | 不理解为何要"构建" |
| 启动服务 (命令行) | 高 | 没有图形界面入口 |

**结论**：当前方案假设用户具备开发者背景，完全不适合非技术用户。

---

## 目标体验

```
用户操作：双击安装包 → 填写 API Key → 点击启动 → 开始使用
耗时：< 5 分钟
技术门槛：零（等同于安装微信）
```

---

## 升级方案总览

采用**两层方案**并行推进，按优先级排序：

| 优先级 | 方案 | 适用场景 | 实现周期 |
|--------|------|----------|----------|
| P0 | 脚本一键安装 + Web 配置向导 | 有网络的 Mac/Windows 用户 | 1-2 周 |
| P1 | Docker Desktop 桌面应用封装 | 有 Docker 环境或愿意装 Docker 的用户 | 2-3 周 |

---

## P0 方案：脚本一键安装 + Web 配置向导（优先实现）

### 核心思路

用户运行**一条命令**（Mac）或**双击一个脚本**（Windows），自动完成所有依赖安装、服务启动，然后在浏览器中通过**图形化向导**完成配置。

### Mac 安装流程

```bash
# 用户在终端运行这一条命令即可
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.sh)"
```

**脚本自动完成：**

```
1. 检测 macOS 版本（要求 12+）
2. 检测并安装 Homebrew（如缺失）
3. 检测并安装 Python 3.11（通过 Homebrew）
4. 检测并安装 Node.js 18（通过 Homebrew）
5. 下载 comobot 最新 release（zip，非 git clone）
6. 创建虚拟环境并安装 Python 依赖
7. 构建前端静态资源
8. 创建 ~/.comobot/ 数据目录
9. 创建 macOS 启动项（LaunchAgent plist）
10. 写入桌面快捷方式（.command 文件）
11. 自动打开浏览器 → http://localhost:18790/setup
```

### Windows 安装流程

提供 `install.bat` 或 PowerShell 脚本，用户**右键 → 以管理员身份运行**：

```powershell
# PowerShell 一键安装（用户在 PowerShell 运行）
irm https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.ps1 | iex
```

**脚本自动完成：**

```
1. 检测 Windows 版本（要求 Win10 1903+）
2. 检测并用 winget 安装 Python 3.11
3. 检测并用 winget 安装 Node.js 18
4. 下载 comobot 最新 release（zip）
5. 解压到 %APPDATA%\comobot\
6. 创建虚拟环境并安装 Python 依赖
7. 构建前端静态资源
8. 注册 Windows 服务或创建开机启动项
9. 在桌面创建快捷方式（.lnk）
10. 自动打开浏览器 → http://localhost:18790/setup
```

### Web 配置向导（Setup Wizard）

这是 P0 方案的**核心新增功能**，在现有 Vue 3 前端基础上新增 `/setup` 路由，实现图形化首次配置。

#### 向导步骤设计

**Step 1：欢迎页**
```
欢迎使用 Comobot！
让我们花 2 分钟完成初始配置。
[开始配置 →]
```

**Step 2：选择 AI 提供商**
```
请选择您的 AI 服务：
○ OpenAI (ChatGPT)          → 需要 OpenAI API Key
○ Anthropic (Claude)         → 需要 Anthropic API Key
○ OpenRouter (多模型聚合)    → 需要 OpenRouter API Key  ← 推荐新手
○ 本地模型 (Ollama)          → 无需 API Key，需安装 Ollama

[如何获取 API Key？] （点击展开教程）
```

**Step 3：填写 API Key**
```
OpenRouter API Key：
[sk-or-v1-________________] [验证]

✅ 验证成功！可用余额：$5.00

选择默认模型：
[anthropic/claude-opus-4-5 ▼]
```

**Step 4：基础设置**
```
助手名称：[Comobot        ]
界面语言：[中文（简体）   ▼]
开机自启：[✅ 是          ]
```

**Step 5：完成**
```
🎉 配置完成！

Comobot 已在后台运行
访问地址：http://localhost:18790

[开始使用]
```

#### 向导后端 API

需新增以下 API 端点（在现有 FastAPI 路由基础上扩展）：

```python
POST /api/setup/validate-key     # 验证 API Key 可用性
POST /api/setup/complete         # 写入配置文件并重启服务
GET  /api/setup/status           # 查询是否已完成初始化
GET  /api/setup/providers        # 获取可用提供商列表
```

---

## P1 方案：Docker Desktop 封装

### 核心思路

利用 Docker Desktop（Mac/Windows 均有图形界面版本），提供 `docker-compose.yml` + 一键启动脚本，用户无需了解 Python/Node.js。

### 用户操作流程

```
1. 安装 Docker Desktop（官网下载，点击安装，约 5 分钟）
2. 下载 comobot-docker.zip，解压
3. 双击 start.command（Mac）或 start.bat（Windows）
4. 浏览器自动打开 → http://localhost:18790/setup
5. 完成向导配置
```

### 文件结构

```
comobot-docker/
├── docker-compose.yml       # 主编排文件
├── start.command            # Mac 启动脚本（双击运行）
├── start.bat                # Windows 启动脚本（双击运行）
├── stop.command             # Mac 停止脚本
├── stop.bat                 # Windows 停止脚本
└── README.txt               # 极简说明（3步）
```

### `docker-compose.yml` 设计

```yaml
services:
  comobot:
    image: ghcr.io/musenming/comobot:latest
    ports:
      - "18790:18790"
    volumes:
      - comobot-data:/root/.comobot
    restart: unless-stopped
    environment:
      - COMOBOT_FIRST_RUN=true

volumes:
  comobot-data:
```

### Dockerfile 设计要点

```dockerfile
FROM python:3.12-slim

# 多阶段构建：先构建前端
FROM node:20-alpine AS frontend-builder
COPY web/ /app/web/
RUN cd /app/web && npm ci && npm run build

# 主镜像：只包含运行时
FROM python:3.12-slim
COPY --from=frontend-builder /app/web/dist /app/web/dist
COPY comobot/ /app/comobot/
COPY pyproject.toml /app/
RUN pip install -e /app/
EXPOSE 18790
CMD ["comobot", "gateway"]
```

**优势**：镜像一次构建，用户端无需安装任何开发工具。

---

## Web 配置向导详细实现规范

### 前端路由（新增）

```typescript
// web/src/router/index.ts 新增
{
  path: '/setup',
  component: () => import('@/views/SetupWizard.vue'),
  meta: { requiresSetup: false }
}
```

路由守卫逻辑：
- 若 `GET /api/setup/status` 返回 `{ initialized: false }` → 重定向到 `/setup`
- 若已初始化 → 允许访问所有路由

### 配置写入方式

Setup Wizard 完成后，后端将配置写入 `~/.comobot/config.json`，**用户永远不需要手动编辑这个文件**。

对于高级用户，Web UI 提供「高级设置」页面，通过表单编辑所有配置项（而非直接编辑 JSON）。

### API Key 安全

- API Key 在前端**永不明文显示**（显示为 `sk-or-****...****`）
- 传输使用 HTTPS（或本地 HTTP，因仅 localhost）
- 存储使用现有 `comobot/security/` 加密模块

---

## 实现路线图

### Phase 1（第 1-2 周）：P0 脚本安装 + 配置向导

**后端任务：**
- [ ] 新增 `GET /api/setup/status` 端点
- [ ] 新增 `GET /api/setup/providers` 端点（返回支持的提供商列表）
- [ ] 新增 `POST /api/setup/validate-key` 端点（调用 LLM 做一次测试请求）
- [ ] 新增 `POST /api/setup/complete` 端点（写配置 + 重启 agent）
- [ ] 修改 `comobot gateway` 启动时，若未初始化则重定向到 `/setup`

**前端任务：**
- [ ] 新建 `web/src/views/SetupWizard.vue`（步进式表单）
- [ ] 新建 `web/src/views/SetupWizard/` 各步骤组件
- [ ] 路由守卫：未初始化时强制跳转 `/setup`
- [ ] 现有「设置」页完善为完整配置管理界面（替代 JSON 手动编辑）

**安装脚本任务：**
- [ ] 编写 `scripts/install.sh`（Mac/Linux）
- [ ] 编写 `scripts/install.ps1`（Windows PowerShell）
- [ ] 编写 `scripts/install.bat`（Windows 批处理，调用 PS1）
- [x] 安装脚本通过 GitHub raw URL 分发（无需额外静态托管）

### Phase 2（第 3-4 周）：P1 Docker 方案

- [ ] 编写多阶段 `Dockerfile`（前端构建 + Python 运行时）
- [ ] 完善 `docker-compose.yml`（含数据卷、健康检查）
- [ ] 编写 `start.command` / `start.bat` 启动脚本
- [ ] GitHub Actions 自动构建并推送到 `ghcr.io`
- [ ] 打包发布 `comobot-docker.zip`

---

## 安装包分发渠道

| 渠道 | 目标用户 | 状态 |
|------|----------|------|
| GitHub raw URL (`scripts/install.sh`) | Mac 技术友好用户 | P0 |
| GitHub raw URL (`scripts/install.ps1`) | Windows 技术友好用户 | P0 |
| Docker Hub / GHCR | 有 Docker 的用户 | P1 |
| GitHub Releases（comobot-docker.zip） | 愿意用 Docker 的普通用户 | P1 |

---

## 安装后用户体验目标

```
安装完成后，用户看到的第一个界面：

┌─────────────────────────────────────────┐
│  🤖 欢迎使用 Comobot                    │
│                                         │
│  请选择您的 AI 服务提供商：              │
│                                         │
│  ● OpenRouter（推荐）                   │
│  ○ OpenAI                               │
│  ○ Anthropic Claude                     │
│  ○ 本地模型（Ollama）                   │
│                                         │
│  [获取免费 API Key] [下一步 →]          │
└─────────────────────────────────────────┘
```

**成功标准（验收条件）：**
1. Mac 用户（P0）：打开终端，粘贴一条命令，5 分钟内在浏览器完成配置并开始聊天
2. Windows 用户（P0）：双击 install.bat，等待安装完成，5 分钟内在浏览器完成配置并开始聊天
3. Docker 用户（P1）：解压 zip，双击 start.command/start.bat，浏览器自动打开向导
4. 出错时提供友好的中文错误提示和解决建议

---

## 技术风险与应对

| 风险 | 概率 | 应对方案 |
|------|------|----------|
| Mac `.command` 文件被 Gatekeeper 拦截 | 中 | README 说明右键 → 打开；同时提供脚本方案 |
| 用户没有 winget（旧版 Windows） | 中 | 脚本内嵌 Python/Node.js 下载逻辑，直接从官网下载 |
| Python 版本冲突（用户已有旧版） | 中 | 安装到独立目录（如 `%APPDATA%\comobot\python\`），不影响系统 Python |
| 防火墙阻断 curl/wget 下载 | 低 | 提供 GitHub Releases 直接下载备选 |
| Docker Desktop 未安装或未启动 | 中 | start 脚本检测并给出友好提示，附 Docker Desktop 下载链接 |

---

## 附录：推荐技术栈

| 组件 | 技术选型 | 理由 |
|------|----------|------|
| Mac 脚本安装 | Bash + Homebrew | 最成熟，用户接受度高 |
| Windows 脚本安装 | PowerShell + winget | 现代 Windows 内置，无需额外安装 |
| Docker 镜像 | 多阶段构建（Node 前端 + uv Python） | 镜像小、构建快；与现有 Dockerfile 一致 |
| Docker 分发 | comobot-docker.zip + start 脚本 | 用户零命令行操作，双击即启动 |
| Web 向导前端 | Vue 3 + Naive UI（现有） | 复用现有技术栈，无需引入新框架 |
| CI/CD | GitHub Actions | 自动构建镜像、打包分发物并挂载到 Release |
