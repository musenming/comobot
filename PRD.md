# comobot 产品需求文档 (PRD)

> 轻量级、开箱即用的多通道智能体编排与自动化平台
>
> 版本: 1.0 | 日期: 2026-03-05 | 状态: 草案

---

## 1. 文档目的

本文档定义 **comobot** 产品的完整需求规格，涵盖功能、架构、安全、部署及性能指标。comobot 基于 nanobot 开源框架二次开发，继承其核心 Agent 能力，并在此基础上新增可视化编排、Web 管控、结构化存储和企业级安全能力。

---

## 2. 背景与目标

### 2.1 背景

随着大语言模型在企业与个人场景的快速普及，用户对多 Agent 编排、跨平台消息触达、任务自动化等能力的需求日益增长。现有方案普遍存在：

- 编排逻辑复杂，上手成本高；
- 多渠道集成碎片化，缺乏统一管理；
- 部署依赖重，运维门槛高；
- 安全与并发控制不足，难以生产环境稳定运行；
- 目标用户多为非技术人员，命令行安装困难。

### 2.2 目标

| 维度 | 目标 |
|------|------|
| **轻量** | 核心依赖少，docker-compose 一键部署，嵌入式 SQLite 免运维 |
| **易用** | Web 初始化向导 + 预设模板 + 可视化流程编排，零代码可用 |
| **多通道** | 继承 10 个渠道，本期重点打磨 Telegram（Webhook + Polling） |
| **多模型** | 兼容主流闭源 API + 本地推理端点，支持多 Key 轮询 |
| **安全可控** | JWT 鉴权、AES-256-GCM 凭证加密、白名单、Prompt 注入防护 |
| **稳定高效** | SQLite WAL 并发优化、排他锁、优雅降级、可靠持久化 |

### 2.3 用户模型

```
┌──────────────┐         ┌─────────────────────┐
│   管理员 (1)  │────────→│    Web 控制面板       │
│   JWT 登录    │         │  配置 / 编排 / 监控   │
└──────────────┘         └─────────────────────┘
                                    │
                          配置 Agent / 渠道 / 模型
                                    │
                                    ▼
┌──────────────┐         ┌─────────────────────┐
│ 终端用户 (N)  │────────→│   Telegram / 其他渠道  │
│ 白名单控制    │         │   与 Bot 交互          │
└──────────────┘         └─────────────────────┘
```

- **管理员**（单人）：通过 Web UI 管理 Agent 配置、编排流程、模型密钥、渠道设置，JWT 认证登录。
- **终端用户**（多人）：通过 Telegram 等渠道与 Bot 交互，受白名单控制。无需登录 Web UI。

---

## 3. 范围与分期

### 3.1 一期（本期）

| 模块 | 说明 |
|------|------|
| 品牌重命名 | nanobot → comobot 全量替换（包名、路径、UI、文档） |
| Web 控制面板 | Vue 3 前端 + FastAPI 后端，初始化向导、配置管理、日志监控 |
| 可视化编排器 | 混合模式：预设模板 + 高级流程图编辑器 |
| SQLite 存储层 | 会话历史、用户数据、编排流程迁移到 SQLite（配置文件 + 技能 Markdown 保留文件形式） |
| 安全体系 | JWT 鉴权、AES-256-GCM 凭证加密、Prompt 注入防护 |
| Telegram 增强 | 新增 Webhook 模式，保持 Polling 模式 |
| 多模型增强 | 多 Key 轮询、请求级负载均衡 |
| 并发控制 | 状态机排他锁、超时控制、指数退避重试 |
| 部署优化 | docker-compose 一键部署，Web 引导初始化 |

### 3.2 二期（规划）

- 更多渠道深度打磨（Discord/Slack/飞书/钉钉）
- 编排器节点类型扩展（条件分支、循环、并行）
- 多管理员 RBAC 权限
- 插件市场（技能分发）

### 3.3 三期（远景）

- 分布式部署与水平扩容
- 可视化数据分析大盘
- 多租户隔离

---

## 4. 系统架构

### 4.1 架构总图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Web 控制面板 (Vue 3)                         │
│  初始化向导 │ 编排器 │ 模型管理 │ 渠道配置 │ 日志监控 │ 会话查看    │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ REST API + WebSocket
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      FastAPI 后端 (API Layer)                        │
│                                                                      │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌───────────────────┐   │
│  │ Auth     │  │ Orchestr. │  │ Config   │  │ WebSocket Push    │   │
│  │ (JWT)    │  │ API       │  │ API      │  │ (日志/状态实时推送) │   │
│  └──────────┘  └───────────┘  └──────────┘  └───────────────────┘   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
┌────────────────┐ ┌─────────────┐ ┌──────────────────┐
│  Orchestrator  │ │  AgentLoop  │ │   ChannelManager  │
│  (编排引擎)     │ │  (核心引擎)  │ │  (渠道管理)        │
│                │ │             │ │                    │
│ 模板解析       │ │ LLM 调用    │ │ Telegram (P+W)    │
│ 流程图执行     │ │ 工具执行    │ │ Discord / Slack    │
│ 变量替换       │ │ 记忆整合    │ │ 飞书 / 钉钉        │
│ 条件路由       │ │ 子Agent     │ │ Email / WhatsApp   │
└───────┬────────┘ └──────┬──────┘ │ QQ / Matrix        │
        │                 │        └─────────┬──────────┘
        └────────┬────────┘                  │
                 ▼                           │
        ┌────────────────┐          ┌────────▼─────────┐
        │   MessageBus   │◄────────►│   Provider Layer  │
        │ (异步消息总线)   │          │  (LLM 提供者)     │
        └───────┬────────┘          │                   │
                │                   │ LiteLLM (100+)    │
                ▼                   │ Custom / Local    │
        ┌────────────────┐          │ 多Key轮询          │
        │   SQLite DB    │          └───────────────────┘
        │                │
        │ sessions       │          ┌───────────────────┐
        │ users          │          │   文件系统          │
        │ workflows      │          │                   │
        │ credentials    │          │ config.json       │
        │ cron_jobs      │          │ SOUL.md / USER.md │
        │ audit_log      │          │ skills/*.md       │
        └────────────────┘          │ MEMORY.md         │
                                    └───────────────────┘
```

### 4.2 存储策略（混合模式）

| 数据类型 | 存储位置 | 理由 |
|---------|---------|------|
| 会话历史 | **SQLite** | 高频读写、需要查询、需要事务保障 |
| 用户数据 | **SQLite** | 白名单、配额、审计日志需结构化查询 |
| 编排流程定义 | **SQLite** | 需要版本管理和快速加载 |
| 定时任务 | **SQLite** | 替代 jobs.json，需要状态原子更新 |
| 凭证密钥 | **SQLite** | AES-256-GCM 加密存储 |
| 审计日志 | **SQLite** | 可追溯、可查询 |
| 主配置 | **文件** (config.json) | 方便手动编辑、环境变量覆盖、Git 管理 |
| 人格模板 | **文件** (SOUL.md 等) | Markdown 天然适合 LLM 上下文注入，方便手动编辑 |
| 技能定义 | **文件** (SKILL.md) | 技能系统依赖文件发现机制，保持零代码扩展 |
| 长期记忆 | **文件** (MEMORY.md) | 始终注入上下文，Agent 可直接读写 |

### 4.3 技术栈

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| 前端 | Vue 3 + Vite + Pinia | 响应式 SPA，黑白极简风格 |
| 编排器前端 | Vue Flow (vue-flow) | 基于 Vue 3 的流程图组件 |
| 后端 API | FastAPI | 异步、自动 OpenAPI 文档、WebSocket 支持 |
| 核心引擎 | asyncio + 现有 AgentLoop | 继承 nanobot 核心，增强并发控制 |
| 数据库 | SQLite + aiosqlite | WAL 模式，异步访问 |
| 认证 | python-jose (JWT) + bcrypt | 无状态 token 认证 |
| 加密 | cryptography (AES-256-GCM) | 凭证加密 |
| LLM 路由 | litellm (现有) | 100+ 后端，增加多 Key 轮询 |
| 部署 | Docker + docker-compose | 单文件编排，SQLite 挂载卷 |

---

## 5. 核心功能需求

### 5.1 品牌重命名 (nanobot → comobot)

**范围**：全量替换，涉及约 92 个文件、400+ 处引用。
**额外需求**：部分nanobot的命令为大写英文字母，比如Nanobot或者NANOBOT，需要把Nanobot改为Comobot，把NANOBOT改为COMOBOT，以此类推。

| 类别 | 变更内容 |
|------|---------|
| Python 包 | `nanobot/` 目录 → `comobot/`，所有 `from nanobot.` → `from comobot.` |
| 包名 | `nanobot-ai` → `comobot` |
| CLI 命令 | `nanobot` → `comobot` |
| 数据目录 | `~/.nanobot/` → `~/.comobot/` |
| 环境变量前缀 | `NANOBOT_` → `COMOBOT_` |
| 用户面文案 | "I am nanobot" → "I am comobot"，帮助文本、邮件主题等 |
| Docker | 服务名、容器名、卷挂载路径 |
| TypeScript Bridge | 包名、认证目录、浏览器标识 |
| 技能元数据 | SKILL.md 中 `{"nanobot": {...}}` → `{"comobot": {...}}` |
| 文档 | README.md、SECURITY.md、structure.md、CLAUDE.md |
| GitHub 引用 | `HKUDS/nanobot` → `musenming/comobot` |

### 5.2 Web 控制面板

#### 5.2.1 初始化向导 (Setup Wizard)

首次启动时引导用户完成最小配置：

```
步骤 1: 设置管理员密码
       └─→ 输入密码 → bcrypt 哈希存储 → 生成 JWT Secret

步骤 2: 配置 LLM 提供者
       └─→ 选择提供者 (OpenAI/Claude/本地...) → 输入 API Key → AES 加密存入 SQLite

步骤 3: 配置 Telegram Bot
       └─→ 输入 Bot Token → 选择 Polling/Webhook → 配置白名单用户 ID

步骤 4: 完成
       └─→ 启动 Agent → 跳转到控制面板主页
```

#### 5.2.2 控制面板功能

| 页面 | 功能 |
|------|------|
| **仪表盘** | 系统状态概览：Agent 在线状态、活跃会话数、今日消息量、模型调用量、错误率 |
| **编排器** | 创建/编辑/启停编排流程（见 5.3 节） |
| **模型管理** | 添加/编辑/删除 LLM 提供者配置，测试连通性，查看调用统计 |
| **渠道管理** | 启停渠道、配置参数、查看渠道状态、白名单管理 |
| **会话查看** | 浏览历史会话、按用户/渠道筛选、查看完整对话内容 |
| **定时任务** | 创建/编辑/删除 Cron 任务，查看执行历史和日志 |
| **日志监控** | 实时日志流（WebSocket 推送）、按级别/模块筛选、错误告警 |
| **系统设置** | 管理员密码修改、Agent 人格配置（编辑 SOUL.md 等）、数据备份/恢复 |

#### 5.2.3 UI 设计原则

- 黑白极简风格，无多余视觉装饰
- 移动端与 PC 端完美自适应
- 操作反馈即时（WebSocket 实时推送状态变化）
- 配置变更即时生效（热重载，无需重启服务）

### 5.3 可视化编排器 (Orchestrator)

#### 5.3.1 混合模式设计

```
┌─────────────────────────────────────────────┐
│              编排器入口                       │
│                                             │
│  ┌─────────────┐    ┌────────────────────┐  │
│  │  模板模式    │    │  高级模式 (流程图)  │  │
│  │  (默认)     │    │  (手动切换)         │  │
│  │             │    │                    │  │
│  │ 选择场景模板 │    │ 拖拽节点 + 连线    │  │
│  │ 填写参数    │    │ 自定义 DAG 流程    │  │
│  │ 一键启用    │    │ 高级配置           │  │
│  └─────────────┘    └────────────────────┘  │
└─────────────────────────────────────────────┘
```

#### 5.3.2 模板模式

预设场景模板，用户填参即用：

| 模板 | 说明 | 参数 |
|------|------|------|
| **智能客服** | 接收用户消息 → LLM 回答 → 回复用户 | System Prompt、模型选择、知识库路径 |
| **定时摘要** | Cron 触发 → 抓取 URL → LLM 摘要 → 推送 Telegram | URL 列表、Cron 表达式、推送目标 |
| **消息转发** | 接收消息 → 条件匹配 → 转发到指定渠道/群 | 匹配规则、目标渠道 |
| **文档助手** | 接收文件 → 解析内容 → LLM 分析 → 回复 | 支持格式、分析指令 |
| **自定义** | 从空白模板开始 → 自动切换到高级模式 | — |

#### 5.3.3 高级模式（流程图编辑器）

**节点类型**：

| 节点类型 | 图标 | 说明 | 配置项 |
|---------|------|------|--------|
| **Trigger** | ⚡ | 流程入口 | 触发方式：消息到达 / Cron 定时 / Webhook 调用 / 手动 |
| **LLM Call** | 🤖 | 调用大模型 | 模型选择、System Prompt、温度、最大 Token |
| **Tool** | 🔧 | 执行工具 | 工具类型：Web 搜索 / 文件读写 / Shell 命令 / HTTP 请求 |
| **Condition** | 🔀 | 条件分支 | 条件表达式（基于变量值判断） |
| **Response** | 💬 | 发送消息 | 目标渠道 + chat_id，消息内容（支持变量替换） |
| **Delay** | ⏱️ | 延时等待 | 等待时长 |
| **SubAgent** | 🔄 | 调用子 Agent | 任务描述、迭代上限 |

**变量系统**：

```
{{trigger.message}}     — 触发消息原文
{{trigger.sender_id}}   — 发送者 ID
{{trigger.channel}}     — 来源渠道
{{trigger.timestamp}}   — 触发时间
{{llm.response}}        — LLM 最新回复
{{tool.result}}         — 工具执行结果
{{env.VARIABLE}}        — 环境变量
{{workflow.name}}       — 当前流程名称
```

**执行引擎**：

```
Trigger 事件到达
  → 编排引擎加载 Workflow 定义
  → 初始化执行上下文 (变量空间)
  → 按 DAG 拓扑序执行节点:
      ├─ Trigger: 提取消息数据 → 写入变量
      ├─ LLM Call: 构建 Prompt (变量替换) → 调用 Provider → 结果写入变量
      ├─ Tool: 执行工具 → 结果写入变量
      ├─ Condition: 评估表达式 → 选择分支
      ├─ Response: 渲染消息模板 → 通过 MessageBus 发送
      ├─ Delay: asyncio.sleep
      └─ SubAgent: 调用 SubagentManager.spawn
  → 执行完成 → 更新状态 → 记录审计日志
```

#### 5.3.4 编排器与现有 AgentLoop 的关系

```
                    ┌───────────────────────┐
                    │     消息到达           │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │   路由判断             │
                    │   是否匹配编排流程？    │
                    └──┬────────────────┬───┘
                       │                │
                 匹配编排流程       无匹配流程
                       │                │
              ┌────────▼───────┐ ┌──────▼──────┐
              │  Orchestrator  │ │  AgentLoop   │
              │  (流程图执行)   │ │  (自由对话)   │
              └────────────────┘ └─────────────┘
```

- 编排流程优先：消息到达时先匹配编排规则（关键词、渠道、用户等）
- 无匹配则回退到现有 AgentLoop（自由对话模式）
- 两者共享：MessageBus、Provider、ToolRegistry、SessionManager

### 5.4 多渠道集成

#### 5.4.1 渠道清单与本期状态

| 渠道 | 状态 | 本期工作 |
|------|------|---------|
| **Telegram** | ✅ 已有 Polling | **新增 Webhook 模式**，`secret_token` 校验 |
| Discord | ✅ 已有 | 维持现状 |
| Slack | ✅ 已有 | 维持现状 |
| 飞书 | ✅ 已有 | 维持现状 |
| 钉钉 | ✅ 已有 | 维持现状 |
| Email | ✅ 已有 | 维持现状 |
| WhatsApp | ✅ 已有 | 维持现状 |
| QQ | ✅ 已有 | 维持现状 |
| Matrix | ✅ 已有 | 维持现状 |
| Mochat | ✅ 已有 | 维持现状 |

#### 5.4.2 Telegram Webhook 模式

```
Telegram 服务器
  │
  │ POST https://your-domain/webhook/telegram
  │ Header: X-Telegram-Bot-Api-Secret-Token: <secret>
  │
  ▼
FastAPI Webhook Endpoint
  │
  ├─ 校验 secret_token
  ├─ 解析 Update 对象
  ├─ 校验 allowFrom 白名单
  └─ 封装为 InboundMessage → MessageBus
```

配置方式（Web UI 或 config.json）：

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "encrypted:...",
      "mode": "webhook",
      "webhookUrl": "https://your-domain/webhook/telegram",
      "secretToken": "auto-generated-or-custom",
      "allowFrom": ["user_id_1", "user_id_2"]
    }
  }
}
```

### 5.5 多模型适配

#### 5.5.1 现有能力（继承）

通过 litellm 已支持 100+ 后端：OpenAI、Claude、Gemini、DeepSeek、Kimi、Qwen、GLM、本地推理（vLLM/Ollama）等。

#### 5.5.2 新增：多 Key 轮询与负载均衡

```python
# config.json 中的提供者配置
{
  "providers": {
    "openai": {
      "api_keys": [              # 新增：多 Key 数组
        "sk-key-1",
        "sk-key-2",
        "sk-key-3"
      ],
      "strategy": "round_robin",  # 轮询策略: round_robin | random | least_used
      "api_base": null
    }
  }
}
```

**轮询策略**：

| 策略 | 说明 |
|------|------|
| `round_robin` | 按顺序轮询，均匀分配请求 |
| `random` | 随机选择，简单高效 |
| `least_used` | 选择最近使用最少的 Key，配合 429 退避 |

**429 处理**：

```
请求发送 → 返回 429
  → 当前 Key 标记冷却 (cooldown_seconds, 默认 60s)
  → 自动切换到下一个可用 Key
  → 所有 Key 冷却中 → 指数退避等待 (1s, 2s, 4s, 8s, 最大 60s)
  → 向用户返回"服务繁忙，请稍后重试"
```

### 5.6 定时任务 (Cron)

**继承**现有 CronService 的 at/every/cron 三种调度方式，变更存储后端：

| 变更 | 原 (nanobot) | 新 (comobot) |
|------|-------------|-------------|
| 存储 | `cron/jobs.json` 文件 | SQLite `cron_jobs` 表 |
| 管理方式 | 仅 CLI / Agent 工具 | Web UI + CLI + Agent 工具 |
| 执行日志 | 仅内存状态 | SQLite `cron_logs` 表持久化 |

### 5.7 记忆系统

**保持现有两层记忆设计**，增强可观测性：

| 层级 | 存储 | 变更 |
|------|------|------|
| MEMORY.md | 文件（不变） | Web UI 可查看/编辑 |
| HISTORY.md | 文件（不变） | Web UI 可查看 |
| 会话历史 | **JSONL → SQLite** | 支持 Web UI 浏览、按用户/渠道筛选 |

---

## 6. 数据层设计

### 6.1 SQLite 数据库

**文件位置**：`~/.comobot/comobot.db`

**核心表结构**：

```sql
-- 管理员账户
CREATE TABLE admin (
    id          INTEGER PRIMARY KEY,
    username    TEXT UNIQUE NOT NULL,
    password    TEXT NOT NULL,            -- bcrypt 哈希
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

-- 会话记录
CREATE TABLE sessions (
    id              INTEGER PRIMARY KEY,
    session_key     TEXT UNIQUE NOT NULL,  -- "channel:chat_id"
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    last_consolidated INTEGER DEFAULT 0
);

-- 会话消息
CREATE TABLE messages (
    id          INTEGER PRIMARY KEY,
    session_id  INTEGER REFERENCES sessions(id),
    role        TEXT NOT NULL,             -- system / user / assistant / tool
    content     TEXT,
    tool_calls  TEXT,                      -- JSON
    tool_call_id TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_messages_session ON messages(session_id, id);

-- 编排流程定义
CREATE TABLE workflows (
    id          INTEGER PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    description TEXT,
    template    TEXT,                      -- 模板标识 (NULL = 自定义流程)
    definition  TEXT NOT NULL,             -- JSON: 节点 + 边 + 配置
    enabled     INTEGER DEFAULT 1,
    trigger_rules TEXT,                    -- JSON: 触发匹配规则
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

-- 编排执行记录
CREATE TABLE workflow_runs (
    id          INTEGER PRIMARY KEY,
    workflow_id INTEGER REFERENCES workflows(id),
    trigger_data TEXT,                     -- JSON: 触发消息数据
    status      TEXT DEFAULT 'running',    -- running / completed / failed
    variables   TEXT,                      -- JSON: 执行时的变量快照
    error       TEXT,
    started_at  TEXT DEFAULT (datetime('now')),
    finished_at TEXT
);

-- 定时任务
CREATE TABLE cron_jobs (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    schedule    TEXT NOT NULL,             -- JSON: CronSchedule
    payload     TEXT NOT NULL,             -- JSON: CronPayload
    enabled     INTEGER DEFAULT 1,
    next_run_at TEXT,
    last_run_at TEXT,
    last_status TEXT,
    last_error  TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

-- 加密凭证
CREATE TABLE credentials (
    id          INTEGER PRIMARY KEY,
    provider    TEXT NOT NULL,             -- openai / anthropic / telegram / ...
    key_name    TEXT NOT NULL,             -- api_key / bot_token / ...
    encrypted   BLOB NOT NULL,            -- AES-256-GCM 加密
    nonce       BLOB NOT NULL,            -- GCM nonce
    tag         BLOB NOT NULL,            -- GCM auth tag
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(provider, key_name)
);

-- 白名单用户
CREATE TABLE allowed_users (
    id          INTEGER PRIMARY KEY,
    channel     TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    alias       TEXT,                      -- 备注名
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(channel, user_id)
);

-- 审计日志
CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY,
    timestamp   TEXT DEFAULT (datetime('now')),
    level       TEXT NOT NULL,             -- info / warn / error
    module      TEXT NOT NULL,             -- agent / channel / cron / auth / ...
    event       TEXT NOT NULL,             -- message_received / llm_call / tool_exec / ...
    detail      TEXT,                      -- JSON
    session_key TEXT
);
CREATE INDEX idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX idx_audit_module ON audit_log(module);
```

### 6.2 SQLite 配置

```python
# 数据库初始化
PRAGMAS = {
    "journal_mode": "wal",        # WAL 模式：并发读写
    "busy_timeout": 5000,         # 锁等待 5 秒
    "synchronous": "normal",      # 平衡性能与安全
    "foreign_keys": "on",         # 外键约束
    "cache_size": -8000,          # 8MB 缓存
}
```

### 6.3 文件系统（保留）

```
~/.comobot/
├── config.json                 # 主配置（手动可编辑）
├── comobot.db                  # SQLite 数据库
├── secret.key                  # AES 主密钥（首次生成，或环境变量注入）
└── workspace/
    ├── AGENTS.md               # Agent 行为指令
    ├── SOUL.md                 # 人格定义
    ├── USER.md                 # 用户画像
    ├── TOOLS.md                # 工具约束
    ├── HEARTBEAT.md            # 心跳任务
    ├── memory/
    │   ├── MEMORY.md           # 长期记忆
    │   └── HISTORY.md          # 历史日志
    ├── skills/                 # 用户自定义技能
    └── media/                  # 媒体文件缓存
```

---

## 7. 安全需求

### 7.1 身份鉴权

| 场景 | 方案 |
|------|------|
| Web 控制面板 | JWT 认证，token 有效期 24h，支持刷新 |
| 管理员密码 | bcrypt 哈希加盐存储，最低 8 位 |
| Telegram 用户 | `allowed_users` 表白名单，网关层拦截 |
| Telegram Webhook | `secret_token` 头校验 |
| API 访问 | 所有 API 端点（除 /setup 和 /auth/login）需 Bearer Token |

### 7.2 凭证加密

```
密钥来源 (二选一):
  ├─ 环境变量: COMOBOT_SECRET_KEY
  └─ 文件: ~/.comobot/secret.key (首次启动自动生成)

加密流程:
  明文 API Key
    → 生成随机 12 字节 nonce
    → AES-256-GCM 加密
    → 存入 credentials 表 (encrypted + nonce + tag)

解密流程:
  从 credentials 表读取 (encrypted + nonce + tag)
    → AES-256-GCM 解密
    → 返回明文 (仅内存中使用，不写日志)
```

### 7.3 Prompt 注入防护

| 层级 | 措施 |
|------|------|
| 输入层 | 用户消息中的 `<system>` / `<|system|>` 等标记转义 |
| 上下文层 | 运行时注入的数据标记为 `untrusted`（现有机制） |
| 模板层 | 编排器变量替换时自动转义特殊标记 |
| 输出层 | 工具执行结果截断（现有 10K 限制） |

### 7.4 网络隔离

- 本地推理引擎（vLLM/Ollama）在 docker-compose 中限定 `internal` 网络
- Web UI 默认监听 `0.0.0.0:8080`，可配置绑定地址
- SQLite 文件权限 `600`（仅 owner 可读写）

---

## 8. 并发与可靠性

### 8.1 排他锁

```
消息到达
  → 查询 session 状态
  → [状态 = processing?]
      ├─ YES → 排队等待 (asyncio.Event) 或丢弃并提示"正在处理中"
      └─ NO  → 设置状态为 processing → 执行 Agent → 完成后释放
```

实现方式：内存级 `asyncio.Lock` per session_key（现有 AgentLoop 已有 `_dispatch_lock`，需扩展为 per-session 粒度）。

### 8.2 超时控制

| 操作 | 超时 | 处理 |
|------|------|------|
| LLM API 调用 | 60s（可配置） | 超时后向用户发送错误提示 |
| 工具执行 (exec) | 60s（现有） | 超时后 kill 进程 |
| MCP 工具调用 | 30s（现有） | 超时后返回错误 |
| Webhook 响应 | 5s | 立即 200 OK，异步处理 |

### 8.3 优雅停机

```
收到 SIGTERM / SIGINT
  → 停止接收新消息
  → 等待当前所有 processing 任务完成（最多 30s）
  → 持久化内存中的会话状态到 SQLite
  → 关闭所有渠道连接
  → 关闭数据库连接
  → 退出进程
```

### 8.4 指数退避

```python
# LLM API 429 重试策略
retry_config = {
    "max_retries": 5,
    "initial_delay": 1.0,      # 秒
    "multiplier": 2.0,
    "max_delay": 60.0,
    "jitter": True,            # 随机抖动，防止惊群
}
```

---

## 9. 部署方案

### 9.1 docker-compose（推荐）

```yaml
version: "3.8"
services:
  comobot:
    image: comobot:latest
    ports:
      - "8080:8080"             # Web UI + API
    volumes:
      - ~/.comobot:/root/.comobot  # 数据持久化
    environment:
      - COMOBOT_SECRET_KEY=${COMOBOT_SECRET_KEY}  # 可选，不设则自动生成
    restart: unless-stopped
```

单容器包含：FastAPI 后端 + Vue 3 前端静态文件 + Agent 引擎。

### 9.2 首次启动流程

```
docker-compose up -d
  → 服务启动，检测 ~/.comobot/comobot.db 不存在
  → 自动创建数据库 + 表结构
  → Web UI 进入初始化向导 (http://localhost:8080/setup)
  → 用户完成配置
  → 自动启动 Agent + 渠道
  → 进入正常运行状态
```

### 9.3 升级策略

```
docker-compose pull && docker-compose up -d
  → 新版本启动
  → 检测数据库版本 (schema_version 表)
  → 自动执行迁移脚本
  → 正常运行
```

---

## 10. API 设计概要

### 10.1 认证

| 端点 | 方法 | 说明 |
|------|------|------|
| `POST /api/auth/login` | 公开 | 管理员登录，返回 JWT |
| `POST /api/auth/refresh` | JWT | 刷新 Token |
| `POST /api/setup` | 公开（仅首次） | 初始化向导提交 |

### 10.2 核心资源

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/dashboard` | JWT | 仪表盘数据 |
| `GET/POST/PUT/DELETE /api/workflows` | JWT | 编排流程 CRUD |
| `POST /api/workflows/{id}/execute` | JWT | 手动触发流程 |
| `GET /api/workflows/{id}/runs` | JWT | 执行历史 |
| `GET/POST/PUT/DELETE /api/providers` | JWT | 模型提供者 CRUD |
| `POST /api/providers/{id}/test` | JWT | 测试连通性 |
| `GET/POST/PUT/DELETE /api/channels` | JWT | 渠道 CRUD |
| `GET /api/sessions` | JWT | 会话列表 |
| `GET /api/sessions/{key}/messages` | JWT | 会话消息 |
| `GET/POST/PUT/DELETE /api/cron` | JWT | 定时任务 CRUD |
| `GET /api/logs` | JWT | 审计日志查询 |
| `GET /api/settings` | JWT | 系统设置读取 |
| `PUT /api/settings` | JWT | 系统设置更新 |

### 10.3 Webhook

| 端点 | 方法 | 说明 |
|------|------|------|
| `POST /webhook/telegram` | Telegram 签名校验 | Telegram Webhook 入口 |

### 10.4 WebSocket

| 端点 | 说明 |
|------|------|
| `WS /ws/logs` | 实时日志流推送 |
| `WS /ws/status` | Agent/渠道状态实时更新 |

---

## 11. 验收标准

### 11.1 部署验收

- [ ] `docker-compose up -d` 一键启动，无额外依赖
- [ ] 首次访问 `http://localhost:8080` 自动进入初始化向导
- [ ] 向导完成后 Agent 自动上线

### 11.2 功能验收

- [ ] Web UI 可完成全部配置（模型、渠道、白名单），无需编辑配置文件
- [ ] 模板模式：选择"智能客服"模板，填参后 Telegram Bot 正确响应
- [ ] 高级模式：拖拽创建 Trigger → LLM → Response 流程，保存后可执行
- [ ] 无编排匹配时，回退到自由对话模式（现有 AgentLoop）
- [ ] Telegram Polling 和 Webhook 两种模式均可正常工作
- [ ] 至少接入一个闭源模型 + 一个本地模型（Ollama），在 UI 中可切换
- [ ] 多 Key 配置后，请求均匀分配到各 Key
- [ ] Cron 定时任务在 Web UI 创建后按时执行
- [ ] 现有 10 个渠道在 comobot 重命名后功能不退化

### 11.3 性能验收

- [ ] 100 并发用户场景下，SQLite 无 `database is locked` 报错
- [ ] LLM API 调用超时 60s 内返回明确错误提示
- [ ] 单条消息端到端延迟（不含 LLM 推理）< 200ms

### 11.4 安全验收

- [ ] 非白名单用户无法触发 Agent 任务
- [ ] 数据库中 API Key 经 AES-256-GCM 加密，明文仅存在于内存
- [ ] Web UI 未登录无法访问任何配置 API
- [ ] Telegram Webhook 伪造请求（错误 secret_token）被拒绝
- [ ] Prompt 注入测试：用户消息中包含 `ignore previous instructions` 不影响系统行为

---

## 12. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| SQLite 并发写入瓶颈 | 高并发下写入延迟 | WAL 模式 + busy_timeout + 写操作队列化 |
| 本地模型推理慢 | 用户体验差 | 超时提示 + 流式输出（如模型支持） |
| 编排器复杂度高 | 开发周期长 | 先做模板模式 MVP，高级模式分步迭代 |
| 前后端分离开发 | 联调成本 | FastAPI 自动生成 OpenAPI spec，前端按 spec 开发 |
| 重命名导致回归 | 功能异常 | 全量测试覆盖，rename 后跑完整测试套件 |

---

## 13. 实施路线与进度追踪

> 状态图例：⬜ 未开始 | 🔵 进行中 | ✅ 已完成 | ⏸️ 阻塞

### Phase 0: 品牌重命名

| # | 任务 | 状态 | 关键产出 |
|---|------|------|---------|
| 0.1 | Python 包目录 `nanobot/` → `comobot/` | ✅ | 目录重命名 + 所有 import 路径更新 |
| 0.2 | 包元数据更新 (pyproject.toml) | ✅ | 包名、CLI 入口、构建路径 |
| 0.3 | 配置路径 `~/.nanobot/` → `~/.comobot/` | ✅ | schema.py, loader.py, helpers.py + 迁移提示 |
| 0.4 | 环境变量前缀 `NANOBOT_` → `COMOBOT_` | ✅ | schema.py env_prefix |
| 0.5 | 用户面文案与品牌标识 | ✅ | SOUL.md, 帮助文本, 邮件主题, CLI 标题 |
| 0.6 | TypeScript Bridge 重命名 | ✅ | package.json, 认证目录, 浏览器标识 |
| 0.7 | Docker / Shell 脚本更新 | ✅ | docker-compose, Dockerfile, tmux 脚本 |
| 0.8 | 技能元数据 key 更新 | ✅ | SKILL.md frontmatter + skills.py 向后兼容解析 |
| 0.9 | 文档全量更新 | ✅ | README.md, SECURITY.md, COMMUNICATION.md |
| 0.10 | 测试文件 import 更新 + 全量测试通过 | ✅ | 99 passed, 1 skipped, 3 pre-existing failures |

### Phase 1: 基础设施

| # | 任务 | 状态 | 关键产出 |
|---|------|------|---------|
| 1.1 | SQLite 存储层核心实现 | ✅ | `comobot/db/` 模块：连接池、WAL 配置、9 表迁移 |
| 1.2 | 会话存储迁移 (JSONL → SQLite) | ✅ | SQLiteSessionManager，与原 Session 接口兼容 |
| 1.3 | Cron 存储迁移 (jobs.json → SQLite) | ✅ | CronService 支持双后端 (file/SQLite)，SQLiteCronStore 集成完成 |
| 1.4 | 凭证加密模块 (AES-256-GCM) | ✅ | CredentialVault: 加密/存储/检索/删除 |
| 1.5 | FastAPI 后端骨架 | ✅ | create_app 工厂 + health/auth/setup 路由 |
| 1.6 | JWT 认证模块 | ✅ | AuthManager: bcrypt 密码 + JWT 签发/验证 |
| 1.7 | Vue 3 前端项目初始化 | ✅ | Vite + Vue 3 + Naive UI + Pinia + Vue Router |
| 1.8 | 初始化向导 (Setup Wizard) | ✅ | 4 步向导 + /api/setup 端点 |

### Phase 2: 核心功能

| # | 任务 | 状态 | 关键产出 |
|---|------|------|---------|
| 2.1 | Web UI — 仪表盘 | ✅ | API + Vue 页面（统计卡片） |
| 2.2 | Web UI — 模型管理 | ✅ | providers CRUD API |
| 2.3 | Web UI — 渠道管理 | ✅ | channels API + 白名单管理 |
| 2.4 | Web UI — 会话查看 | ✅ | sessions + messages API |
| 2.5 | Web UI — 定时任务 | ✅ | cron API |
| 2.6 | Web UI — 日志监控 | ✅ | audit_log 查询 API |
| 2.7 | Web UI — 系统设置 | ✅ | settings + password API |
| 2.8 | 编排器后端 — 流程执行引擎 | ✅ | WorkflowEngine: DAG 拓扑执行 + 变量替换 |
| 2.9 | 编排器后端 — 模板解析器 | ✅ | 4 个预设模板 + build_from_template |
| 2.10 | 编排器后端 — 消息路由集成 | ✅ | AgentLoop._dispatch 先查编排再回退 |
| 2.11 | 编排器前端 — 模板模式 | ✅ | WorkflowsView.vue: 模板选择 + 参数表单 + 创建 |
| 2.12 | 编排器前端 — 高级模式 (Vue Flow) | ✅ | WorkflowEditorView: 拖拽节点、连线、配置面板、保存/加载 |
| 2.13 | Telegram Webhook 模式 | ✅ | FastAPI 端点 + secret_token + schema 字段 |

### Phase 3: 增强与加固

| # | 任务 | 状态 | 关键产出 |
|---|------|------|---------|
| 3.1 | 多 Key 轮询与负载均衡 | ✅ | KeyRotator: round_robin / random / least_used |
| 3.2 | 429 指数退避与 Key 冷却 | ✅ | mark_cooldown + 自动切 Key |
| 3.3 | Per-session 并发锁 | ✅ | WeakValueDictionary per-session asyncio.Lock |
| 3.4 | 优雅停机 | ✅ | SIGTERM/SIGINT → drain sessions (30s) → cleanup |
| 3.5 | 审计日志系统 | ✅ | AuditLogger + audit_log 表 + Web API 查询 |
| 3.6 | Prompt 注入防护增强 | ✅ | _escape_prompt_injection 在变量替换中 |

### Phase 4: 部署打磨

| # | 任务 | 状态 | 关键产出 |
|---|------|------|---------|
| 4.1 | docker-compose 部署优化 | ✅ | 多阶段构建、前端+bridge 预编译、named volume、stop_grace_period |
| 4.2 | 数据库自动迁移机制 | ✅ | schema_version 表 + MIGRATIONS 列表、幂等执行 |
| 4.3 | 端到端测试 | ✅ | 34 tests passing: DB/Security/API/Orchestrator/KeyRotator |
| 4.4 | 文档更新 | ✅ | CLAUDE.md + structure.md 已同步 comobot 重命名 |
| 4.5 | 安全审计 | ✅ | AES-256-GCM、bcrypt、参数化 SQL、Pydantic 验证、注入防护 |

### 进度总览

| Phase | 任务数 | 已完成 | 进度 |
|-------|--------|--------|------|
| Phase 0: 重命名 | 10 | 10 | 100% |
| Phase 1: 基础设施 | 8 | 8 | 100% |
| Phase 2: 核心功能 | 13 | 13 | 100% |
| Phase 3: 增强 | 6 | 6 | 100% |
| Phase 4: 打磨 | 5 | 5 | 100% |
| **总计** | **42** | **42** | **100%** |

---

## 14. 后续规划

| 阶段 | 内容 |
|------|------|
| 二期 | 更多渠道深度适配、编排器节点扩展（循环/并行）、多管理员 RBAC |
| 三期 | 分布式部署、消息队列（Redis/RabbitMQ）替代内存 Bus |
| 四期 | 可视化数据分析大盘、运营指标看板 |
