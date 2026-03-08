# Comobot · ComindX 智能体引擎

> Comobot 是 ComindX 的核心执行引擎：轻量、可控、可编排、可私有化部署。

[![PyPI](https://img.shields.io/pypi/v/comobot)](https://pypi.org/project/comobot/)
![Python](https://img.shields.io/badge/python-≥3.11-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 为什么是 ComindX

ComindX 的目标不是“再造一个聊天机器人”，而是构建一个可长期演进的**数字认知中枢**：

- **开箱即用**：`onboard` 初始化后即可对话与接入渠道。
- **端侧私有**：配置与数据本地优先，支持私有部署。
- **动态认知对齐**：通过记忆、模板、编排形成持续对齐能力。
- **无界编排**：从模板化到流程图，覆盖简单自动化到复杂工作流。
- **工程可控**：轻依赖、可观测、安全机制明确，适合个人与小团队落地。

---

## Comobot 的核心特点（PRD 对齐）

### 1) 轻量但完整
- Python `>=3.11`，核心工程结构清晰，易读易改。
- 支持 CLI、API、网关、Web 前端的统一运行形态。

### 2) 多通道接入
- 支持 Telegram、Discord、Slack、飞书、钉钉、Email、WhatsApp、QQ、Matrix 等。
- 统一渠道管理，便于从单渠道快速扩展到多渠道。

### 3) 多模型与路由能力
- 基于 LiteLLM 生态兼容主流模型服务。
- 支持多 Key 轮询与请求级调度（按 PRD 路线持续增强）。

### 4) 可视化编排（Web）
- 提供 Web 控制台与编排能力（模板模式 + 高级流程模式）。
- 适配“零代码起步 + 高级可定制”双场景。

### 5) 安全与稳定
- JWT 鉴权、敏感凭证加密（AES-256-GCM，PRD 设计）。
- SQLite + WAL 并发优化、状态控制与重试机制（按 PRD 演进）。

> 详细规格请阅读：[`PRD.md`](./PRD.md)

---

## 架构概览

```text
Web UI (Vue3)  <->  FastAPI API  <->  AgentLoop / Orchestrator
                                     |             |
                                ChannelManager   Provider Layer
                                     \             /
                                      Message Bus
                                           |
                                     SQLite + Files
```

- **控制面**：Web 控制台负责配置、编排、监控。
- **执行面**：AgentLoop 承担推理、工具调用、记忆整合。
- **连接面**：ChannelManager 统一多渠道收发。
- **存储面**：结构化数据落 SQLite，模板与技能保留文件形态。

---

## 快速开始

### 方式 A：源码安装（推荐开发者）

```bash
git clone https://github.com/musenming/comobot.git
cd comobot
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
```

### 方式 B：PyPI

```bash
pip install comobot
```

### 方式 C：uv（快速）

```bash
uv tool install comobot
```

### 初始化

```bash
comobot onboard
```

初始化后编辑 `~/.comobot/config.json`：

```json
{
  "providers": {
    "openrouter": {
      "apiKey": "sk-or-v1-xxx"
    }
  },
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5",
      "provider": "openrouter"
    }
  }
}
```

### 启动

```bash
comobot agent
comobot gateway
```

---

## Docker（生产友好）

```bash
# 首次初始化
docker compose run --rm comobot-cli onboard

# 启动网关
docker compose up -d comobot-gateway
```

> `~/.comobot` 会作为数据目录挂载，便于持久化与迁移。

---

## Web 控制台

前端位于 [`web/`](./web)。

### 开发模式

```bash
# 终端 1
comobot gateway

# 终端 2
cd web
npm install
npm run dev
```

### 生产模式

```bash
cd web
npm install
npm run build
cd ..
comobot gateway
```

---

## 常用命令

```bash
comobot --help
comobot --version
comobot agent -m "Hello"
comobot channels login
pytest tests/ -v
ruff check .
ruff format .
```

---

## 项目结构

```
comobot/
├─ 🐍 agent/                Agent core logic
│  ├─ 🔄 loop.py            Agent loop (LLM ↔ tools ↔ memory)
│  ├─ 🧠 context.py         Prompt builder & context manager
│  ├─ 📦 memory.py          Persistent memory store
│  ├─ 🛠️ skills.py          Skills loader & registry
│  ├─ 🧵 subagent.py        Background task executor
│  └─ 🔌 tools/             Built-in tools (shell, fs, web, spawn, mcp, cron, message)
├─ 🚀 api/                  FastAPI REST API & gateway
│  └─ 🗺️ routes/            API route handlers
├─ 🚌 bus/                  Event bus & message queue
├─ 💬 channels/             Chat integrations (Telegram, Slack, DingTalk, Feishu, Discord, QQ, Email, Matrix, WhatsApp, Mochat)
├─ 💻 cli/                  CLI entry point (`comobot` via Typer)
├─ ⚙️ config/               Config schema (Pydantic) & loader
├─ ⏰ cron/                 Scheduled tasks (SQLite store)
├─ 🗄️ db/                   Database layer (SQLite + WAL mode)
├─ ❤️ heartbeat/            Proactive wake-up service
├─ 🎛️ orchestrator/         Optional orchestration layer on AgentLoop
├─ 🧠 providers/            LLM providers (litellm, openai-codex, custom, key rotator)
├─ 🔐 security/             Auth, encryption, access control
├─ 💬 session/              Session management (SQLite backend)
├─ 🧩 skills/               Built-in skills (memory, cron, github, tmux, weather, clawhub, summarize, skill-creator)
├─ 📄 templates/            Prompt templates (AGENTS.md, SOUL.md, TOOLS.md, USER.md, HEARTBEAT.md)
├─ 🧰 utils/                Shared helpers
├─ 🌉 bridge/               TypeScript WhatsApp bridge (Node.js)
├─ 🌐 web/                  Vue 3 + Naive UI frontend
└─ 🧪 tests/                Pytest test suite (138 tests)
```

---

## 路线图

- **一期（当前主线）**：品牌重构、Web 控制台、编排器、SQLite、安全体系、Telegram 增强。更多渠道深度打磨、节点类型扩展、RBAC、插件化。分布式扩容、多租户、可视化分析大盘。
- **二期（规划）**：端侧个性化模型

完整计划请查看：[`PRD.md`](./PRD.md)

---

## 相关文档

- 安装说明：[`INSTALL.md`](./INSTALL.md)
- 安全策略：[`SECURITY.md`](./SECURITY.md)
- 项目结构：[`structure.md`](./structure.md)
- 需求规格：[`PRD.md`](./PRD.md)

---

## License

MIT
