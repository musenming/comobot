# comobot / nanobot — 项目结构文档

> 基于 nanobot 框架的超轻量级个人 AI 助手，核心代码约 11,000 行 Python + 370 行 TypeScript。

---

## 目录总览

```
comobot/
├── comobot/                    # 核心 Python 包
│   ├── agent/                  # Agent 核心引擎 (2482 行)
│   │   ├── loop.py             #   主处理循环 — 消息消费、LLM 调用、工具执行
│   │   ├── context.py          #   上下文构建器 — 系统提示词组装
│   │   ├── memory.py           #   两层记忆系统 — MEMORY.md + HISTORY.md
│   │   ├── skills.py           #   技能加载器 — 发现、校验、渐进加载
│   │   ├── subagent.py         #   子 Agent 管理 — 后台任务派生与回收
│   │   └── tools/              #   内置工具集 (12+)
│   │       ├── base.py         #     Tool 抽象基类 + ToolRegistry
│   │       ├── filesystem.py   #     read_file / write_file / edit_file / list_dir
│   │       ├── shell.py        #     exec — Shell 命令执行
│   │       ├── web.py          #     web_search (Brave) / web_fetch (Jina)
│   │       ├── message.py      #     message — 跨渠道发消息
│   │       ├── spawn.py        #     spawn — 启动后台子 Agent
│   │       ├── cron.py         #     cron — 定时任务管理
│   │       ├── mcp.py          #     MCP 服务器工具动态加载
│   │       └── registry.py     #     工具注册表
│   │
│   ├── channels/               # 渠道适配层 (4960 行)
│   │   ├── base.py             #   BaseChannel 抽象基类
│   │   ├── manager.py          #   ChannelManager — 渠道生命周期管理与消息路由
│   │   ├── telegram.py         #   Telegram Bot API 轮询
│   │   ├── discord.py          #   Discord Gateway WebSocket
│   │   ├── slack.py            #   Slack Socket Mode
│   │   ├── whatsapp.py         #   WhatsApp (Node.js Bridge)
│   │   ├── feishu.py           #   飞书 WebSocket 长连接
│   │   ├── dingtalk.py         #   钉钉 Stream 模式
│   │   ├── email.py            #   Email (IMAP 轮询 + SMTP)
│   │   ├── matrix.py           #   Matrix 协议 (可选 E2E 加密)
│   │   ├── qq.py               #   QQ Bot SDK + WebSocket
│   │   └── mochat.py           #   Mochat Socket.IO
│   │
│   ├── providers/              # LLM 提供者抽象层 (1314 行)
│   │   ├── base.py             #   LLMProvider 抽象基类 + LLMResponse
│   │   ├── registry.py         #   ProviderSpec 注册表 — 模型路由与自动检测
│   │   ├── litellm_provider.py #   LiteLLM 通用提供者 (100+ 后端)
│   │   ├── custom_provider.py  #   OpenAI 兼容 API 直连
│   │   ├── openai_codex_provider.py  # OAuth 认证提供者
│   │   └── transcription.py    #   语音转文字
│   │
│   ├── cli/                    # 命令行接口 (912 行)
│   │   └── commands.py         #   Typer CLI — onboard / gateway / agent / status
│   │
│   ├── config/                 # 配置管理 (487 行)
│   │   ├── schema.py           #   Pydantic v2 配置模型定义
│   │   └── loader.py           #   配置加载 / 保存 / 迁移
│   │
│   ├── cron/                   # 定时任务服务 (441 行)
│   │   ├── service.py          #   CronService — 调度循环与持久化
│   │   └── types.py            #   CronJob / CronSchedule / CronPayload 类型
│   │
│   ├── heartbeat/              # 周期唤醒服务 (178 行)
│   │   └── service.py          #   HeartbeatService — 两阶段决策+执行
│   │
│   ├── bus/                    # 异步消息总线 (88 行)
│   │   ├── events.py           #   InboundMessage / OutboundMessage 事件定义
│   │   └── queue.py            #   MessageBus — 双向 asyncio.Queue
│   │
│   ├── session/                # 会话管理 (217 行)
│   │   └── manager.py          #   Session + SessionManager — JSONL 持久化
│   │
│   ├── templates/              # 提示词模板
│   │   ├── AGENTS.md           #   Agent 行为指令
│   │   ├── SOUL.md             #   人格与价值观
│   │   ├── TOOLS.md            #   工具使用约束
│   │   ├── USER.md             #   用户画像模板
│   │   ├── HEARTBEAT.md        #   心跳任务模板
│   │   └── memory/
│   │       └── MEMORY.md       #   长期记忆初始模板
│   │
│   ├── skills/                 # 内置技能 (8 个 SKILL.md)
│   │   ├── cron/SKILL.md       #   定时提醒与任务调度
│   │   ├── memory/SKILL.md     #   记忆管理指令
│   │   ├── github/SKILL.md     #   GitHub CLI 集成
│   │   ├── weather/SKILL.md    #   天气查询 (wttr.in / Open-Meteo)
│   │   ├── summarize/SKILL.md  #   URL/文件/YouTube 摘要
│   │   ├── tmux/SKILL.md       #   远程 tmux 会话控制
│   │   ├── clawhub/SKILL.md    #   ClawHub 技能仓库
│   │   └── skill-creator/SKILL.md  # 技能创建向导
│   │
│   └── utils/                  # 工具函数 (72 行)
│       └── helpers.py
│
├── bridge/                     # WhatsApp Node.js 桥接 (370 行 TS)
│   ├── src/
│   │   ├── index.ts            #   入口
│   │   ├── server.ts           #   WebSocket 服务
│   │   ├── whatsapp.ts         #   WhatsApp Web 客户端
│   │   └── types.d.ts          #   类型定义
│   ├── package.json
│   └── tsconfig.json
│
├── tests/                      # 测试套件 (16 文件, 3567 行)
│
├── pyproject.toml              # 项目元数据 + 依赖 + ruff/pytest 配置
├── Dockerfile                  # 容器化部署
├── docker-compose.yml          # 编排配置
├── core_agent_lines.sh         # 核心代码行数统计脚本
├── README.md                   # 项目说明
├── COMMUNICATION.md            # 通信协议文档
├── SECURITY.md                 # 安全策略
└── LICENSE                     # MIT 许可证
```

---

## 架构总图

```
┌──────────────────────────────────────────────────────────────────────┐
│                         用户 / 外部平台                               │
│  Telegram  Discord  Slack  飞书  钉钉  Email  WhatsApp  QQ  Matrix  │
└─────┬────────┬───────┬──────┬─────┬──────┬───────┬──────┬──────┬────┘
      │        │       │      │     │      │       │      │      │
      └────────┴───────┴──────┴─────┴──────┴───────┴──────┴──────┘
                                    │
                          ┌─────────▼──────────┐
                          │   ChannelManager    │
                          │  (渠道生命周期管理)   │
                          └─────────┬──────────┘
                                    │
                    InboundMessage ──┤── OutboundMessage
                                    │
                          ┌─────────▼──────────┐
                          │    MessageBus       │
                          │  inbound ↓  ↑ outbound │
                          └─────────┬──────────┘
                                    │
              ┌─────────────────────▼─────────────────────┐
              │              AgentLoop (核心引擎)           │
              │                                            │
              │  ┌──────────────┐    ┌──────────────────┐  │
              │  │ContextBuilder│    │   ToolRegistry    │  │
              │  │              │    │                   │  │
              │  │ ┌──────────┐ │    │ filesystem  exec  │  │
              │  │ │ 模板加载  │ │    │ web_search  fetch │  │
              │  │ │ 记忆注入  │ │    │ message   spawn  │  │
              │  │ │ 技能摘要  │ │    │ cron   MCP tools │  │
              │  │ └──────────┘ │    └────────┬─────────┘  │
              │  └──────┬───────┘             │            │
              │         │                     │            │
              │         ▼                     ▼            │
              │  ┌─────────────┐    ┌──────────────────┐   │
              │  │ LLM Provider│◄──►│ 工具执行 (≤40轮)  │   │
              │  │ (推理引擎)   │    └──────────────────┘   │
              │  └─────────────┘                           │
              └──────┬───────────────────┬─────────────────┘
                     │                   │
          ┌──────────▼────────┐  ┌───────▼────────┐
          │  SessionManager   │  │  MemoryStore   │
          │  (JSONL 会话持久化) │  │  (两层记忆系统) │
          └───────────────────┘  └────────────────┘
                                         │
                              ┌──────────┴──────────┐
                              │                     │
                        MEMORY.md              HISTORY.md
                      (始终加载上下文)          (grep 按需检索)

              ┌───────────────┐    ┌────────────────┐
              │  CronService  │    │HeartbeatService│
              │  (定时任务调度) │    │ (周期唤醒决策)  │
              │               │    │                │
              │ at/every/cron │    │ Phase1: 决策   │
              │ jobs.json     │    │ Phase2: 执行   │
              └───────┬───────┘    └───────┬────────┘
                      │                    │
                      └────────┬───────────┘
                               ▼
                    AgentLoop.process_direct()
```

---

## 模块关系矩阵

| 模块 | 依赖 | 被依赖 |
|------|------|--------|
| **AgentLoop** | MessageBus, SessionManager, MemoryStore, ContextBuilder, ToolRegistry, Provider, SubagentManager | CLI, CronService, HeartbeatService |
| **ContextBuilder** | SkillsLoader, MemoryStore, Config | AgentLoop |
| **MemoryStore** | Provider (用于整合时调 LLM) | AgentLoop, ContextBuilder |
| **ToolRegistry** | 各 Tool 实现 | AgentLoop, SubagentManager |
| **MessageBus** | — (无外部依赖) | AgentLoop, ChannelManager |
| **SessionManager** | — | AgentLoop |
| **ChannelManager** | MessageBus, 各 Channel 实现, Config | CLI (gateway) |
| **Provider** | litellm / httpx / openai | AgentLoop, MemoryStore, HeartbeatService |
| **CronService** | Config | CLI (gateway) → AgentLoop |
| **HeartbeatService** | Provider, Config | CLI (gateway) → AgentLoop |
| **SubagentManager** | ToolRegistry, Provider, SkillsLoader | AgentLoop (通过 spawn 工具) |
| **Config** | Pydantic | 几乎所有模块 |
| **CLI** | 所有模块 | 用户 |

---

## 核心数据流

### 1. 消息处理流程

```
用户发送消息
  → Channel 接收并校验 allowFrom
  → 封装为 InboundMessage (channel, sender_id, chat_id, content, media)
  → MessageBus.publish_inbound()
  → AgentLoop.run() 消费
  → SessionManager 加载会话历史
  → ContextBuilder 组装:
      System Prompt = Identity + Bootstrap + Memory + Skills + Runtime
      Messages = [system, ...history, user_message]
  → Provider.chat(messages, tools)
  → [有 tool_calls?]
      ├─ YES → 逐个执行工具 → 结果追加 → 重新调用 LLM (最多40轮)
      └─ NO  → 最终响应
  → 保存到 Session (JSONL 追加)
  → 检查是否需要记忆整合
  → OutboundMessage 发布到 MessageBus
  → ChannelManager 路由到对应 Channel
  → Channel 发送给用户
```

### 2. 记忆整合流程

```
未整合消息数 ≥ memory_window / 2
  → 提取旧消息
  → 构建整合 Prompt
  → LLM 调用 save_memory(history_entry, memory_update)
  → history_entry 追加到 HISTORY.md    (时间线日志)
  → memory_update 写入 MEMORY.md       (长期记忆)
  → session.last_consolidated 指针前移
```

### 3. 心跳流程

```
每 30 分钟触发
  → Phase 1: 读取 HEARTBEAT.md → LLM 决策 skip/run
      ├─ skip → 等待下一次
      └─ run  → Phase 2
  → Phase 2: AgentLoop.process_direct(tasks) → 完整工具循环
  → 结果推送给用户最活跃的渠道
```

### 4. 子 Agent 流程

```
主 Agent 调用 spawn(task, label)
  → SubagentManager 创建后台任务 (≤15 轮迭代)
  → 可用工具: 文件操作 + exec + web (无 message / spawn)
  → 完成后 → system channel 注入结果
  → 主 Agent 收到 → 整理后回复用户
```

---

## 配置体系

```
~/.comobot/
├── config.json                 # 主配置文件
│   ├── providers               #   LLM API 密钥 (anthropic, openai, deepseek, ...)
│   ├── agents.defaults         #   模型/温度/最大迭代/记忆窗口
│   ├── channels                #   各渠道 token + allowFrom 白名单
│   ├── tools                   #   exec 超时/MCP servers/Brave API key
│   └── gateway                 #   心跳间隔
│
└── workspace/                  # 工作空间 (Agent 可读写)
    ├── AGENTS.md               #   Agent 行为指令
    ├── SOUL.md                 #   人格定义
    ├── USER.md                 #   用户画像
    ├── TOOLS.md                #   工具约束
    ├── HEARTBEAT.md            #   心跳任务清单
    ├── memory/
    │   ├── MEMORY.md           #   长期记忆
    │   └── HISTORY.md          #   历史日志
    ├── sessions/               #   会话存储 (JSONL)
    ├── skills/                 #   用户自定义技能
    └── cron/
        └── jobs.json           #   定时任务持久化
```

---

## 安全机制

| 机制 | 实现位置 | 说明 |
|------|---------|------|
| **发送者白名单** | `channels/base.py` | 每个渠道 `allowFrom` 配置，空列表 = 拒绝所有 |
| **工作空间隔离** | `tools/base.py` | `restrictToWorkspace=true` 时文件操作仅限工作空间 |
| **危险命令拦截** | `tools/shell.py` | 黑名单: rm -rf, format, dd, shutdown 等 |
| **执行超时** | `tools/shell.py` | 默认 60 秒，可配置 |
| **输出截断** | `tools/shell.py` | 工具输出限制 10K 字符 |
| **MCP 超时** | `tools/mcp.py` | 每个调用默认 30 秒 |
| **不可信标记** | `agent/context.py` | 运行时上下文 (时间/渠道) 标记为 untrusted |

---

## 扩展指南

| 扩展类型 | 操作方式 | 是否需要改代码 |
|---------|---------|--------------|
| 新增 LLM 提供者 | `schema.py` 加字段 + `registry.py` 加 ProviderSpec | 是 |
| 新增渠道 | 继承 `BaseChannel` + 注册到 `ChannelManager` | 是 |
| 新增工具 | 继承 `Tool` + 注册到 `AgentLoop` | 是 |
| 新增技能 | 创建 `workspace/skills/{name}/SKILL.md` | **否** |
| 定制 Agent 行为 | 编辑 SOUL.md / AGENTS.md / USER.md | **否** |
| 新增 MCP 工具 | config.json 添加 `mcpServers` 配置 | **否** |

---

## 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.11+ / TypeScript (bridge) |
| 异步框架 | asyncio |
| 配置校验 | Pydantic v2 |
| CLI | Typer |
| 日志 | loguru |
| LLM 路由 | litellm |
| 代码规范 | ruff (E, F, I, N, W; 行宽 100) |
| 测试 | pytest + pytest-asyncio |
| 部署 | Docker / docker-compose |
