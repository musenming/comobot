# Comobot 前后端 API 接口定义文档

> 版本: 1.0 | 日期: 2026-03-06
>
> **Base URL**: `http://localhost:18790`（开发）/ `http://your-domain`（生产）
>
> **API Docs（Swagger UI）**: `GET /api/docs`（FastAPI 自动生成）

---

## 目录

1. [通用约定](#1-通用约定)
2. [认证鉴权](#2-认证鉴权)
3. [系统初始化](#3-系统初始化)
4. [仪表盘](#4-仪表盘)
5. [工作流编排](#5-工作流编排)
6. [模型提供者](#6-模型提供者)
7. [渠道管理](#7-渠道管理)
8. [会话与消息](#8-会话与消息)
9. [定时任务](#9-定时任务)
10. [审计日志](#10-审计日志)
11. [系统设置](#11-系统设置)
12. [Webhook 接入](#12-webhook-接入)
13. [实时推送（WebSocket）](#13-实时推送websocket)
14. [前端 axios 集成参考](#14-前端-axios-集成参考)
15. [接口现状与缺口清单](#15-接口现状与缺口清单)

---

## 1. 通用约定

### 1.1 请求格式

| 项目 | 规范 |
|------|------|
| 协议 | HTTPS（生产）/ HTTP（本地开发） |
| 数据格式 | `Content-Type: application/json` |
| 字符编码 | UTF-8 |
| 时间格式 | ISO 8601 字符串，如 `"2026-03-06T08:00:00"` |

### 1.2 认证方式

除 `/api/health`、`/api/setup/*`、`/api/auth/login`、`/webhook/*` 外，所有端点均需要 JWT 认证：

```http
Authorization: Bearer <access_token>
```

### 1.3 统一响应结构

**成功**：直接返回业务对象或数组（不统一包装）：

```json
{ "id": 1, "name": "my-workflow" }
```

**失败**：FastAPI 标准错误格式：

```json
{
  "detail": "错误描述字符串"
}
```

### 1.4 通用 HTTP 状态码

| 状态码 | 含义 |
|--------|------|
| `200` | 成功 |
| `400` | 请求参数错误 |
| `401` | 未认证或 Token 过期 |
| `403` | 权限不足（如 Webhook secret 校验失败） |
| `404` | 资源不存在 |
| `422` | 请求体校验失败（Pydantic）|
| `500` | 服务端内部错误 |

### 1.5 分页约定

当前大多数列表接口**未实现分页**，通过 `LIMIT` 硬限制返回数量。前端在调用时需关注此限制，后续迭代需补充 `page` / `page_size` 参数。

---

## 2. 认证鉴权

### 2.1 管理员登录

```
POST /api/auth/login
```

**认证**：无需（公开端点）

**Request Body**

```json
{
  "username": "admin",
  "password": "your-password"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | `string` | ✓ | 管理员用户名，默认 `"admin"` |
| `password` | `string` | ✓ | 明文密码（HTTPS 传输） |

**Response 200**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `access_token` | `string` | JWT Token，有效期 24 小时 |
| `token_type` | `string` | 固定为 `"bearer"` |

**Response 401**

```json
{ "detail": "Invalid credentials" }
```

**前端处理**：登录成功后将 `access_token` 存入 `localStorage`，后续请求在 `Authorization` Header 中携带。

---

### 2.2 刷新 Token

```
POST /api/auth/refresh
```

**认证**：需要 Bearer Token（用旧 Token 换新 Token）

**Request Body**：无

**Response 200**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**使用建议**：前端在 Token 即将过期时（距过期 < 30 分钟）调用此接口静默刷新，避免用户被强制登出。

---

## 3. 系统初始化

### 3.1 查询初始化状态

```
GET /api/setup/status
```

**认证**：无需（公开端点，路由守卫使用）

**Response 200**

```json
{
  "setup_complete": false
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `setup_complete` | `boolean` | `false` 表示尚未初始化，前端应跳转至 `/setup` |

**前端路由守卫逻辑**：

```typescript
// router/index.ts 中 beforeEach
const res = await fetch('/api/setup/status')
const { setup_complete } = await res.json()
if (!setup_complete) return '/setup'
```

---

### 3.2 提交初始化配置

```
POST /api/setup
```

**认证**：无需（公开端点，仅首次可调用）

**Request Body**

```json
{
  "admin_username": "admin",
  "admin_password": "mypassword123",
  "provider": "openai",
  "api_key": "sk-xxxxxxxxxxxx",
  "api_base": null,
  "telegram_token": "1234567890:XXXXXXXXXXXXXXX",
  "telegram_mode": "polling",
  "allowed_users": ["123456789", "987654321"]
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `admin_username` | `string` | ✗ | `"admin"` | 管理员用户名 |
| `admin_password` | `string` | ✓ | — | 密码，最少 8 位 |
| `provider` | `string` | ✗ | `null` | LLM 提供者，如 `"openai"`, `"anthropic"` |
| `api_key` | `string` | ✗ | `null` | LLM API Key，AES-256-GCM 加密存储 |
| `api_base` | `string` | ✗ | `null` | 自定义 API Base URL（本地推理端点） |
| `telegram_token` | `string` | ✗ | `null` | Telegram Bot Token |
| `telegram_mode` | `string` | ✗ | `"polling"` | `"polling"` 或 `"webhook"` |
| `allowed_users` | `string[]` | ✗ | `null` | Telegram 白名单用户 ID 列表 |

**Response 200**

```json
{
  "success": true,
  "message": "Setup completed successfully"
}
```

**Response 400**（已初始化 / 密码过短）

```json
{ "detail": "Setup already completed" }
```

---

### 3.3 健康检查

```
GET /api/health
```

**认证**：无需

**Response 200**

```json
{ "status": "ok" }
```

**用途**：Docker 健康检查、前端 WebSocket 重连前的连通性测试。

---

## 4. 仪表盘

### 4.1 获取统计数据

```
GET /api/dashboard
```

**认证**：需要 Bearer Token

**Response 200**

```json
{
  "total_sessions": 128,
  "total_messages": 4096,
  "total_workflows": 5,
  "active_workflows": 3,
  "cron_jobs": 2,
  "recent_errors": 0
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `total_sessions` | `integer` | 历史会话总数 |
| `total_messages` | `integer` | 全部消息条数 |
| `total_workflows` | `integer` | 工作流总数 |
| `active_workflows` | `integer` | 已启用（`enabled=1`）的工作流数 |
| `cron_jobs` | `integer` | 定时任务总数 |
| `recent_errors` | `integer` | 近 24 小时 `error` 级日志条数 |

> **UI 注意**：`recent_errors > 0` 时，对应数字卡片应高亮为红色。

---

## 5. 工作流编排

### 5.1 获取工作流列表

```
GET /api/workflows
```

**认证**：需要 Bearer Token

**Response 200** — `WorkflowItem[]`

```json
[
  {
    "id": 1,
    "name": "智能客服 Bot",
    "description": "接收用户消息并智能回复",
    "template": "smart_customer_service",
    "enabled": 1,
    "trigger_rules": "{\"channel\":\"telegram\",\"prefix\":\"/chat\"}",
    "created_at": "2026-03-01T10:00:00",
    "updated_at": "2026-03-05T14:23:00"
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `integer` | 主键 |
| `name` | `string` | 工作流名称（唯一） |
| `description` | `string` | 描述 |
| `template` | `string \| null` | 使用的模板 ID；`null` 表示自定义 |
| `enabled` | `0 \| 1` | 是否启用（注意后端返回整数，前端转布尔处理） |
| `trigger_rules` | `string \| null` | JSON 字符串，触发规则（前端需 `JSON.parse`） |
| `created_at` | `string` | 创建时间 |
| `updated_at` | `string` | 最后更新时间 |

---

### 5.2 获取单个工作流

```
GET /api/workflows/{workflow_id}
```

**认证**：需要 Bearer Token

**Path Params**

| 参数 | 类型 | 说明 |
|------|------|------|
| `workflow_id` | `integer` | 工作流 ID |

**Response 200** — `WorkflowDetail`

```json
{
  "id": 1,
  "name": "智能客服 Bot",
  "description": "接收用户消息并智能回复",
  "template": "smart_customer_service",
  "enabled": 1,
  "trigger_rules": { "channel": "telegram", "prefix": "/chat" },
  "definition": {
    "nodes": [
      { "id": "trigger", "type": "trigger", "data": { "trigger_type": "message" } },
      { "id": "llm", "type": "llm_call", "data": { "system_prompt": "You are helpful.", "model": "gpt-4o" } },
      { "id": "reply", "type": "response", "data": { "content": "{{llm.response}}", "channel": "{{trigger.channel}}", "chat_id": "{{trigger.chat_id}}" } }
    ],
    "edges": [
      { "source": "trigger", "target": "llm" },
      { "source": "llm", "target": "reply" }
    ]
  },
  "created_at": "2026-03-01T10:00:00",
  "updated_at": "2026-03-05T14:23:00"
}
```

> 与列表接口的区别：`definition` 和 `trigger_rules` 字段已被**反序列化为对象**（后端 `json.loads` 处理）。

**Response 404**

```json
{ "detail": "Workflow not found" }
```

---

### 5.3 创建工作流（自定义）

```
POST /api/workflows
```

**认证**：需要 Bearer Token

**Request Body**

```json
{
  "name": "我的工作流",
  "description": "处理用户消息",
  "template": null,
  "definition": {
    "nodes": [
      { "id": "trigger", "type": "trigger", "data": { "trigger_type": "message" } }
    ],
    "edges": []
  },
  "trigger_rules": {
    "channel": "telegram",
    "keywords": ["帮助", "help"],
    "prefix": "/help"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | `string` | ✓ | 工作流名称，需唯一 |
| `description` | `string` | ✗ | 描述，默认空字符串 |
| `template` | `string \| null` | ✗ | 模板标识 |
| `definition` | `object` | ✓ | 流程定义对象，含 `nodes` 和 `edges` |
| `trigger_rules` | `object \| null` | ✗ | 触发匹配规则 |

**`trigger_rules` 字段说明**

| 字段 | 类型 | 说明 |
|------|------|------|
| `channel` | `string` | 指定渠道，如 `"telegram"`；`null` 表示匹配所有渠道 |
| `keywords` | `string[]` | 关键词列表（OR 匹配，大小写不敏感） |
| `prefix` | `string` | 消息前缀匹配，如 `"/chat"` |

**`definition.nodes` 节点类型**

| `type` 值 | 说明 | `data` 字段 |
|-----------|------|------------|
| `trigger` | 触发器 | `trigger_type`: `"message"` \| `"cron"` \| `"webhook"` \| `"manual"` |
| `llm_call` | LLM 调用 | `system_prompt`, `model`, `user_message`, `temperature`, `max_tokens` |
| `tool` | 工具执行 | `tool_type`: `"http_request"`; `url`, `method` |
| `condition` | 条件分支 | `expression` |
| `response` | 发送消息 | `content`, `channel`, `chat_id` |
| `delay` | 延时 | `delay_seconds` |
| `subagent` | 子 Agent | `task_description`, `max_iterations` |

**Response 200**

```json
{ "id": 6, "name": "我的工作流" }
```

---

### 5.4 更新工作流

```
PUT /api/workflows/{workflow_id}
```

**认证**：需要 Bearer Token

**Path Params**

| 参数 | 类型 | 说明 |
|------|------|------|
| `workflow_id` | `integer` | 工作流 ID |

**Request Body**（所有字段均可选，仅更新传入字段）

```json
{
  "name": "新名称",
  "description": "新描述",
  "enabled": false,
  "definition": { "nodes": [], "edges": [] },
  "trigger_rules": { "channel": "slack" }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `string \| null` | 新名称 |
| `description` | `string \| null` | 新描述 |
| `enabled` | `boolean \| null` | 启用/停用 |
| `definition` | `object \| null` | 新的流程定义 |
| `trigger_rules` | `object \| null` | 新的触发规则 |

**Response 200**

```json
{ "id": 1, "updated": true }
```

**Response 400**（body 未传任何字段）

```json
{ "detail": "No fields to update" }
```

---

### 5.5 删除工作流

```
DELETE /api/workflows/{workflow_id}
```

**认证**：需要 Bearer Token

**Response 200**

```json
{ "deleted": true }
```

---

### 5.6 手动执行工作流

```
POST /api/workflows/{workflow_id}/execute
```

**认证**：需要 Bearer Token

**Request Body**：无（使用固定 trigger_data）

**Response 200**（执行成功）

```json
{
  "status": "completed",
  "variables": {
    "trigger.message": "Manual trigger",
    "trigger.channel": "web",
    "trigger.chat_id": "admin",
    "llm.response": "你好！有什么我可以帮助你的？"
  }
}
```

**Response 200**（执行失败）

```json
{
  "status": "failed",
  "error": "Workflow 3 not found or disabled"
}
```

> **UI 注意**：此接口用于「Live Debug」面板的「Run Now」按钮，前端应根据 `status` 字段决定渲染成功或失败状态。

---

### 5.7 获取工作流执行记录

```
GET /api/workflows/{workflow_id}/runs
```

**认证**：需要 Bearer Token

**Response 200** — `WorkflowRun[]`（最近 50 条）

```json
[
  {
    "id": 42,
    "workflow_id": 1,
    "trigger_data": "{\"message\":\"Manual trigger\"}",
    "status": "completed",
    "variables": "{\"llm.response\":\"你好！\"}",
    "error": null,
    "started_at": "2026-03-06T09:00:00",
    "finished_at": "2026-03-06T09:00:03"
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `integer` | 执行记录 ID |
| `workflow_id` | `integer` | 所属工作流 ID |
| `trigger_data` | `string` | JSON 字符串，触发数据快照 |
| `status` | `"running" \| "completed" \| "failed"` | 执行状态 |
| `variables` | `string \| null` | JSON 字符串，执行结束时的变量快照 |
| `error` | `string \| null` | 失败时的错误信息 |
| `started_at` | `string` | 开始时间 |
| `finished_at` | `string \| null` | 结束时间；`running` 时为 `null` |

---

### 5.8 获取模板列表

```
GET /api/workflows/templates
```

**认证**：需要 Bearer Token

**Response 200** — `WorkflowTemplate[]`

```json
[
  {
    "id": "smart_customer_service",
    "name": "Smart Customer Service",
    "description": "Receive user message -> LLM answer -> Reply to user",
    "params": [
      {
        "key": "system_prompt",
        "label": "System Prompt",
        "type": "textarea",
        "default": "You are a helpful customer service assistant."
      },
      {
        "key": "model",
        "label": "Model",
        "type": "text",
        "default": ""
      }
    ]
  },
  {
    "id": "scheduled_summary",
    "name": "Scheduled Summary",
    "description": "Cron trigger -> Fetch URL -> LLM summarize -> Push to channel",
    "params": [
      { "key": "url", "label": "URL to summarize", "type": "text", "default": "" },
      { "key": "cron_expr", "label": "Cron Expression", "type": "text", "default": "0 9 * * *" },
      { "key": "channel", "label": "Target Channel", "type": "text", "default": "telegram" },
      { "key": "chat_id", "label": "Target Chat ID", "type": "text", "default": "" }
    ]
  },
  {
    "id": "message_forwarder",
    "name": "Message Forwarder",
    "description": "Receive message -> Match condition -> Forward to target channel",
    "params": [
      { "key": "keywords", "label": "Match Keywords (comma separated)", "type": "text", "default": "" },
      { "key": "target_channel", "label": "Target Channel", "type": "text", "default": "telegram" },
      { "key": "target_chat_id", "label": "Target Chat ID", "type": "text", "default": "" }
    ]
  },
  {
    "id": "document_assistant",
    "name": "Document Assistant",
    "description": "Receive file -> Parse content -> LLM analyze -> Reply",
    "params": [
      { "key": "analysis_prompt", "label": "Analysis Prompt", "type": "textarea", "default": "Analyze the following document and provide key insights." }
    ]
  }
]
```

**`params[].type`** 枚举值：

| 值 | UI 渲染 |
|----|---------|
| `"text"` | 单行输入框 |
| `"textarea"` | 多行文本框 |
| `"select"` | 下拉选择（预留） |

---

### 5.9 从模板创建工作流

```
POST /api/workflows/from-template
```

**认证**：需要 Bearer Token

**Request Body**

```json
{
  "template_id": "smart_customer_service",
  "name": "我的客服 Bot",
  "params": {
    "system_prompt": "你是一个专业的中文客服助手。",
    "model": "gpt-4o"
  },
  "trigger_rules": {
    "channel": "telegram",
    "prefix": "/cs"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `template_id` | `string` | ✓ | 模板 ID（来自 5.8 接口） |
| `name` | `string` | ✓ | 工作流名称 |
| `params` | `object` | ✗ | 模板参数键值对（键对应 `params[].key`） |
| `trigger_rules` | `object \| null` | ✗ | 触发规则 |

**Response 200**

```json
{ "id": 7, "name": "我的客服 Bot" }
```

---

## 6. 模型提供者

### 6.1 获取已配置的提供者列表

```
GET /api/providers
```

**认证**：需要 Bearer Token

**Response 200** — `ProviderItem[]`

```json
[
  { "provider": "openai", "key_name": "api_key" },
  { "provider": "anthropic", "key_name": "api_key" },
  { "provider": "telegram", "key_name": "bot_token" }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `provider` | `string` | 提供者标识，如 `"openai"`, `"anthropic"`, `"telegram"` |
| `key_name` | `string` | 凭证类型，如 `"api_key"`, `"bot_token"` |

> **安全说明**：响应中**不包含**凭证明文（AES-256-GCM 加密存储，不可逆返回）。前端展示时可根据 `key_name` 标注「已配置」状态。

---

### 6.2 添加/更新提供者凭证

```
POST /api/providers
```

**认证**：需要 Bearer Token

**Request Body**

```json
{
  "provider": "openai",
  "key_name": "api_key",
  "value": "sk-xxxxxxxxxxxxxxxxxxxx"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `provider` | `string` | ✓ | 提供者标识 |
| `key_name` | `string` | ✗ | 凭证类型，默认 `"api_key"` |
| `value` | `string` | ✓ | 凭证明文（传输后立即 AES 加密存储） |

**支持的 `provider` 值**

| `provider` | 说明 |
|-----------|------|
| `openai` | OpenAI |
| `anthropic` | Anthropic Claude |
| `gemini` | Google Gemini |
| `deepseek` | DeepSeek |
| `qwen` | 阿里云通义千问 |
| `zhipu` | 智谱 AI / ChatGLM |
| `ollama` | 本地 Ollama（仅需 `api_base`） |
| `vllm` | 本地 vLLM 端点 |
| `telegram` | Telegram Bot Token（`key_name: "bot_token"`） |

**Response 200**

```json
{ "provider": "openai", "key_name": "api_key", "stored": true }
```

---

### 6.3 删除提供者凭证

```
DELETE /api/providers/{provider}/{key_name}
```

**认证**：需要 Bearer Token

**Path Params**

| 参数 | 类型 | 说明 |
|------|------|------|
| `provider` | `string` | 提供者标识 |
| `key_name` | `string` | 凭证类型 |

**Response 200**

```json
{ "deleted": true }
```

**Response 404**

```json
{ "detail": "Credential not found" }
```

---

### 6.4 测试提供者连通性

```
POST /api/providers/{provider}/test
```

**认证**：需要 Bearer Token

**Path Params**

| 参数 | 类型 | 说明 |
|------|------|------|
| `provider` | `string` | 提供者标识 |

**Response 200**

```json
{ "provider": "openai", "status": "ok", "key_prefix": "sk-abcd..." }
```

> **当前限制**：该接口仅验证凭证存在性（返回 Key 前缀），**未实际发起 LLM API 调用**。如需真实连通性测试，后续需扩展此接口。

**Response 404**

```json
{ "detail": "No API key found for this provider" }
```

---

## 7. 渠道管理

### 7.1 获取渠道列表

```
GET /api/channels
```

**认证**：需要 Bearer Token

**Response 200** — `ChannelItem[]`

```json
[
  { "name": "telegram", "type": "telegram" },
  { "name": "discord", "type": "discord" },
  { "name": "slack", "type": "slack" },
  { "name": "feishu", "type": "feishu" },
  { "name": "dingtalk", "type": "dingtalk" },
  { "name": "email", "type": "email" },
  { "name": "whatsapp", "type": "whatsapp" },
  { "name": "qq", "type": "qq" },
  { "name": "matrix", "type": "matrix" },
  { "name": "mochat", "type": "mochat" }
]
```

> **当前限制**：返回静态列表，**不含运行时状态和已配置参数**。前端展示时需结合 `GET /api/providers` 判断各渠道是否已配置（例如 `telegram` 是否有 `bot_token`）。

---

### 7.2 获取白名单用户列表

```
GET /api/channels/allowed-users
```

**认证**：需要 Bearer Token

**Response 200** — `AllowedUser[]`

```json
[
  {
    "id": 1,
    "channel": "telegram",
    "user_id": "123456789",
    "alias": "张三",
    "created_at": "2026-03-01T10:00:00"
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `integer` | 主键 |
| `channel` | `string` | 渠道名称 |
| `user_id` | `string` | 渠道内的用户 ID |
| `alias` | `string \| null` | 备注名 |
| `created_at` | `string` | 添加时间 |

---

### 7.3 添加白名单用户

```
POST /api/channels/allowed-users?channel={channel}&user_id={user_id}&alias={alias}
```

**认证**：需要 Bearer Token

> **注意**：当前接口使用 **Query Parameters** 而非 JSON Body，前端调用时需用 `params` 传参。

**Query Params**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `channel` | `string` | ✓ | 渠道名称 |
| `user_id` | `string` | ✓ | 用户 ID |
| `alias` | `string` | ✗ | 备注名 |

**前端调用示例**

```typescript
await api.post('/channels/allowed-users', null, {
  params: { channel: 'telegram', user_id: '123456789', alias: '张三' }
})
```

**Response 200**

```json
{ "added": true }
```

---

### 7.4 删除白名单用户

```
DELETE /api/channels/allowed-users/{channel}/{user_id}
```

**认证**：需要 Bearer Token

**Path Params**

| 参数 | 类型 | 说明 |
|------|------|------|
| `channel` | `string` | 渠道名称 |
| `user_id` | `string` | 用户 ID |

**Response 200**

```json
{ "deleted": true }
```

---

## 8. 会话与消息

### 8.1 获取会话列表

```
GET /api/sessions
```

**认证**：需要 Bearer Token

**Response 200** — `Session[]`（最近 100 条，按最新活跃排序）

```json
[
  {
    "id": 1,
    "session_key": "telegram:123456789",
    "created_at": "2026-03-01T08:00:00",
    "updated_at": "2026-03-06T09:30:00",
    "last_consolidated": 48
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `integer` | 主键 |
| `session_key` | `string` | `"渠道:chat_id"` 格式，如 `"telegram:123456789"` |
| `created_at` | `string` | 会话首次建立时间 |
| `updated_at` | `string` | 最后活跃时间 |
| `last_consolidated` | `integer` | 最后一次记忆整合时的消息 ID |

**前端解析 `session_key`**：

```typescript
const [channel, chatId] = session.session_key.split(':')
```

---

### 8.2 获取会话消息列表

```
GET /api/sessions/{session_key}/messages
```

**认证**：需要 Bearer Token

**Path Params**

| 参数 | 类型 | 说明 |
|------|------|------|
| `session_key` | `string` | 完整的 session_key，如 `telegram:123456789`（URL 编码：`telegram%3A123456789`） |

**Response 200** — `Message[]`（按时间正序）

```json
[
  {
    "id": 1,
    "role": "user",
    "content": "你好，帮我总结一下今天的新闻",
    "tool_calls": null,
    "tool_call_id": null,
    "created_at": "2026-03-06T09:30:00"
  },
  {
    "id": 2,
    "role": "assistant",
    "content": "好的，以下是今天的主要新闻摘要：\n\n1. ...",
    "tool_calls": null,
    "tool_call_id": null,
    "created_at": "2026-03-06T09:30:05"
  },
  {
    "id": 3,
    "role": "tool",
    "content": "{\"result\": \"search results...\"}",
    "tool_calls": null,
    "tool_call_id": "call_abc123",
    "created_at": "2026-03-06T09:30:03"
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `integer` | 消息 ID（正序排列） |
| `role` | `"system" \| "user" \| "assistant" \| "tool"` | 消息角色 |
| `content` | `string \| null` | 消息内容（Markdown） |
| `tool_calls` | `string \| null` | JSON 字符串，LLM 发起工具调用时存在 |
| `tool_call_id` | `string \| null` | 工具调用回复的 ID |
| `created_at` | `string` | 消息时间 |

**前端渲染说明**：
- `role === "user"` → 右侧气泡
- `role === "assistant"` → 左侧气泡，渲染 Markdown
- `role === "tool"` → 折叠卡片（展开后显示 JSON）
- `role === "system"` → 不展示（系统消息）

**Response 200**（session 不存在时返回空数组）

```json
[]
```

---

## 9. 定时任务

### 9.1 获取定时任务列表

```
GET /api/cron
```

**认证**：需要 Bearer Token

**Response 200** — `CronJob[]`（按创建时间倒序）

```json
[
  {
    "id": 1,
    "name": "每日摘要",
    "schedule": "{\"type\":\"cron\",\"expr\":\"0 9 * * *\"}",
    "payload": "{\"message\":\"执行每日摘要\",\"channel\":\"telegram\",\"chat_id\":\"123456789\"}",
    "enabled": 1,
    "next_run_at": "2026-03-07T09:00:00",
    "last_run_at": "2026-03-06T09:00:01",
    "last_status": "success",
    "last_error": null,
    "created_at": "2026-03-01T10:00:00"
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `integer` | 主键 |
| `name` | `string` | 任务名称 |
| `schedule` | `string` | JSON 字符串，调度配置（前端需 `JSON.parse`） |
| `payload` | `string` | JSON 字符串，执行载荷 |
| `enabled` | `0 \| 1` | 是否启用 |
| `next_run_at` | `string \| null` | 下次执行时间 |
| `last_run_at` | `string \| null` | 上次执行时间 |
| `last_status` | `string \| null` | 上次执行状态：`"success"` / `"failed"` |
| `last_error` | `string \| null` | 上次失败错误信息 |
| `created_at` | `string` | 创建时间 |

**`schedule` 字段结构**（解析后）

```json
{ "type": "cron", "expr": "0 9 * * *" }
// 或
{ "type": "every", "seconds": 3600 }
// 或
{ "type": "at", "time": "09:00" }
```

---

### 9.2 删除定时任务

```
DELETE /api/cron/{job_id}
```

**认证**：需要 Bearer Token

**Path Params**

| 参数 | 类型 | 说明 |
|------|------|------|
| `job_id` | `integer` | 任务 ID |

**Response 200**

```json
{ "deleted": true }
```

---

## 10. 审计日志

### 10.1 查询日志

```
GET /api/logs
```

**认证**：需要 Bearer Token

**Query Params**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `level` | `string` | ✗ | 全部 | 过滤级别：`"info"` / `"warn"` / `"error"` |
| `module` | `string` | ✗ | 全部 | 过滤模块：`"agent"` / `"channel"` / `"cron"` / `"auth"` / `"workflow"` |
| `limit` | `integer` | ✗ | `100` | 返回条数上限，最大 `1000` |

**Response 200** — `AuditLog[]`（按时间倒序）

```json
[
  {
    "id": 1024,
    "timestamp": "2026-03-06T09:30:05",
    "level": "info",
    "module": "agent",
    "event": "message_received",
    "detail": "{\"channel\":\"telegram\",\"chat_id\":\"123456789\",\"length\":42}",
    "session_key": "telegram:123456789"
  },
  {
    "id": 1023,
    "timestamp": "2026-03-06T09:29:01",
    "level": "error",
    "module": "channel",
    "event": "send_failed",
    "detail": "{\"error\":\"Connection timeout\"}",
    "session_key": null
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `integer` | 主键 |
| `timestamp` | `string` | 日志时间 |
| `level` | `"info" \| "warn" \| "error"` | 日志级别 |
| `module` | `string` | 模块来源 |
| `event` | `string` | 事件名称 |
| `detail` | `string \| null` | JSON 字符串，事件详情 |
| `session_key` | `string \| null` | 关联的会话 key |

---

## 11. 系统设置

### 11.1 获取系统信息

```
GET /api/settings
```

**认证**：需要 Bearer Token

**Response 200**

```json
{
  "version": "0.1.0",
  "status": "running"
}
```

> **当前限制**：仅返回版本号和运行状态，不含 UI 主题、Agent 配置等设置项。如需扩展，后续增加字段。

---

### 11.2 修改管理员密码

```
PUT /api/settings/password
```

**认证**：需要 Bearer Token

**Request Body**

```json
{
  "new_password": "newSecurePassword123"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `new_password` | `string` | ✓ | 新密码，最少 8 位 |

**Response 200**

```json
{ "updated": true }
```

**Response 200**（密码不满足长度要求时，注意：后端返回 200 而非 400）

```json
{ "error": "Password must be at least 8 characters" }
```

> **前端注意**：需检查响应体是否含 `error` 字段，不能仅凭 HTTP 200 判断成功。

---

## 12. Webhook 接入

### 12.1 Telegram Webhook

```
POST /webhook/telegram
```

**认证**：Telegram 签名校验（Header 验证）

**Request Headers**

| Header | 说明 |
|--------|------|
| `X-Telegram-Bot-Api-Secret-Token` | 配置时设置的 Secret Token；若未配置则不校验 |

**Request Body**：Telegram Update 对象（由 Telegram 服务器发送，前端无需关注）

**Response 200**

```json
{ "ok": true }
```

**Response 403**（Secret Token 校验失败）

```json
{ "detail": "Invalid secret token" }
```

---

## 13. 实时推送（WebSocket）

> **当前状态**：WebSocket 端点在 UIUX.md 中已规划，**后端代码尚未实现**，属于待开发功能。以下为前后端协商的接口规范，供后续实现参考。

### 13.1 实时日志流

```
WS /ws/logs
```

**认证**：Query Param 携带 token（WebSocket 不支持自定义 Header）

```
ws://localhost:18790/ws/logs?token=<access_token>
```

**服务端推送格式**（Text Frame，JSON）

```json
{
  "id": 1025,
  "timestamp": "2026-03-06T09:31:00",
  "level": "info",
  "module": "agent",
  "event": "message_processed",
  "detail": null,
  "session_key": "telegram:123456789"
}
```

**前端连接示例**

```typescript
const ws = new WebSocket(`/ws/logs?token=${localStorage.getItem('token')}`)
ws.onmessage = (e) => {
  const log = JSON.parse(e.data)
  logs.value.unshift(log)
  if (logs.value.length > 500) logs.value.pop()
}
ws.onclose = () => {
  // 自动重连逻辑
  setTimeout(connectWs, 3000)
}
```

---

### 13.2 系统状态推送

```
WS /ws/status
```

**认证**：同 `/ws/logs`，Query Param 携带 token

**服务端推送格式**

```json
{
  "type": "agent_status",
  "data": {
    "online": true,
    "active_sessions": 3,
    "processing": ["telegram:123456789"]
  }
}
```

```json
{
  "type": "channel_status",
  "data": {
    "channel": "telegram",
    "status": "online",
    "last_message_at": "2026-03-06T09:31:00"
  }
}
```

**`type` 枚举**

| `type` | 说明 |
|--------|------|
| `agent_status` | Agent 在线状态变化 |
| `channel_status` | 渠道连接状态变化 |
| `workflow_run` | 工作流执行状态更新 |

---

## 14. 前端 axios 集成参考

### 14.1 axios 实例配置

```typescript
// src/api/client.ts
import axios from 'axios'
import { useAuthStore } from '../stores/auth'
import router from '../router'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求拦截器：自动注入 token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：401 自动登出
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      router.push('/login')
    }
    return Promise.reject(err)
  }
)

export default api
```

### 14.2 类型定义参考

```typescript
// src/types/api.ts

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface DashboardStats {
  total_sessions: number
  total_messages: number
  total_workflows: number
  active_workflows: number
  cron_jobs: number
  recent_errors: number
}

export interface Workflow {
  id: number
  name: string
  description: string
  template: string | null
  enabled: 0 | 1
  trigger_rules: string | null  // JSON 字符串，使用时需 JSON.parse
  created_at: string
  updated_at: string
}

export interface WorkflowDetail extends Omit<Workflow, 'trigger_rules'> {
  definition: WorkflowDefinition
  trigger_rules: TriggerRules | null  // 已解析为对象
}

export interface WorkflowDefinition {
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
}

export interface WorkflowNode {
  id: string
  type: 'trigger' | 'llm_call' | 'tool' | 'condition' | 'response' | 'delay' | 'subagent'
  data: Record<string, unknown>
}

export interface WorkflowEdge {
  source: string
  target: string
}

export interface TriggerRules {
  channel?: string
  keywords?: string[]
  prefix?: string
}

export interface WorkflowRun {
  id: number
  workflow_id: number
  trigger_data: string | null
  status: 'running' | 'completed' | 'failed'
  variables: string | null
  error: string | null
  started_at: string
  finished_at: string | null
}

export interface WorkflowTemplate {
  id: string
  name: string
  description: string
  params: TemplateParam[]
}

export interface TemplateParam {
  key: string
  label: string
  type: 'text' | 'textarea' | 'select'
  default: string
}

export interface ProviderItem {
  provider: string
  key_name: string
}

export interface ChannelItem {
  name: string
  type: string
}

export interface AllowedUser {
  id: number
  channel: string
  user_id: string
  alias: string | null
  created_at: string
}

export interface Session {
  id: number
  session_key: string
  created_at: string
  updated_at: string
  last_consolidated: number
}

export interface Message {
  id: number
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string | null
  tool_calls: string | null
  tool_call_id: string | null
  created_at: string
}

export interface CronJob {
  id: number
  name: string
  schedule: string   // JSON 字符串
  payload: string    // JSON 字符串
  enabled: 0 | 1
  next_run_at: string | null
  last_run_at: string | null
  last_status: string | null
  last_error: string | null
  created_at: string
}

export interface AuditLog {
  id: number
  timestamp: string
  level: 'info' | 'warn' | 'error'
  module: string
  event: string
  detail: string | null
  session_key: string | null
}
```

---

## 15. 接口现状与缺口清单

以下为对比 UIUX.md 的前端需求与当前后端实现，梳理出的**缺口**，优先级供后续开发参考。

### 15.1 现有接口的已知问题

| 接口 | 问题 | 影响 | 建议 |
|------|------|------|------|
| `GET /api/channels` | 返回静态列表，不含运行状态、已配置 Token 和白名单汇总 | 渠道管理页无法展示配置状态和呼吸灯 | 扩展返回字段：`enabled`, `configured`, `status`, `last_activity_at` |
| `POST /api/channels/allowed-users` | 使用 Query Params 而非 JSON Body | 与 axios 默认使用习惯不一致 | 改为接受 JSON Body |
| `POST /api/providers/{provider}/test` | 仅验证凭证存在性，未实际调用 LLM API | 测试按钮不能反映真实连通性 | 发起真实 LLM 调用并返回延迟 |
| `GET /api/settings` | 仅返回 `{version, status}`，无法管理 UI 偏好和 Agent 配置 | 设置页功能残缺 | 扩展字段，或拆分为多个子端点 |
| `PUT /api/settings/password` | 密码长度校验失败时返回 HTTP 200 + `{error: ...}` | 前端需特殊处理，违反 REST 约定 | 改为返回 HTTP 400 |
| `GET /api/workflows`（列表） | `trigger_rules` 返回 JSON 字符串，需前端 `JSON.parse` | 使用不便，易出错 | 后端统一序列化为对象返回 |

### 15.2 UIUX 需要但后端尚未实现的接口

**P0 — 阻塞 UI 核心功能**

| 端点 | 说明 |
|------|------|
| `GET /api/channels/{channel}/config` | 获取单个渠道的配置详情（Token 脱敏、模式、白名单数量等） |
| `PUT /api/channels/{channel}/config` | 更新渠道配置（Token、模式、Webhook URL 等），热重载生效 |
| `POST /api/channels/{channel}/test` | 发送握手测试请求（如 Telegram `getMe`），返回响应日志 |
| `WS /ws/logs` | 实时日志流 WebSocket（日志监控页必需） |
| `WS /ws/status` | Agent/渠道状态实时推送（仪表盘/渠道页呼吸灯必需） |

**P1 — 影响核心功能体验**

| 端点 | 说明 |
|------|------|
| `POST /api/cron` | 通过 Web UI 创建定时任务 |
| `PUT /api/cron/{job_id}` | 更新定时任务（修改计划/启停） |
| `POST /api/cron/{job_id}/run` | 手动触发定时任务执行 |
| `GET /api/dashboard/trend` | 近 7 天消息量/Token 消耗趋势数据（仪表盘 Sparklines） |
| `GET /api/sessions/{session_key}` | 单个会话元数据（前端路由 `/sessions/:key` 需要） |
| `PUT /api/providers/{provider}` | 更新提供者配置（如修改轮询策略、添加新 Key） |

**P2 — 增强功能**

| 端点 | 说明 |
|------|------|
| `GET /api/settings/agent` | 获取 SOUL.md / USER.md / MEMORY.md 内容 |
| `PUT /api/settings/agent` | 更新 Agent 配置文件内容 |
| `DELETE /api/settings/memory` | 清空 MEMORY.md（危险操作，需二次确认） |
| `GET /api/logs?search=keyword` | 日志关键词搜索（新增 `search` 查询参数） |
| `GET /api/logs?from=&to=` | 日志时间范围过滤 |
| `GET /api/workflows/{id}/runs/{run_id}` | 获取单次执行详情（含每节点执行日志） |
