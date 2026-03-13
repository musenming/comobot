# comobot — 项目结构文档

> 轻量级个人 AI 助手框架，多渠道支持。核心代码约 17,000 行 Python + 370 行 TypeScript + Vue 3 前端。

---

## 目录总览

```
comobot/
├── comobot/                       # 核心 Python 包 (93 文件, ~17K 行)
│   ├── agent/                     # Agent 核心引擎
│   │   ├── loop.py                #   主处理循环 — 消息消费、LLM 调用、工具执行
│   │   ├── context.py             #   上下文构建器 — 系统提示词组装
│   │   ├── memory.py              #   两层记忆系统 — MEMORY.md + 每日日志
│   │   ├── memory_search.py       #   记忆搜索引擎 — BM25 + 向量混合检索 (FTS5)
│   │   ├── skills.py              #   技能加载器 — 发现、校验、渐进加载
│   │   ├── subagent.py            #   子 Agent 管理 — 后台任务派生与回收
│   │   └── tools/                 #   内置工具集
│   │       ├── base.py            #     Tool 抽象基类 + 参数校验
│   │       ├── registry.py        #     ToolRegistry 工具注册表
│   │       ├── filesystem.py      #     read_file / write_file / edit_file / list_dir
│   │       ├── shell.py           #     exec — Shell 命令执行 (带安全拦截)
│   │       ├── web.py             #     web_search (Brave) / web_fetch (Jina)
│   │       ├── message.py         #     message — 跨渠道发消息
│   │       ├── spawn.py           #     spawn — 启动后台子 Agent
│   │       ├── cron.py            #     cron — 定时任务管理
│   │       ├── mcp.py             #     MCP 服务器工具动态加载
│   │       └── memory_tools.py    #     memory_search / memory_get 记忆工具
│   │
│   ├── api/                       # FastAPI REST API + WebSocket
│   │   ├── app.py                 #   FastAPI 应用工厂 — 路由注册、中间件、CORS
│   │   ├── deps.py                #   依赖注入 — get_db / get_current_user
│   │   └── routes/                #   API 路由模块
│   │       ├── auth.py            #     /api/auth — JWT 登录/注册
│   │       ├── chat.py            #     /api/chat — Web 聊天接口
│   │       ├── sessions.py        #     /api/sessions — 会话管理
│   │       ├── channels.py        #     /api/channels — 渠道状态与配置
│   │       ├── cron.py            #     /api/cron — 定时任务 CRUD
│   │       ├── skills.py          #     /api/skills — 技能列表与管理
│   │       ├── providers.py       #     /api/providers — LLM 提供者管理
│   │       ├── workflows.py       #     /api/workflows — 工作流 CRUD
│   │       ├── dashboard.py       #     /api/dashboard — 仪表盘统计
│   │       ├── logs.py            #     /api/logs — 审计日志查询
│   │       ├── settings.py        #     /api/settings — 系统设置
│   │       ├── setup.py           #     /api/setup — 初始化向导
│   │       ├── webhook.py         #     /api/webhook — 外部 Webhook 接入
│   │       ├── health.py          #     /api/health — 健康检查
│   │       └── ws.py              #     /ws/* — WebSocket (chat/logs/status/cron)
│   │
│   ├── channels/                  # 渠道适配层 (11 个渠道)
│   │   ├── base.py                #   BaseChannel 抽象基类
│   │   ├── manager.py             #   ChannelManager — 渠道生命周期管理与消息路由
│   │   ├── telegram.py            #   Telegram Bot API 轮询
│   │   ├── discord.py             #   Discord Gateway WebSocket
│   │   ├── slack.py               #   Slack Socket Mode
│   │   ├── whatsapp.py            #   WhatsApp (Node.js Bridge)
│   │   ├── feishu.py              #   Feishu WebSocket 长连接
│   │   ├── dingtalk.py            #   钉钉 Stream 模式
│   │   ├── email.py               #   Email (IMAP 轮询 + SMTP)
│   │   ├── matrix.py              #   Matrix 协议 (可选 E2E 加密)
│   │   ├── qq.py                  #   QQ Bot SDK + WebSocket
│   │   └── mochat.py              #   Mochat Socket.IO
│   │
│   ├── providers/                 # LLM 提供者抽象层
│   │   ├── base.py                #   LLMProvider 抽象基类 + LLMResponse
│   │   ├── registry.py            #   ProviderSpec 注册表 — 模型路由与自动检测
│   │   ├── litellm_provider.py    #   LiteLLM 通用提供者 (100+ 后端)
│   │   ├── custom_provider.py     #   OpenAI 兼容 API 直连
│   │   ├── openai_codex_provider.py  # OAuth 认证提供者
│   │   ├── key_rotator.py         #   API Key 轮换策略
│   │   └── transcription.py       #   语音转文字
│   │
│   ├── db/                        # 数据库层 (SQLite + WAL)
│   │   ├── connection.py          #   aiosqlite 异步连接封装
│   │   ├── migrations.py          #   版本化迁移 — (version, name, sql) 三元组
│   │   └── audit.py               #   审计日志写入
│   │
│   ├── security/                  # 安全模块
│   │   ├── auth.py                #   JWT 认证 + 密码哈希
│   │   └── crypto.py              #   AES-GCM 凭据加密
│   │
│   ├── session/                   # 会话管理
│   │   ├── manager.py             #   Session 模型 + SessionManager 接口
│   │   └── sqlite_manager.py      #   SQLiteSessionManager 持久化实现
│   │
│   ├── knowhow/                   # Know-how 经验学习系统
│   │   ├── __init__.py            #   导出 KnowhowStore
│   │   ├── store.py               #   Know-how CRUD (Markdown + SQLite)
│   │   └── extractor.py           #   LLM 摘要提取
│   │
│   ├── orchestrator/              # 工作流编排 (可选)
│   │   ├── engine.py              #   Orchestrator 执行引擎
│   │   ├── templates.py           #   工作流模板解析
│   │   └── variables.py           #   变量上下文管理
│   │
│   ├── cli/                       # 命令行接口
│   │   └── commands.py            #   Typer CLI — onboard / gateway / agent / status
│   │
│   ├── config/                    # 配置管理
│   │   ├── schema.py              #   Pydantic v2 配置模型定义
│   │   └── loader.py              #   配置加载 / 保存 / 迁移
│   │
│   ├── cron/                      # 定时任务服务
│   │   ├── service.py             #   CronService — 调度循环
│   │   ├── sqlite_store.py        #   SQLite 持久化存储
│   │   └── types.py               #   CronJob / CronSchedule / CronPayload 类型
│   │
│   ├── heartbeat/                 # 周期唤醒服务
│   │   └── service.py             #   HeartbeatService — 两阶段决策+执行
│   │
│   ├── bus/                       # 异步消息总线
│   │   ├── events.py              #   InboundMessage / OutboundMessage 事件定义
│   │   └── queue.py               #   MessageBus — 双向 asyncio.Queue
│   │
│   ├── templates/                 # 提示词模板
│   │   ├── AGENTS.md              #   Agent 行为指令
│   │   ├── SOUL.md                #   人格与价值观
│   │   ├── TOOLS.md               #   工具使用约束
│   │   ├── USER.md                #   用户画像模板
│   │   ├── IDENTITY.md            #   身份标识模板
│   │   ├── BOOTSTRAP.md           #   引导模板
│   │   ├── HEARTBEAT.md           #   心跳任务模板
│   │   └── memory/
│   │       └── MEMORY.md          #   长期记忆初始模板
│   │
│   ├── skills/                    # 内置技能 (8 个 SKILL.md)
│   │   ├── cron/SKILL.md          #   定时提醒与任务调度
│   │   ├── memory/SKILL.md        #   记忆管理指令
│   │   ├── github/SKILL.md        #   GitHub CLI 集成
│   │   ├── weather/SKILL.md       #   天气查询 (wttr.in / Open-Meteo)
│   │   ├── summarize/SKILL.md     #   URL/文件/YouTube 摘要
│   │   ├── tmux/SKILL.md          #   远程 tmux 会话控制
│   │   ├── clawhub/SKILL.md       #   ClawHub 技能仓库 (安装前强制安全审查)
│   │   ├── skill-vetter/SKILL.md  #   技能安全审查 — 安装前红旗检测与风险分级
│   │   └── skill-creator/SKILL.md #   技能创建向导
│   │
│   └── utils/                     # 工具函数
│       ├── helpers.py             #   通用辅助函数
│       └── migrate.py             #   数据迁移工具
│
├── web/                           # Vue 3 + Naive UI 前端 (42 文件)
│   └── src/
│       ├── main.ts                #   入口
│       ├── App.vue                #   根组件
│       ├── api/
│       │   └── client.ts          #   Axios API 客户端 (Bearer JWT 拦截器)
│       ├── router/
│       │   └── index.ts           #   Vue Router 路由定义
│       ├── stores/                #   Pinia 状态管理
│       │   ├── auth.ts            #     认证状态
│       │   └── theme.ts           #     主题状态
│       ├── theme/
│       │   └── index.ts           #   Naive UI 主题定制
│       ├── composables/
│       │   └── useWebSocket.ts    #   WebSocket 连接复用 Composable
│       ├── views/                 #   页面视图
│       │   ├── ChatView.vue       #     实时聊天 (WebSocket)
│       │   ├── SessionsView.vue   #     会话管理 (历史浏览)
│       │   ├── DashboardView.vue  #     仪表盘
│       │   ├── ChannelsView.vue   #     渠道配置
│       │   ├── ProvidersView.vue  #     LLM 提供者管理
│       │   ├── SkillsView.vue     #     技能管理
│       │   ├── CronView.vue       #     定时任务管理
│       │   ├── MemoryView.vue     #     记忆查看
│       │   ├── WorkflowsView.vue  #     工作流列表
│       │   ├── WorkflowEditorView.vue  # 工作流编辑器
│       │   ├── LogsView.vue       #     审计日志
│       │   ├── SettingsView.vue   #     系统设置
│       │   ├── LoginView.vue      #     登录页
│       │   └── SetupView.vue      #     初始化向导
│       └── components/            #   通用组件
│           ├── AppSidebar.vue     #     侧边栏导航 (折叠/抽屉)
│           ├── PageLayout.vue     #     页面布局容器 (响应式)
│           ├── ChatBubble.vue     #     聊天气泡 (Markdown 渲染)
│           ├── MarkdownRenderer.vue  #  Markdown 渲染器
│           ├── ChannelCard.vue    #     渠道卡片
│           ├── ChannelConfigDrawer.vue  # 渠道配置抽屉
│           ├── ProviderCard.vue   #     提供者卡片
│           ├── ProviderDrawer.vue #     提供者配置抽屉
│           ├── WorkflowCard.vue   #     工作流卡片
│           ├── CronExpressionInput.vue  # Cron 表达式输入
│           ├── StatCard.vue       #     统计卡片
│           ├── SparklineChart.vue #     迷你图表
│           ├── DataTable.vue      #     数据表格
│           ├── StatusBadge.vue    #     状态徽标
│           ├── SkeletonCard.vue   #     骨架屏卡片
│           ├── EmptyState.vue     #     空状态占位
│           ├── ConfirmDialog.vue  #     确认对话框
│           ├── CopyButton.vue     #     复制按钮
│           └── SecretInput.vue    #     密钥输入框
│
├── bridge/                        # WhatsApp Node.js 桥接 (370 行 TS)
│   ├── src/
│   │   ├── index.ts               #   入口
│   │   ├── server.ts              #   WebSocket 服务
│   │   ├── whatsapp.ts            #   WhatsApp Web 客户端
│   │   └── types.d.ts             #   类型定义
│   ├── package.json
│   └── tsconfig.json
│
├── tests/                         # 测试套件 (21 文件)
│   ├── test_api.py                #   REST API 端点测试
│   ├── test_commands.py           #   CLI 命令测试
│   ├── test_cli_input.py          #   CLI 输入处理测试
│   ├── test_context_prompt_cache.py  # 上下文缓存测试
│   ├── test_consolidate_offset.py #   记忆整合偏移测试
│   ├── test_cron_commands.py      #   Cron 命令解析测试
│   ├── test_cron_service.py       #   Cron 服务测试
│   ├── test_db.py                 #   数据库层测试
│   ├── test_email_channel.py      #   Email 渠道测试
│   ├── test_feishu_post_content.py  # 飞书消息测试
│   ├── test_heartbeat_service.py  #   心跳服务测试
│   ├── test_key_rotator.py        #   Key 轮换测试
│   ├── test_loop_save_turn.py     #   AgentLoop 保存测试
│   ├── test_matrix_channel.py     #   Matrix 渠道测试
│   ├── test_memory_consolidation_types.py  # 记忆整合类型测试
│   ├── test_message_tool.py       #   消息工具测试
│   ├── test_message_tool_suppress.py  # 消息抑制测试
│   ├── test_orchestrator.py       #   工作流编排测试
│   ├── test_security.py           #   安全模块测试
│   ├── test_task_cancel.py        #   任务取消测试
│   └── test_tool_validation.py    #   工具参数校验测试
│
├── pyproject.toml                 # 项目元数据 + 依赖 + ruff/pytest 配置
├── Dockerfile                     # 容器化部署
├── docker-compose.yml             # 编排配置
├── CLAUDE.md                      # Claude Code 项目指令 (索引)
├── structure.md                   # 项目结构文档 (本文件)
├── README.md                      # 项目说明
├── INSTALL.md                     # 安装指南
├── SECURITY.md                    # 安全策略
└── LICENSE                        # MIT 许可证
```

---

## 架构总图

```
┌───────────────────────────────────────────────────────────────────────┐
│                          用户 / 外部平台                                │
│  Telegram  Discord  Slack  Feishu  钉钉  Email  WhatsApp  QQ  Matrix   │
└───┬────────┬───────┬──────┬─────┬──────┬───────┬──────┬──────┬───────┘
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
             │  │ │ 技能摘要  │ │    │ cron  MCP  memory│  │
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
         ┌──────────▼────────┐  ┌───────▼────────────────┐
         │  SessionManager   │  │  Memory 系统            │
         │  (SQLite 持久化)   │  │  MemoryStore +          │
         └───────────────────┘  │  MemorySearchEngine     │
                                │  (BM25 + 向量混合检索)   │
                                └────────────────────────┘
                                         │
                              ┌──────────┴──────────┐
                              │                     │
                        MEMORY.md            每日日志 .md
                      (始终加载上下文)        (按需检索)

             ┌───────────────┐    ┌────────────────┐
             │  CronService  │    │HeartbeatService│
             │  (定时任务调度) │    │ (周期唤醒决策)  │
             │               │    │                │
             │ SQLite 持久化  │    │ Phase1: 决策   │
             └───────┬───────┘    │ Phase2: 执行   │
                     │            └───────┬────────┘
                     └────────┬───────────┘
                              ▼
                   AgentLoop.process_direct()

┌────────────────────────────────────────────────────────────┐
│                  FastAPI + WebSocket 层                      │
│                                                             │
│  REST API:                    WebSocket:                    │
│  /api/auth     /api/chat      /ws/chat   (实时聊天)         │
│  /api/sessions /api/channels  /ws/logs   (审计日志流)       │
│  /api/cron     /api/skills    /ws/status (Agent/渠道状态)   │
│  /api/providers /api/workflows /ws/cron  (定时任务事件)     │
│  /api/dashboard /api/settings                               │
│  /api/logs     /api/setup                                   │
│  /api/health   /api/webhook                                 │
└─────────────────────────┬──────────────────────────────────┘
                          │
              ┌───────────▼───────────┐
              │  Web UI (Vue 3)       │
              │  Naive UI + Pinia     │
              │  WebSocket 实时通信     │
              └───────────────────────┘
```

---

## 模块关系矩阵

| 模块 | 依赖 | 被依赖 |
|:---|:---|:---|
| **AgentLoop** | MessageBus, SessionManager, MemoryStore, ContextBuilder, ToolRegistry, Provider, SubagentManager | CLI, CronService, HeartbeatService, API |
| **ContextBuilder** | SkillsLoader, MemoryStore, MemorySearchEngine, Config | AgentLoop |
| **MemoryStore** | Provider (用于整合时调 LLM) | AgentLoop, ContextBuilder |
| **MemorySearchEngine** | SQLite FTS5, 可选向量嵌入 | ContextBuilder, MemoryTools |
| **ToolRegistry** | 各 Tool 实现 | AgentLoop, SubagentManager |
| **MessageBus** | — (无外部依赖) | AgentLoop, ChannelManager |
| **SessionManager** | SQLite (aiosqlite) | AgentLoop, API |
| **ChannelManager** | MessageBus, 各 Channel 实现, Config | CLI (gateway) |
| **Provider** | litellm / httpx / openai | AgentLoop, MemoryStore, HeartbeatService |
| **CronService** | SQLite Store, Config | CLI (gateway) → AgentLoop |
| **HeartbeatService** | Provider, Config | CLI (gateway) → AgentLoop |
| **SubagentManager** | ToolRegistry, Provider, SkillsLoader | AgentLoop (通过 spawn 工具) |
| **Orchestrator** | AgentLoop (可选挂载) | API (workflows) |
| **Database** | aiosqlite | SessionManager, CronStore, API, AuditLog |
| **Security** | JWT (PyJWT), AES-GCM | API (认证中间件) |
| **Config** | Pydantic | 几乎所有模块 |
| **CLI** | 所有模块 | 用户 |
| **Web UI** | API + WebSocket | 用户 (浏览器) |

---

## 核心数据流

### 1. 消息处理流程

```
用户发送消息
  → Channel 接收并校验 allowFrom
  → 封装为 InboundMessage (channel, sender_id, chat_id, content, media)
  → MessageBus.publish_inbound()
  → AgentLoop.run() 消费
  → SessionManager 加载会话历史 (SQLite)
  → ContextBuilder 组装:
      System Prompt = Identity + Bootstrap + Memory + Skills + Runtime
      Messages = [system, ...history, user_message]
  → Provider.chat(messages, tools)
  → [有 tool_calls?]
      ├─ YES → 逐个执行工具 → 结果追加 → 重新调用 LLM (最多40轮)
      └─ NO  → 最终响应
  → _save_turn() 保存到 Session (SQLite)
  → 检查是否需要记忆整合
  → OutboundMessage 发布到 MessageBus
  → ChannelManager 路由到对应 Channel
  → Channel 发送给用户
  → WebSocket 广播到 Web UI (实时同步)
```

### 2. 记忆整合流程

```
未整合消息数 ≥ memory_window / 2
  → 提取旧消息
  → 构建整合 Prompt
  → LLM 调用 save_memory(history_entry, memory_update)
  → history_entry 写入每日日志 (YYYY-MM-DD.md)
  → memory_update 写入 MEMORY.md (长期记忆)
  → session.last_consolidated 指针前移
  → MemorySearchEngine 增量索引更新
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

### 5. Web UI 实时通信

```
浏览器 → WebSocket 连接 (/ws/chat, /ws/logs, /ws/status, /ws/cron)
  → ConnectionManager 管理连接池 (按类型分组)
  → 事件发生时 broadcast_*() 推送到所有客户端
  → 失败连接自动清理
  → 前端断连后 3 秒自动重连
```

---

## 数据库模型 (SQLite + WAL)

### 核心表

| 表名 | 用途 | 关键字段 |
|:---|:---|:---|
| `schema_version` | 迁移版本追踪 | version, applied_at |
| `admin` | 管理员认证 | username, password (bcrypt) |
| `sessions` | 会话元数据 | session_key (UNIQUE), last_consolidated |
| `messages` | 消息存储 | session_id (FK), role, content, tool_calls |
| `cron_jobs` | 定时任务 | schedule, payload, next_run_at, enabled |
| `workflows` | 工作流定义 | template, definition, trigger_rules |
| `workflow_runs` | 工作流执行记录 | status, variables, error |
| `credentials` | 加密凭据 | provider, encrypted (AES-GCM BLOB) |
| `allowed_users` | 访问白名单 | channel + user_id (UNIQUE), alias |
| `audit_log` | 审计日志 | level, module, event, detail |

### 迁移模式

```python
MIGRATIONS = [
    (1, "initial_schema", "CREATE TABLE ..."),
    # 追加新版本即可，run_migrations() 自动检测并执行
]
```

---

## 配置体系

```
~/.comobot/
├── config.json                    # 主配置文件
│   ├── providers                  #   LLM API 密钥 (anthropic, openai, deepseek, ...)
│   ├── agents.defaults            #   模型/温度/最大迭代/记忆窗口
│   ├── channels                   #   各渠道 token + allowFrom 白名单
│   ├── tools                      #   exec 超时/MCP servers/Brave API key
│   └── gateway                    #   端口 (18790) / 心跳间隔
│
└── workspace/                     # 工作空间 (Agent 可读写)
    ├── AGENTS.md                  #   Agent 行为指令
    ├── SOUL.md                    #   人格定义
    ├── USER.md                    #   用户画像
    ├── TOOLS.md                   #   工具约束
    ├── IDENTITY.md                #   身份标识
    ├── BOOTSTRAP.md               #   引导指令
    ├── HEARTBEAT.md               #   心跳任务清单
    ├── memory/
    │   ├── MEMORY.md              #   长期记忆
    │   └── YYYY-MM-DD.md          #   每日记忆日志
    ├── sessions/                  #   (历史遗留, 已迁移至 SQLite)
    ├── skills/                    #   用户自定义技能
    └── cron/                      #   (历史遗留, 已迁移至 SQLite)
```

---

## 安全机制

| 机制 | 实现位置 | 说明 |
|:---|:---|:---|
| **JWT 认证** | `security/auth.py` | Web API 全局认证中间件 |
| **密码哈希** | `security/auth.py` | bcrypt 加密存储 |
| **凭据加密** | `security/crypto.py` | AES-GCM 加密 API Key |
| **发送者白名单** | `channels/base.py` | 每个渠道 `allowFrom` 配置 |
| **工作空间隔离** | `tools/base.py` | `restrictToWorkspace=true` 时文件操作仅限工作空间 |
| **危险命令拦截** | `tools/shell.py` | 黑名单: rm -rf, format, dd, shutdown 等 |
| **执行超时** | `tools/shell.py` | 默认 60 秒，可配置 |
| **输出截断** | `tools/shell.py` | 工具输出限制 10K 字符 |
| **MCP 超时** | `tools/mcp.py` | 每个调用默认 30 秒 |
| **不可信标记** | `agent/context.py` | 运行时上下文 (时间/渠道) 标记为 untrusted |

---

## 扩展指南

| 扩展类型 | 操作方式 | 是否需要改代码 |
|:---|:---|:---|
| 新增 LLM 提供者 | `schema.py` 加字段 + `registry.py` 加 ProviderSpec | 是 |
| 新增渠道 | 继承 `BaseChannel` + 注册到 `ChannelManager` | 是 |
| 新增工具 | 继承 `Tool` + 注册到 `ToolRegistry` | 是 |
| 新增技能 | 创建 `workspace/skills/{name}/SKILL.md` | **否** |
| 定制 Agent 行为 | 编辑 SOUL.md / AGENTS.md / USER.md | **否** |
| 新增 MCP 工具 | config.json 添加 `mcpServers` 配置 | **否** |
| 新增 API 路由 | `api/routes/` 新建模块 + `app.py` 注册 router | 是 |

---

## 技术栈

| 类别 | 技术 |
|:---|:---|
| 语言 | Python 3.11+ / TypeScript (bridge) |
| 异步框架 | asyncio |
| Web 框架 | FastAPI + uvicorn |
| 前端 | Vue 3 + Naive UI + Pinia + Vue Router |
| 数据库 | SQLite + WAL + aiosqlite |
| 配置校验 | Pydantic v2 |
| CLI | Typer |
| 日志 | loguru |
| LLM 路由 | litellm |
| 认证 | JWT (PyJWT) + bcrypt |
| 加密 | AES-GCM (cryptography) |
| 代码规范 | ruff (E, F, I, N, W; 行宽 100) |
| 测试 | pytest + pytest-asyncio |
| 部署 | Docker / docker-compose |
