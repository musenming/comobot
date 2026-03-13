# comobot 升级方案：Session 渠道视图 & Know-how 经验学习系统

本方案旨在升级 **comobot** 的 Web 交互体验与知识沉淀能力：在 Web UI 中提供以渠道维度组织的 Session 视图与实时多端同步，并新增 Know-how 经验学习功能，让 Agent 能从历史成功对话中提炼可复用的程序性知识。

---

## 0. 现状分析与设计原则

### 0.1 现有架构盘点

在设计前，先厘清现有系统已具备的能力，避免重复建设：

| 系统 | 现状 | 与本方案关系 |
|:---|:---|:---|
| **Session 管理** | `SQLiteSessionManager`，session_key 已为 `channel:chat_id` 格式（如 `telegram:12345`） | 存储层无需重写，仅需 Web UI 侧增加渠道维度的展示与同步 |
| **Memory 系统** | 两层设计：MEMORY.md（长期事实）+ 每日日志（YYYY-MM-DD.md），MemorySearchEngine 提供 BM25 + 向量混合搜索 | Know-how 应复用此检索引擎，而非另建一套 |
| **Skills 系统** | `workspace/skills/*/SKILL.md`，含 frontmatter 元数据 + Markdown 指令，SkillsLoader 自动发现与加载 | Know-how 不应自动生成 Skill，两者定位不同（见 0.2） |
| **MessageBus** | 异步 `asyncio.Queue`，InboundMessage/OutboundMessage 解耦渠道与 Agent | 多端同步利用现有 Bus + WebSocket 推送即可 |
| **ContextBuilder** | 按序拼接：Identity → Bootstrap → Memory → Skills → Summary | Know-how 注入点应在 Memory 与 Skills 之间 |

### 0.2 核心概念区分

```
┌──────────────────────────────────────────────────────────────┐
│                      Agent 的三类知识                         │
├──────────────┬───────────────────┬───────────────────────────┤
│   Memory     │    Know-how       │    Skill                  │
│  （记忆）     │   （经验）         │   （技能）                 │
├──────────────┼───────────────────┼───────────────────────────┤
│ 陈述性知识    │ 程序性知识         │ 指令性知识                 │
│ "是什么"     │ "怎么做过"         │ "应该怎么做"               │
│              │                   │                           │
│ 用户偏好、    │ 成功解决某类问题    │ 通用能力模板               │
│ 项目事实、    │ 的完整上下文流程    │ （天气查询、GitHub 操作）   │
│ 决策记录      │ （问题→步骤→结果） │                           │
├──────────────┼───────────────────┼───────────────────────────┤
│ MEMORY.md    │ workspace/knowhow/│ workspace/skills/          │
│ + 每日日志    │ *.md + SQLite 索引 │ */SKILL.md                │
├──────────────┼───────────────────┼───────────────────────────┤
│ 始终加载上下文 │ 按相似度检索注入   │ 按需加载                   │
└──────────────┴───────────────────┴───────────────────────────┘
```

### 0.3 设计原则

1. **复用优先** — 扩展现有 MemorySearchEngine 索引 Know-how 文件，不另建检索系统
2. **文件即真相** — Know-how 内容以 Markdown 文件为主体（与 Skills/Memory 风格一致），SQLite 仅存元数据索引
3. **最小侵入** — Session 存储层不改动，仅在 API/WebSocket/UI 层增加渠道聚合视图
4. **渐进增强** — Know-how 先实现手动提取 + 被动检索，验证价值后再加自动化

---

## 1. Session 渠道视图与多端同步

### 1.1 现状与目标

**现状**：Session 按 `channel:chat_id` 扁平存储，Web UI 的 SessionsView 以列表形式展示，缺乏渠道维度的组织。外部渠道（Telegram/飞书等）的对话不会实时推送到 Web 端。

**目标**：Web UI 在chat视窗中以渠道树形结构展示 Session，外部渠道消息实时同步到 Web 端对应视窗，SessionsView更改为KnowhowView详细设计见*1.4 Web UI 侧边栏重构*

### 1.2 API 层增强

在现有 `/api/sessions` 基础上新增聚合接口：

```
GET /api/sessions/by-channel
```

返回结构：

```json
{
  "channels": [
    {
      "channel_type": "telegram",
      "display_name": "Telegram Bot",
      "sessions": [
        {
          "session_key": "telegram:12345",
          "chat_id": "12345",
          "chat_label": "张三",          // 来自 allowed_users.alias 或 chat_id
          "last_message_at": "2026-03-12T10:30:00",
          "unread_count": 3,
          "message_count": 128
        }
      ]
    },
    {
      "channel_type": "web",
      "display_name": "Web Chat",
      "sessions": [...]
    }
  ]
}
```

**实现方式**：SQL 聚合查询，按 `session_key` 的冒号前缀分组，左连 `allowed_users` 取 alias。

### 1.3 实时同步机制

```
外部渠道消息到达
  → MessageBus.inbound_queue
  → AgentLoop._process_message()
  → 消息写入 SQLite (messages 表)
  → AgentLoop._save_turn() 完成后
  → 发布 WebSocket 事件 → WS /ws/sessions
  → Web UI 收到推送，更新对应 Channel/Session 视窗
```

**WebSocket 事件格式**：

```json
{
  "event": "new_message",
  "session_key": "telegram:12345",
  "message": {
    "role": "user",
    "content": "...",
    "created_at": "2026-03-12T10:30:00"
  }
}
```

**关键设计决策**：

| 决策点 | 方案 | 理由 |
|:---|:---|:---|
| 推送时机 | `_save_turn()` 之后，**并且要及时推送到前端web UI进行前端展示** | 确保消息已持久化，避免幽灵消息；**确保消息能够及时在前端呈现** |
| 推送粒度 | 单条消息 | 避免推送整个 session 历史，Web 端增量追加 |
| Web → 外部渠道 | 不支持（一期） | 在 Web 查看外部渠道消息为只读；双向需引入回复路由，复杂度高，二期考虑 |


### 1.4 Web UI 侧边栏重构

```
┌──────────────────┬─────────────────────────────────——————————————————————————————————┐
│ ComoBot          │     （chat view）                                                  ｜ 
│                  │                                          对话视窗                   ｜            
│    Chat          │                                 generate Knowhow button           ｜
│    Creflow       │                        |                                          ｜
│    Knowhow       │   session 1             |                       帮我查一下天气：Use｜  │
│    Skills        │    - web UI             |   asistant：今天晴...                    ｜│
│    Cron Jobs     │    - abstract           |                                          ｜
│    BrainCopy     │    - timestamp          |                                          ｜
│    ----------    │    - 群聊            |                                          ｜
│                  │    session 2           |                                          ｜
│    Dashboard     │    - telegram          |                                          ｜
│    Channels      │    - abstract          |                                          ｜
│    Providers     │    - timestamp         ｜                                           ｜
│    logs          │    - 单对话             ｜                                          ｜
│    Settings      │                                                                    ｜
│                  │                                                                    ｜
│                  │                                   ┌──────────────────————————————┬ ｜                    
│                  │                                   └─——————————————————————————————┘｜                    
│                  │                                                          
└──────────────────┴──────────────────────────────————————————————————————————————————───┘

┌──────────────────┬─────────────────────────────────————————————————————————————————————————┐
│ ComoBot          │     （Knowhow view）                                                   ｜ 
│                  │                                          对话视窗                       ｜            
│    Chat          │    search 栏                                                           ｜
│    Creflow       │    --------------------                                                ｜
│    Knowhow       │   Knowhow 1                |                       帮我查一下天气：User  │
│    Skills        │    - function abstract     |   asistant：今天晴...                      │
│    Cron Jobs     │    - update time           |                                          ｜
│    BrainCopy     │   ——————————————————————   |                                          ｜
│    ----------    │   Knowhow 1                |                                          ｜
│                  │    - function abstract     |                                          ｜
│    Dashboard     │    - update time           |                                          ｜
│    Channels      │    ——————————————————      |                                          ｜
│    Providers     │                                                                       ｜
│    logs          │                                                                       ｜
│    Settings      │                                                                       ｜
│                  │                                                                       ｜
│                  │                                   ┌──────────────────————————————┬ ｜                    
│                  │                                   └─——————————————————————————————┘｜                    
│                  │                                                          
└──────────────────┴──────────────────────────────————————————————————————————————————───┘




```

**组件拆分**：

| 组件 | 职责 |
|:---|:---|
| `ChannelTree.vue` | 渠道树形列表，折叠/展开，未读角标 |
| `KnowhowSidebar.vue` | Know-how 列表，搜索/筛选，点击预览 |
| `SessionPanel.vue` | 对话消息流，支持实时 WebSocket 追加 |

---

## 2. Know-how 经验学习系统

### 2.1 功能概述

Know-how 允许用户从历史对话中手动选取"成功经验片段"，系统通过 LLM 自动提炼为结构化的程序性知识，存入 `workspace/knowhow/` 目录。当用户发出新请求时，Agent 在 MemorySearchEngine 中检索相似 Know-how，将匹配的经验注入上下文，从而"记住"过去如何解决类似问题。

### 2.2 交互流程

```
用户在对话视窗中操作：

1. 点击工具栏 [提取经验] 按钮
   → 对话气泡进入可勾选状态

2. 勾选相关消息（至少 2 条，含 user + assistant）
   → 底部浮出操作栏，显示已选 N 条

3. 点击 [保存为 Know-how]
   → 前端将选中消息发送至后端

4. 后端调用 LLM 生成摘要：
   ┌─────────────────────────────────────────┐
   │  System: 你是知识提取助手。              │
   │  请根据以下对话片段生成结构化摘要：       │
   │  - title: 简短标题（≤20字）              │
   │  - goal: 用户想达成什么                   │
   │  - steps: 关键步骤（有序列表）            │
   │  - tools_used: 使用了哪些工具             │
   │  - outcome: 最终结果                      │
   │  - tags: 分类标签（2-5个）                │
   │                                          │
   │  对话片段：                               │
   │  {selected_messages}                      │
   └─────────────────────────────────────────┘

5. 返回预览 → 用户可编辑标题/标签 → 确认保存

6. 写入 workspace/knowhow/{id}_{slug}.md
   + SQLite knowhow 表插入元数据
   + MemorySearchEngine 增量索引该文件
```

### 2.3 Know-how 文件格式

存储位置：`workspace/knowhow/`，每条 Know-how 一个 Markdown 文件。

```markdown
---
id: kh_20260312_001
title: 用 Docker Compose 部署 Nginx 反代
tags: ["部署", "Docker", "Nginx"]
goal: 在服务器上部署 Nginx 作为反向代理
source_session: telegram:12345
source_messages: [1023, 1024, 1025, 1026, 1027]
created_at: 2026-03-12T10:30:00
updated_at: 2026-03-12T10:30:00
status: active
---

# 用 Docker Compose 部署 Nginx 反代

## 目标
在 Ubuntu 服务器上通过 Docker Compose 部署 Nginx，配置反向代理到后端服务。

## 关键步骤
1. 创建 `docker-compose.yml`，定义 nginx 服务并映射 80/443 端口
2. 编写 `nginx.conf`，配置 `proxy_pass` 指向后端 `http://app:8080`
3. 挂载 SSL 证书目录到容器内
4. `docker-compose up -d` 启动，`curl -I localhost` 验证

## 使用工具
- `exec`: 执行 docker-compose 命令
- `write_file`: 写入配置文件
- `web_fetch`: 验证部署结果

## 结果
Nginx 成功启动，反向代理正常转发请求，SSL 证书生效。

## 原始对话片段
> user: 帮我在服务器上部署一个 nginx 反代到 8080 端口
> assistant: 好的，我来创建 docker-compose.yml...
> ...（完整片段快照）
```

### 2.4 数据模型

#### SQLite `knowhow` 表（元数据索引）

```sql
CREATE TABLE knowhow (
    id              TEXT PRIMARY KEY,          -- kh_YYYYMMDD_NNN
    title           TEXT NOT NULL,
    tags            TEXT NOT NULL DEFAULT '[]', -- JSON array
    goal            TEXT,                       -- 一句话目标描述
    file_path       TEXT NOT NULL UNIQUE,       -- workspace/knowhow/xxx.md
    source_session  TEXT,                       -- 来源 session_key
    source_messages TEXT,                       -- JSON: [msg_id, ...]
    status          TEXT DEFAULT 'active',      -- active / archived
    usage_count     INTEGER DEFAULT 0,          -- 被检索命中次数
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_knowhow_status ON knowhow(status);
CREATE INDEX idx_knowhow_tags ON knowhow(tags);
```

**设计决策**：

| 决策 | 方案 | 理由 |
|:---|:---|:---|
| 内容存储 | Markdown 文件为主体，SQLite 存索引 | 与 Memory/Skills 一致；文件可被 MemorySearchEngine 自动发现和索引 |
| 不自动生成 Skill | Know-how ≠ Skill | Skill 是通用指令模板，Know-how 是特定经验记录；混淆会污染 Skill 体系 |
| 保留原始对话快照 | 嵌入 Markdown 底部 | 提供溯源能力，Agent 可参考完整上下文而非仅摘要 |
| usage_count | 命中时递增 | 为后续优化提供数据——高频 Know-how 可考虑升级为 Skill |

### 2.5 检索注入机制（Pre-Retrieval）

**复用 MemorySearchEngine**，扩展其文件发现范围至 `workspace/knowhow/`：

```python
# memory_search.py._discover_files() 增加：
def _discover_files(self) -> list[tuple[str, Path]]:
    files = [...]  # 现有 memory 文件发现逻辑

    # Know-how 文件
    knowhow_dir = self.workspace / "knowhow"
    if knowhow_dir.exists():
        for p in sorted(knowhow_dir.glob("*.md")):
            if not p.name.startswith("."):
                files.append((f"knowhow/{p.name}", p))

    return files
```

**注入流程**（在 `ContextBuilder.build_system_prompt` 中）：

```
现有流程：
  Identity → Bootstrap → Memory → Skills

升级后：
  Identity → Bootstrap → Memory → [Know-how 检索结果] → Skills
```

具体实现：

```python
# context.py 变更
class ContextBuilder:
    def __init__(self, workspace: Path, memory_engine: MemorySearchEngine = None):
        ...
        self._memory_engine = memory_engine

    def build_system_prompt(self, skill_names=None, user_message: str = None):
        parts = [...]  # 现有逻辑

        # Know-how 检索注入
        if user_message and self._memory_engine:
            knowhow_chunks = self._memory_engine.search(
                user_message,
                max_results=3,
                file_filter="knowhow/"   # 仅搜索 Know-how 文件
            )
            if knowhow_chunks:
                knowhow_text = self._format_knowhow(knowhow_chunks)
                parts.append(f"# Relevant Experience (Know-how)\n\n{knowhow_text}")

        return "\n\n---\n\n".join(parts)
```

**MemorySearchEngine 扩展**：

```python
# 新增 file_filter 参数
def search(self, query: str, max_results: int = 5, file_filter: str = None):
    # 在现有搜索逻辑中增加 WHERE file_path LIKE 'knowhow/%' 条件
    ...
```

**检索效果控制**：

| 参数 | 默认值 | 说明 |
|:---|:---|:---|
| `knowhow_max_results` | 3 | 最多注入 3 条 Know-how |
| `knowhow_score_threshold` | 0.3 | 低于此分数的不注入（避免噪音） |
| `knowhow_max_tokens` | 2000 | Know-how 注入总 token 上限 |

### 2.6 Know-how API

| 端点 | 方法 | 说明 |
|:---|:---|:---|
| `POST /api/knowhow/extract` | JWT | 提交选中消息，LLM 生成摘要预览 |
| `POST /api/knowhow` | JWT | 确认保存 Know-how |
| `GET /api/knowhow` | JWT | 列表查询（支持 tags/status 筛选） |
| `GET /api/knowhow/{id}` | JWT | 获取单条详情 |
| `PUT /api/knowhow/{id}` | JWT | 编辑标题/标签/状态 |
| `DELETE /api/knowhow/{id}` | JWT | 删除（同时删除 Markdown 文件并重建索引） |

**`POST /api/knowhow/extract` 请求体**：

```json
{
  "session_key": "telegram:12345",
  "message_ids": [1023, 1024, 1025, 1026, 1027]
}
```

**响应**（LLM 生成的预览）：

```json
{
  "preview": {
    "title": "用 Docker Compose 部署 Nginx 反代",
    "goal": "在服务器上部署 Nginx 作为反向代理",
    "steps": ["创建 docker-compose.yml...", "编写 nginx.conf...", ...],
    "tools_used": ["exec", "write_file"],
    "tags": ["部署", "Docker", "Nginx"],
    "outcome": "Nginx 成功启动，反向代理正常转发"
  },
  "raw_messages": [...]
}
```

### 2.7 Know-how Agent 工具（可选增强）

除 Web UI 手动提取外，增加 Agent 工具让 Agent 自身也能操作 Know-how：

```python
class KnowhowSearchTool(Tool):
    name = "knowhow_search"
    description = "搜索过往成功经验（Know-how）"
    # 输入：query 字符串
    # 输出：匹配的 Know-how 列表

class KnowhowSaveTool(Tool):
    name = "knowhow_save"
    description = "将当前对话经验保存为 Know-how"
    # Agent 在成功完成复杂任务后，可主动调用此工具
```

---

## 3. 实施路线图

### Phase 1：Session 渠道视图（后端 + 前端）

| # | 任务 | 关键产出 | 预估复杂度 |
|:---|:---|:---|:---|
| 1.1 | `GET /api/sessions/by-channel` 聚合接口 | SQL 按 session_key 前缀分组 + alias 关联 | 低 |
| 1.2 | `WS /ws/sessions` WebSocket 推送 | AgentLoop._save_turn 后发布事件 | 中 |
| 1.3 | `ChannelTree.vue` 渠道树组件 | 折叠列表 + 未读角标 + 实时更新 | 中 |
| 1.4 | `SessionPanel.vue` 改造 | 支持 WebSocket 增量追加消息 | 低 |
| 1.5 | 侧边栏布局重构 | 上半 Session 栏 + 下半 Know-how 栏 | 低 |

### Phase 2：Know-how 后端核心

| # | 任务 | 关键产出 | 预估复杂度 |
|:---|:---|:---|:---|
| 2.1 | SQLite `knowhow` 表迁移脚本 | 新增表 + 索引，纳入 schema_version 管理 | 低 |
| 2.2 | Know-how 文件读写模块 | `KnowhowStore`: 创建/读取/更新/删除 Markdown 文件 | 中 |
| 2.3 | LLM 摘要提取 Prompt | 提取接口 + 结构化输出解析 | 中 |
| 2.4 | Know-how REST API | 6 个端点（extract/CRUD） | 中 |
| 2.5 | MemorySearchEngine 扩展 | `_discover_files` 增加 knowhow/ + `file_filter` 参数 | 低 |

### Phase 3：Know-how 检索注入 + 前端

| # | 任务 | 关键产出 | 预估复杂度 |
|:---|:---|:---|:---|
| 3.1 | ContextBuilder Know-how 注入 | `build_system_prompt` 增加 Know-how 检索段 | 中 |
| 3.2 | 对话框多选模式 | `MessageSelector.vue`: 勾选 + 浮动操作栏 | 中 |
| 3.3 | Know-how 预览与保存面板 | `KnowhowPreview.vue`: 展示 LLM 摘要 + 编辑 + 确认 | 中 |
| 3.4 | `KnowhowSidebar.vue` 侧边栏 | 列表 + 搜索 + 标签筛选 + 点击预览 | 中 |
| 3.5 | `KnowhowView.vue` 详情页 | 完整 Know-how 查看/编辑/删除 | 低 |

### Phase 4：增强与打磨

| # | 任务 | 关键产出 | 预估复杂度 |
|:---|:---|:---|:---|
| 4.1 | Know-how Agent 工具 | `knowhow_search` + `knowhow_save` 工具注册 | 中 |
| 4.2 | usage_count 统计 | 检索命中时递增，API 返回热门 Know-how | 低 |
| 4.3 | Know-how → Skill 升级建议 | 高频 Know-how 提示用户"是否升级为 Skill" | 低 |
| 4.4 | 端到端测试 | Know-how 提取/检索/注入全链路测试 | 中 |

### 进度总览

| Phase | 任务数 | 预估复杂度 |
|:---|:---|:---|
| Phase 1: Session 渠道视图 | 5 | 中 |
| Phase 2: Know-how 后端 | 5 | 中 |
| Phase 3: Know-how 检索 + 前端 | 5 | 中高 |
| Phase 4: 增强与打磨 | 4 | 低 |
| **总计** | **19** | — |

---

## 4. 与现有系统的集成关系

```
┌─────────────────────────────────────────────────────────────┐
│                        消息到达                              │
└───────────────────────────┬─────────────────────────────────┘
                            │
                ┌───────────▼───────────┐
                │    AgentLoop          │
                │    _process_message   │
                └───┬───────────────┬───┘
                    │               │
           ContextBuilder      _save_turn
           构建 system prompt   保存消息
                    │               │
    ┌───────────────▼──────┐   ┌───▼──────────────┐
    │ 1. Identity          │   │ WebSocket 推送     │
    │ 2. Bootstrap 模板     │   │ → WS /ws/sessions │
    │ 3. Memory (长期+每日) │   │ → Web UI 实时更新  │
    │ 4. ★ Know-how 检索    │   └──────────────────┘
    │ 5. Active Skills     │
    │ 6. Skills Summary    │
    └──────────────────────┘
                    │
        MemorySearchEngine.search()
        同时搜索 memory/ 和 knowhow/
        按分数排序，注入 top-K 结果
```

---

## 5. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|:---|:---|:---|
| Know-how 噪音过多 | Agent 上下文被低质量经验污染 | 设置分数阈值 (0.3)，限制注入条数 (3)，限制总 token (2000) |
| LLM 摘要质量不稳定 | 生成的 Know-how 结构不一致 | 使用结构化输出 (JSON mode) + 人工预览确认环节 |
| Know-how 文件膨胀 | 文件数量增长影响索引速度 | status=archived 的文件不参与检索；定期清理低 usage_count 条目 |
| WebSocket 推送丢失 | Web 端断连期间错过消息 | 前端重连后拉取增量消息（基于 last_message_id） |
| 多端同步一致性 | Web 和外部渠道消息顺序不一致 | 统一以 SQLite messages.id 为排序基准 |

---

## 6. 工程执行规划

本章将 19 个任务细化为可直接执行的代码变更清单，明确文件依赖、复用模式和验证方案。

### 6.1 文件变更总览

#### 后端（11 文件）

| 文件 | 操作 | 关联任务 |
|:---|:---|:---|
| `comobot/db/migrations.py` | 修改 | 2.1 |
| `comobot/api/routes/sessions.py` | 修改 | 1.1 |
| `comobot/api/routes/ws.py` | 修改 | 1.2 |
| `comobot/agent/loop.py` | 修改 | 1.2 |
| `comobot/agent/memory_search.py` | 修改 | 2.5 |
| `comobot/agent/context.py` | 修改 | 3.1 |
| `comobot/knowhow/__init__.py` | 新建 | 2.2 |
| `comobot/knowhow/store.py` | 新建 | 2.2, 2.3 |
| `comobot/knowhow/extractor.py` | 新建 | 2.3 |
| `comobot/api/routes/knowhow.py` | 新建 | 2.4 |
| `comobot/agent/tools/knowhow_tools.py` | 新建 | 4.1 |

#### 前端（9 文件）

| 文件 | 操作 | 关联任务 |
|:---|:---|:---|
| `web/src/views/SessionsView.vue` | 修改 | 1.3, 1.4, 1.5 |
| `web/src/components/ChannelTree.vue` | 新建 | 1.3 |
| `web/src/components/SessionPanel.vue` | 修改 | 1.4 |
| `web/src/composables/useSessionWS.ts` | 新建 | 1.2, 1.4 |
| `web/src/components/MessageSelector.vue` | 新建 | 3.2 |
| `web/src/components/KnowhowPreview.vue` | 新建 | 3.3 |
| `web/src/components/KnowhowSidebar.vue` | 新建 | 3.4 |
| `web/src/views/KnowhowView.vue` | 新建 | 3.5 |
| `web/src/api/client.ts` | 修改 | 2.4, 3.2, 3.3 |

#### 测试（2 文件）

| 文件 | 操作 | 关联任务 |
|:---|:---|:---|
| `tests/test_session_channel.py` | 新建 | 1.1, 1.2 |
| `tests/test_knowhow.py` | 新建 | 2.1–2.5, 4.4 |

---

### 6.2 任务详细变更清单

#### Phase 1：Session 渠道视图

##### 任务 1.1 — `GET /api/sessions/by-channel` 聚合接口

**修改文件**：`comobot/api/routes/sessions.py`

**复用模式**：现有 `list_sessions` 路由的 `Depends(get_db)` + `Depends(get_current_user)` 依赖注入模式。

```python
@router.get("/by-channel")
async def sessions_by_channel(
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """按渠道聚合 Session 列表。"""
    rows = await db.fetchall("""
        SELECT
            s.id,
            s.session_key,
            s.created_at,
            s.updated_at,
            COUNT(m.id) AS message_count,
            au.alias AS chat_label
        FROM sessions s
        LEFT JOIN messages m ON m.session_id = s.id
        LEFT JOIN allowed_users au
            ON au.channel = SUBSTR(s.session_key, 1, INSTR(s.session_key, ':') - 1)
           AND au.user_id = SUBSTR(s.session_key, INSTR(s.session_key, ':') + 1)
        GROUP BY s.id
        ORDER BY s.updated_at DESC
    """)

    channels: dict[str, list] = {}
    for row in rows:
        key = row["session_key"]
        colon = key.index(":")
        ch_type = key[:colon]
        chat_id = key[colon + 1:]
        channels.setdefault(ch_type, []).append({
            "session_key": key,
            "chat_id": chat_id,
            "chat_label": row["chat_label"] or chat_id,
            "last_message_at": row["updated_at"],
            "message_count": row["message_count"],
        })

    display_names = {
        "telegram": "Telegram Bot", "feishu": "飞书",
        "slack": "Slack", "dingtalk": "钉钉",
        "discord": "Discord", "web": "Web Chat",
        "email": "Email", "matrix": "Matrix",
    }
    return {
        "channels": [
            {
                "channel_type": ct,
                "display_name": display_names.get(ct, ct.title()),
                "sessions": sessions,
            }
            for ct, sessions in channels.items()
        ]
    }
```

**注意**：`/by-channel` 路由必须注册在 `/{session_key:path}` 之前，否则会被路径参数吞掉。

---

##### 任务 1.2 — `WS /ws/sessions` 实时推送

**修改文件**：
- `comobot/api/routes/ws.py` — 新增 `session_connections` 池和 `broadcast_session` 方法
- `comobot/agent/loop.py` — `_save_turn` 后发布事件

**ws.py 变更**（复用 `ConnectionManager` 的 `broadcast_*` 模式）：

```python
class ConnectionManager:
    def __init__(self):
        # ... 现有连接池 ...
        self.session_connections: list[WebSocket] = []   # 新增

    async def connect_sessions(self, ws: WebSocket):
        await ws.accept()
        self.session_connections.append(ws)

    def disconnect_sessions(self, ws: WebSocket):
        self.session_connections.remove(ws)

    async def broadcast_session_event(self, event: dict):
        """广播 Session 事件到所有监听客户端。
        复用 broadcast_log / broadcast_status 的失败清理模式。"""
        broken = []
        for ws in self.session_connections:
            try:
                await ws.send_json(event)
            except Exception:
                broken.append(ws)
        for ws in broken:
            self.disconnect_sessions(ws)

# 新增 WebSocket 端点
@router.websocket("/ws/sessions")
async def ws_sessions(ws: WebSocket, _user: str = Depends(ws_auth)):
    await manager.connect_sessions(ws)
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect_sessions(ws)
```

**loop.py 变更**（在 `_save_turn` 完成后触发推送）：

```python
# 在 _save_turn 调用后、sessions.save 之后追加：
from comobot.api.routes.ws import manager as ws_manager

async def _after_save_turn(self, session_key: str, new_messages: list[dict]):
    """将新消息通过 WebSocket 推送到 Web 端。"""
    for msg in new_messages:
        await ws_manager.broadcast_session_event({
            "event": "new_message",
            "session_key": session_key,
            "message": {
                "role": msg.get("role"),
                "content": msg.get("content", ""),
                "created_at": msg.get("timestamp", ""),
            },
        })
```

---

##### 任务 1.3 — `ChannelTree.vue` 渠道树组件

**新建文件**：`web/src/components/ChannelTree.vue`

```vue
<template>
  <div class="channel-tree">
    <div v-for="channel in channels" :key="channel.channel_type" class="channel-group">
      <div class="channel-header" @click="toggle(channel.channel_type)">
        <span class="expand-icon">{{ expanded[channel.channel_type] ? '▼' : '▶' }}</span>
        <span class="channel-name">{{ channel.display_name }}</span>
        <n-badge :value="unreadCount(channel)" :max="99" />
      </div>
      <div v-show="expanded[channel.channel_type]" class="session-list">
        <div
          v-for="s in channel.sessions"
          :key="s.session_key"
          class="session-item"
          :class="{ active: s.session_key === selectedKey }"
          @click="$emit('select', s.session_key)"
        >
          <span class="chat-label">{{ s.chat_label }}</span>
          <span class="msg-count">{{ s.message_count }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NBadge } from 'naive-ui'
import api from '@/api/client'

interface ChannelSession { session_key: string; chat_id: string; chat_label: string; message_count: number }
interface Channel { channel_type: string; display_name: string; sessions: ChannelSession[] }

defineProps<{ selectedKey?: string }>()
defineEmits<{ select: [key: string] }>()

const channels = ref<Channel[]>([])
const expanded = ref<Record<string, boolean>>({})

onMounted(async () => {
  const { data } = await api.get('/sessions/by-channel')
  channels.value = data.channels
  // 默认全部展开
  data.channels.forEach((c: Channel) => { expanded.value[c.channel_type] = true })
})

function toggle(type: string) { expanded.value[type] = !expanded.value[type] }
function unreadCount(ch: Channel) { /* 基于 WebSocket 事件累计，初始版本返回 0 */ return 0 }
</script>
```

---

##### 任务 1.4 — `SessionPanel.vue` WebSocket 增量追加

**修改文件**：`web/src/components/SessionPanel.vue`（或 `SessionsView.vue` 中的对话面板部分）

**新建 Composable**：`web/src/composables/useSessionWS.ts`

```typescript
import { ref, onUnmounted, watch } from 'vue'

interface SessionMessage { role: string; content: string; created_at: string }

export function useSessionWS() {
  const messages = ref<SessionMessage[]>([])
  let ws: WebSocket | null = null

  function connect(token: string) {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${location.host}/ws/sessions?token=${token}`)

    ws.onmessage = (evt) => {
      const data = JSON.parse(evt.data)
      if (data.event === 'new_message') {
        messages.value.push(data.message)
      }
    }
    ws.onclose = () => { setTimeout(() => connect(token), 3000) }  // 自动重连
  }

  onUnmounted(() => ws?.close())
  return { messages, connect }
}
```

**SessionPanel 变更要点**：
- 监听 `useSessionWS().messages`，过滤当前 `session_key`，追加到本地消息列表
- 断连重连后通过 `GET /api/sessions/{key}/messages?offset=lastId` 补齐遗漏消息

---

##### 任务 1.5 — 侧边栏布局重构

**修改文件**：`web/src/views/SessionsView.vue`

将原有 Session 列表替换为上下分栏结构：

```
┌─────────────────────┐
│  ChannelTree.vue     │  ← 上半（flex: 1, overflow: auto）
│  (渠道树 + Session)   │
├─────────────────────┤
│  KnowhowSidebar.vue │  ← 下半（max-height: 40%, overflow: auto）
│  (经验列表)           │
└─────────────────────┘
```

**变更**：引入 `ChannelTree` 替代原有 session 列表，底部增加 `KnowhowSidebar` 占位（Phase 3 填充）。使用 CSS `flex-direction: column` 布局，中间可拖拽分割线（`n-layout-sider` 或自定义 `resize` handle）。

---

#### Phase 2：Know-how 后端核心

##### 任务 2.1 — SQLite `knowhow` 表迁移

**修改文件**：`comobot/db/migrations.py`

**复用模式**：`MIGRATIONS` 列表追加新版本，遵循 `(version, name, sql)` 三元组格式。

```python
MIGRATIONS.append((
    2,
    "add_knowhow_table",
    """
    CREATE TABLE IF NOT EXISTS knowhow (
        id              TEXT PRIMARY KEY,
        title           TEXT NOT NULL,
        tags            TEXT NOT NULL DEFAULT '[]',
        goal            TEXT,
        file_path       TEXT NOT NULL UNIQUE,
        source_session  TEXT,
        source_messages TEXT,
        status          TEXT DEFAULT 'active',
        usage_count     INTEGER DEFAULT 0,
        created_at      TEXT DEFAULT (datetime('now')),
        updated_at      TEXT DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_knowhow_status ON knowhow(status);
    CREATE INDEX IF NOT EXISTS idx_knowhow_tags ON knowhow(tags);
    """,
))
```

**验证**：`run_migrations()` 会自动检测 `schema_version` 表，仅执行未应用的版本。

---

##### 任务 2.2 — `KnowhowStore` 文件读写模块

**新建文件**：
- `comobot/knowhow/__init__.py` — 导出 `KnowhowStore`
- `comobot/knowhow/store.py` — 核心实现

**复用模式**：参照 `comobot/skills/` 的 `SkillsLoader` 文件发现模式 + `comobot/agent/tools/memory_tools.py` 的 `MemoryGetTool` 路径安全检查。

```python
# comobot/knowhow/store.py
from pathlib import Path
import json, re, datetime

class KnowhowStore:
    """管理 workspace/knowhow/ 下的 Markdown 文件与 SQLite 元数据。"""

    def __init__(self, workspace: Path, db):
        self._dir = workspace / "knowhow"
        self._dir.mkdir(exist_ok=True)
        self._db = db

    def _gen_id(self) -> str:
        """生成 kh_YYYYMMDD_NNN 格式 ID。"""
        today = datetime.date.today().strftime("%Y%m%d")
        # 查询当天已有数量，递增
        ...

    def _slugify(self, title: str) -> str:
        """中英文标题转文件名安全 slug。"""
        ...

    async def create(self, preview: dict, raw_messages: list[dict]) -> dict:
        """
        1. 生成 ID + slug
        2. 渲染 Markdown（frontmatter + body + 原始对话快照）
        3. 写入 workspace/knowhow/{id}_{slug}.md
        4. INSERT INTO knowhow 表
        5. 通知 MemorySearchEngine 增量索引
        返回：完整元数据 dict
        """
        ...

    async def get(self, knowhow_id: str) -> dict | None:
        """从 SQLite 查元数据，从文件读 Markdown 正文。"""
        ...

    async def list(self, status: str = "active", tags: list[str] | None = None) -> list[dict]:
        """列表查询，支持 status 和 tags JSON 筛选。"""
        sql = "SELECT * FROM knowhow WHERE status = ?"
        params = [status]
        if tags:
            for tag in tags:
                sql += " AND tags LIKE ?"
                params.append(f'%"{tag}"%')
        sql += " ORDER BY updated_at DESC"
        ...

    async def update(self, knowhow_id: str, **fields) -> dict:
        """更新标题/标签/状态，同步修改 Markdown frontmatter。"""
        ...

    async def delete(self, knowhow_id: str) -> bool:
        """删除 SQLite 记录 + Markdown 文件。"""
        ...

    async def increment_usage(self, knowhow_id: str):
        """usage_count += 1，用于检索命中时调用。"""
        await self._db.execute(
            "UPDATE knowhow SET usage_count = usage_count + 1 WHERE id = ?",
            (knowhow_id,),
        )
```

---

##### 任务 2.3 — LLM 摘要提取

**新建文件**：`comobot/knowhow/extractor.py`

**复用模式**：参照 `comobot/agent/loop.py` 中 LLM 调用模式（`litellm.acompletion`）。

```python
# comobot/knowhow/extractor.py
import json
from litellm import acompletion

EXTRACT_SYSTEM_PROMPT = """你是知识提取助手。请根据以下对话片段生成结构化摘要，以 JSON 格式返回：
{
  "title": "简短标题（≤20字）",
  "goal": "用户想达成什么",
  "steps": ["关键步骤1", "关键步骤2", ...],
  "tools_used": ["工具名1", ...],
  "outcome": "最终结果",
  "tags": ["标签1", "标签2"]
}
"""

async def extract_knowhow(
    messages: list[dict],
    model: str = "gpt-4o-mini",
) -> dict:
    """调用 LLM 从对话片段提取结构化 Know-how 摘要。

    Args:
        messages: 用户选中的原始对话消息列表
        model: LLM 模型名（通过 litellm 路由）

    Returns:
        解析后的 dict，包含 title/goal/steps/tools_used/outcome/tags
    """
    conversation = "\n".join(
        f"{m['role']}: {m['content']}" for m in messages
    )

    resp = await acompletion(
        model=model,
        messages=[
            {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
            {"role": "user", "content": f"对话片段：\n{conversation}"},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    return json.loads(resp.choices[0].message.content)
```

---

##### 任务 2.4 — Know-how REST API

**新建文件**：`comobot/api/routes/knowhow.py`

**复用模式**：完全遵循 `comobot/api/routes/sessions.py` 的路由注册模式。

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/knowhow")

class ExtractRequest(BaseModel):
    session_key: str
    message_ids: list[int]

class SaveRequest(BaseModel):
    preview: dict
    session_key: str
    message_ids: list[int]
    raw_messages: list[dict]

class UpdateRequest(BaseModel):
    title: str | None = None
    tags: list[str] | None = None
    status: str | None = None

@router.post("/extract")
async def extract(req: ExtractRequest, db=Depends(get_db), _=Depends(get_current_user)):
    """提交选中消息 → LLM 生成摘要预览。"""
    # 1. 从 messages 表查询 message_ids 对应内容
    # 2. 调用 extractor.extract_knowhow(messages)
    # 3. 返回 {"preview": {...}, "raw_messages": [...]}

@router.post("")
async def create(req: SaveRequest, db=Depends(get_db), _=Depends(get_current_user)):
    """确认保存 Know-how。"""
    # 调用 KnowhowStore.create(req.preview, req.raw_messages)

@router.get("")
async def list_knowhow(
    status: str = "active",
    tags: str | None = None,
    db=Depends(get_db), _=Depends(get_current_user),
):
    """列表查询（支持 tags/status 筛选）。"""

@router.get("/{knowhow_id}")
async def get_knowhow(knowhow_id: str, db=Depends(get_db), _=Depends(get_current_user)):
    """获取单条详情。"""

@router.put("/{knowhow_id}")
async def update_knowhow(knowhow_id: str, req: UpdateRequest, db=Depends(get_db), _=Depends(get_current_user)):
    """编辑标题/标签/状态。"""

@router.delete("/{knowhow_id}")
async def delete_knowhow(knowhow_id: str, db=Depends(get_db), _=Depends(get_current_user)):
    """删除（同时删除 Markdown 文件）。"""
```

**路由注册**：在 `comobot/api/gateway.py` 中 `app.include_router(knowhow.router)` 追加。

---

##### 任务 2.5 — MemorySearchEngine 扩展

**修改文件**：`comobot/agent/memory_search.py`

**变更 1** — `_discover_files()` 增加 knowhow 目录：

```python
def _discover_files(self) -> list[tuple[str, Path]]:
    files = []
    # ... 现有 memory 文件发现逻辑保持不变 ...

    # 新增：Know-how 文件
    knowhow_dir = self.workspace / "knowhow"
    if knowhow_dir.exists():
        for p in sorted(knowhow_dir.glob("*.md")):
            if not p.name.startswith("."):
                files.append((f"knowhow/{p.name}", p))

    return files
```

**变更 2** — `search()` 增加 `file_filter` 参数：

```python
def search(
    self,
    query: str,
    max_results: int = 5,
    file_filter: str | None = None,  # 新增：如 "knowhow/" 仅搜索该前缀
) -> list[MemoryChunk]:
    # 在 _bm25_search 和 _vector_search 中追加条件：
    # WHERE file_path LIKE '{file_filter}%'
    ...
```

**兼容性**：`file_filter=None` 时行为与原有完全一致，不影响现有 Memory 搜索。

---

#### Phase 3：Know-how 检索注入 + 前端

##### 任务 3.1 — ContextBuilder Know-how 注入

**修改文件**：`comobot/agent/context.py`

**变更**：`build_system_prompt` 方法签名增加 `user_message` 参数：

```python
def build_system_prompt(
    self,
    skill_names=None,
    user_message: str | None = None,  # 新增
) -> str:
    parts = [...]  # 现有 Identity → Bootstrap → Memory → Skills 逻辑

    # 在 Memory 和 Skills 之间插入 Know-how 段
    if user_message and self._memory_engine:
        knowhow_chunks = self._memory_engine.search(
            user_message, max_results=3, file_filter="knowhow/"
        )
        # 过滤低分结果
        knowhow_chunks = [c for c in knowhow_chunks if c.score >= 0.3]
        if knowhow_chunks:
            text = self._format_knowhow(knowhow_chunks)
            # 插入到 Memory 之后、Skills 之前
            parts.insert(memory_index + 1, f"# Relevant Experience (Know-how)\n\n{text}")

    return "\n\n---\n\n".join(parts)

def _format_knowhow(self, chunks: list) -> str:
    """格式化 Know-how 检索结果为 Markdown 片段。"""
    sections = []
    for chunk in chunks:
        sections.append(
            f"## {chunk.file_path}\n"
            f"(relevance: {chunk.score:.2f})\n\n"
            f"{chunk.content}"
        )
    return "\n\n".join(sections)
```

**调用方变更**：`AgentLoop._run_agent_loop` 中构建 system prompt 时传入当前用户消息。

---

##### 任务 3.2 — `MessageSelector.vue` 对话框多选模式

**新建文件**：`web/src/components/MessageSelector.vue`

```vue
<template>
  <div class="message-selector">
    <!-- 工具栏按钮 -->
    <n-button v-if="!selecting" size="small" @click="selecting = true">
      提取经验
    </n-button>

    <!-- 多选模式下，每条消息前显示 checkbox -->
    <slot :selecting="selecting" :selected="selected" :toggleSelect="toggleSelect" />

    <!-- 底部浮动操作栏 -->
    <Transition name="slide-up">
      <div v-if="selecting && selected.size > 0" class="action-bar">
        <span>已选 {{ selected.size }} 条消息</span>
        <n-button type="primary" @click="$emit('extract', [...selected])">
          保存为 Know-how
        </n-button>
        <n-button @click="cancel">取消</n-button>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { NButton } from 'naive-ui'

defineEmits<{ extract: [ids: number[]] }>()

const selecting = ref(false)
const selected = ref(new Set<number>())

function toggleSelect(id: number) {
  if (selected.value.has(id)) selected.value.delete(id)
  else selected.value.add(id)
}
function cancel() { selecting.value = false; selected.value.clear() }
</script>
```

---

##### 任务 3.3 — `KnowhowPreview.vue` 预览与保存

**新建文件**：`web/src/components/KnowhowPreview.vue`

```vue
<template>
  <n-modal v-model:show="visible" preset="card" title="Know-how 预览" style="width: 600px">
    <n-spin :show="loading">
      <n-form v-if="preview" label-placement="top">
        <n-form-item label="标题">
          <n-input v-model:value="preview.title" />
        </n-form-item>
        <n-form-item label="目标">
          <n-input v-model:value="preview.goal" type="textarea" :rows="2" />
        </n-form-item>
        <n-form-item label="关键步骤">
          <div v-for="(step, i) in preview.steps" :key="i">
            {{ i + 1 }}. {{ step }}
          </div>
        </n-form-item>
        <n-form-item label="标签">
          <n-dynamic-tags v-model:value="preview.tags" />
        </n-form-item>
      </n-form>
    </n-spin>
    <template #action>
      <n-button type="primary" :loading="saving" @click="save">确认保存</n-button>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import api from '@/api/client'

const props = defineProps<{
  sessionKey: string
  messageIds: number[]
  show: boolean
}>()
const emit = defineEmits<{ saved: []; 'update:show': [v: boolean] }>()

const visible = ref(false)
const preview = ref<any>(null)
const loading = ref(false)
const saving = ref(false)

watch(() => props.show, async (v) => {
  visible.value = v
  if (v) {
    loading.value = true
    const { data } = await api.post('/knowhow/extract', {
      session_key: props.sessionKey,
      message_ids: props.messageIds,
    })
    preview.value = data.preview
    loading.value = false
  }
})

async function save() {
  saving.value = true
  await api.post('/knowhow', {
    preview: preview.value,
    session_key: props.sessionKey,
    message_ids: props.messageIds,
  })
  saving.value = false
  emit('saved')
  emit('update:show', false)
}
</script>
```

---

##### 任务 3.4 — `KnowhowSidebar.vue` 侧边栏

**新建文件**：`web/src/components/KnowhowSidebar.vue`

```vue
<template>
  <div class="knowhow-sidebar">
    <div class="sidebar-header">
      <span>Know-how</span>
      <n-input v-model:value="search" size="small" placeholder="搜索经验..." clearable />
    </div>
    <div class="knowhow-list">
      <div
        v-for="item in filtered"
        :key="item.id"
        class="knowhow-item"
        @click="$emit('select', item.id)"
      >
        <div class="title">{{ item.title }}</div>
        <div class="tags">
          <n-tag v-for="tag in JSON.parse(item.tags)" :key="tag" size="tiny">{{ tag }}</n-tag>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { NInput, NTag } from 'naive-ui'
import api from '@/api/client'

defineEmits<{ select: [id: string] }>()

const items = ref<any[]>([])
const search = ref('')

const filtered = computed(() =>
  items.value.filter(
    (i) => !search.value || i.title.includes(search.value) || i.tags.includes(search.value),
  ),
)

onMounted(async () => {
  const { data } = await api.get('/knowhow')
  items.value = data
})
</script>
```

---

##### 任务 3.5 — `KnowhowView.vue` 详情页

**新建文件**：`web/src/views/KnowhowView.vue`

提供完整 Know-how 查看、编辑标题/标签、归档、删除功能。使用 `n-card` + `n-descriptions` 展示元数据，`v-md-preview` 或 `<pre>` 渲染 Markdown 正文。路由注册为 `/knowhow/:id`。

---

#### Phase 4：增强与打磨

##### 任务 4.1 — Know-how Agent 工具

**新建文件**：`comobot/agent/tools/knowhow_tools.py`

**复用模式**：完全遵循 `memory_tools.py` 的 `Tool` 子类模式。

```python
from comobot.agent.tools.base import Tool

class KnowhowSearchTool(Tool):
    def __init__(self, engine, store):
        self._engine = engine
        self._store = store

    @property
    def name(self) -> str: return "knowhow_search"

    @property
    def description(self) -> str:
        return "搜索过往成功经验（Know-how），返回与查询相关的经验摘要列表。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "max_results": {"type": "integer", "default": 3, "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs) -> str:
        query = kwargs["query"]
        max_results = kwargs.get("max_results", 3)
        chunks = self._engine.search(query, max_results=max_results, file_filter="knowhow/")
        # 格式化为 JSON 字符串返回
        ...


class KnowhowSaveTool(Tool):
    """Agent 主动保存当前对话经验为 Know-how。"""

    @property
    def name(self) -> str: return "knowhow_save"

    @property
    def description(self) -> str:
        return "将当前对话中的成功经验保存为 Know-how，供未来类似问题参考。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "经验标题（≤20字）"},
                "goal": {"type": "string", "description": "目标描述"},
                "steps": {"type": "array", "items": {"type": "string"}, "description": "关键步骤"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "分类标签"},
                "outcome": {"type": "string", "description": "最终结果"},
            },
            "required": ["title", "goal", "steps", "tags"],
        }

    async def execute(self, **kwargs) -> str:
        # 调用 KnowhowStore.create() 保存
        ...
```

**工具注册**：在 `AgentLoop.__init__` 或工具注册入口中：

```python
from comobot.agent.tools.knowhow_tools import KnowhowSearchTool, KnowhowSaveTool
registry.register(KnowhowSearchTool(memory_engine, knowhow_store))
registry.register(KnowhowSaveTool(knowhow_store))
```

---

##### 任务 4.2 — `usage_count` 统计

**修改文件**：`comobot/agent/context.py`、`comobot/knowhow/store.py`

在 `ContextBuilder._format_knowhow` 中，每次 Know-how 被注入上下文时调用 `store.increment_usage(id)`。API `GET /api/knowhow` 支持 `?sort=usage_count` 返回热门经验。

---

##### 任务 4.3 — Know-how → Skill 升级建议

**修改文件**：`comobot/api/routes/knowhow.py`

在 `GET /api/knowhow` 响应中，为 `usage_count >= 10` 的条目追加 `"suggest_upgrade": true` 字段。前端 `KnowhowSidebar.vue` 显示升级提示图标。

---

##### 任务 4.4 — 端到端测试

**新建文件**：`tests/test_knowhow.py`、`tests/test_session_channel.py`

```python
# tests/test_knowhow.py
import pytest
from comobot.knowhow.store import KnowhowStore
from comobot.knowhow.extractor import extract_knowhow

class TestKnowhowStore:
    """KnowhowStore CRUD 测试。"""

    async def test_create_and_get(self, tmp_path, mock_db):
        store = KnowhowStore(tmp_path, mock_db)
        result = await store.create(
            preview={"title": "测试", "goal": "验证", "steps": ["步骤1"], "tags": ["test"]},
            raw_messages=[{"role": "user", "content": "hello"}],
        )
        assert result["id"].startswith("kh_")
        assert (tmp_path / "knowhow" / f"{result['id']}_测试.md").exists()

        fetched = await store.get(result["id"])
        assert fetched["title"] == "测试"

    async def test_list_filter_by_tags(self, tmp_path, mock_db): ...
    async def test_delete_removes_file(self, tmp_path, mock_db): ...
    async def test_increment_usage(self, tmp_path, mock_db): ...

class TestKnowhowExtractor:
    """LLM 摘要提取测试（mock LLM 响应）。"""
    async def test_extract_returns_structured(self, mock_litellm): ...

class TestMemorySearchKnowhow:
    """MemorySearchEngine 扩展测试。"""
    def test_discover_files_includes_knowhow(self, tmp_path): ...
    def test_search_with_file_filter(self, tmp_path): ...

class TestKnowhowAPI:
    """REST API 端到端测试（使用 FastAPI TestClient）。"""
    async def test_extract_endpoint(self, client): ...
    async def test_crud_lifecycle(self, client): ...

# tests/test_session_channel.py
class TestSessionByChannel:
    """渠道聚合 API 测试。"""
    async def test_by_channel_grouping(self, client): ...
    async def test_empty_sessions(self, client): ...

class TestSessionWebSocket:
    """WebSocket 推送测试。"""
    async def test_new_message_broadcast(self, client): ...
    async def test_reconnect_incremental(self, client): ...
```

---

### 6.3 任务依赖关系与并行执行策略

```
Phase 1                          Phase 2
┌─────────────────────┐          ┌─────────────────────┐
│ 1.1 by-channel API ─┐         │ 2.1 DB migration ───┐│
│ 1.2 WS 推送 ────────┼──→ 1.4  │ 2.2 KnowhowStore ──┼┼──→ 2.4 REST API
│ 1.3 ChannelTree ─────┘   │    │ 2.3 LLM extractor ──┘│    │
│ 1.5 侧边栏布局 ←─────────┘    │ 2.5 Search 扩展       │    │
└─────────────────────┘          └─────────────────────┘    │
                                                             │
Phase 3                          Phase 4                     │
┌─────────────────────┐          ┌───────────────────┐      │
│ 3.1 Context 注入 ←──2.5       │ 4.1 Agent 工具 ←──2.2   │
│ 3.2 MessageSelector ──→ 3.3 ←─┘  4.2 usage_count     │
│ 3.4 KnowhowSidebar ←─ 2.4     │ 4.3 升级建议 ←─ 4.2  │
│ 3.5 KnowhowView ←── 2.4       │ 4.4 端到端测试 ←─ ALL │
└─────────────────────┘          └───────────────────┘
```

**并行策略**：

| 阶段 | 可并行任务 | 串行依赖 |
|:---|:---|:---|
| Phase 1+2 同时启动 | 1.1/1.3/1.5 并行；2.1→2.2→2.4 串行 | 1.2→1.4（WS 先于面板） |
| Phase 2 内部 | 2.2 与 2.3 并行 | 2.1 先于 2.2（需要表结构） |
| Phase 3 | 3.2 与 3.4/3.5 并行 | 3.1 依赖 2.5；3.3 依赖 3.2+2.4 |
| Phase 4 | 4.1/4.2/4.3 并行 | 4.4 依赖所有任务完成 |

**最短路径**：Phase 1 和 Phase 2 并行推进，Phase 3 在 Phase 2 核心（2.1-2.4）完成后启动，Phase 4 最后收尾。

---

### 6.4 现有模式复用索引

| 复用模式 | 源文件 | 复用位置 | 复用内容 |
|:---|:---|:---|:---|
| WebSocket broadcast | `comobot/api/routes/ws.py` L13-102 `ConnectionManager` | 任务 1.2 | 连接池管理 + 失败清理的 `broadcast_*` 模式 |
| Tool 基类 | `comobot/agent/tools/base.py` `Tool` ABC | 任务 4.1 | `name/description/parameters/execute` 四属性模式 |
| Tool 注册 | `comobot/agent/tools/memory_tools.py` | 任务 4.1 | `MemorySearchTool` 构造函数注入 engine 的模式 |
| 路由注册 | `comobot/api/routes/sessions.py` | 任务 1.1, 2.4 | `Depends(get_db)` + `Depends(get_current_user)` 依赖注入 |
| DB 迁移 | `comobot/db/migrations.py` `MIGRATIONS` 列表 | 任务 2.1 | `(version, name, sql)` 三元组追加模式 |
| 文件发现 | `comobot/agent/memory_search.py` `_discover_files` | 任务 2.5 | `glob("*.md")` + 路径前缀分类 |
| 上下文构建 | `comobot/agent/context.py` `build_system_prompt` | 任务 3.1 | `parts` 列表拼接 + `"\n\n---\n\n".join()` |
| Session 存储 | `comobot/agent/loop.py` `_save_turn` | 任务 1.2 | 持久化后触发副作用的时机 |
| Vue 组件 | `web/src/views/SessionsView.vue` | 任务 1.3-1.5 | 两栏布局 + WebSocket 集成模式 |

---

### 6.5 验证方案

#### 第一层：单元测试

| 测试目标 | 文件 | 覆盖范围 |
|:---|:---|:---|
| KnowhowStore CRUD | `tests/test_knowhow.py` | 创建/读取/更新/删除/usage_count |
| LLM 摘要提取 | `tests/test_knowhow.py` | Mock LLM 响应，验证结构化输出解析 |
| MemorySearchEngine 扩展 | `tests/test_knowhow.py` | `_discover_files` 含 knowhow/、`file_filter` 过滤 |
| Session 聚合 SQL | `tests/test_session_channel.py` | 多渠道分组、alias 关联、空数据 |

#### 第二层：API 测试

| 测试目标 | 方法 | 验证点 |
|:---|:---|:---|
| `GET /api/sessions/by-channel` | FastAPI `TestClient` | 返回结构、渠道分组正确性 |
| `POST /api/knowhow/extract` | FastAPI `TestClient` | LLM 调用 + 结构化响应 |
| Know-how CRUD | FastAPI `TestClient` | 创建→查询→更新→删除全生命周期 |

#### 第三层：WebSocket 测试

| 测试目标 | 方法 | 验证点 |
|:---|:---|:---|
| Session 消息推送 | `TestClient.websocket_connect` | 消息写入后 WS 客户端收到事件 |
| 断连重连 | 模拟断连 + 增量拉取 | 重连后消息不丢失 |

#### 第四层：前端 E2E

| 测试目标 | 工具 | 验证点 |
|:---|:---|:---|
| 渠道树展示 | 浏览器手动 / Playwright | 折叠/展开、Session 切换 |
| 消息多选 + Know-how 提取 | 浏览器手动 / Playwright | 勾选→预览→保存完整流程 |
| Know-how 侧边栏 | 浏览器手动 / Playwright | 列表加载、搜索过滤、点击详情 |

#### 第五层：全量回归

```bash
# 后端全量测试
.venv/bin/pytest tests/ -v

# 代码质量
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

确保现有 138 个测试全部通过，无回归。

---

### 6.6 开发完成进度

> 最后更新：2026-03-12

#### Phase 1：Session 渠道视图

| # | 任务 | 状态 | 完成日期 | 备注 |
|:---|:---|:---|:---|:---|
| 1.1 | `GET /api/sessions/by-channel` 聚合接口 | ✅ 已完成 | 2026-03-12 | |
| 1.2 | `WS /ws/sessions` WebSocket 推送 | ✅ 已完成 | 2026-03-12 | ConnectionManager + AgentLoop 集成 |
| 1.3 | `ChannelTree.vue` 渠道树组件 | ✅ 已完成 | 2026-03-12 | |
| 1.4 | `SessionPanel.vue` WebSocket 增量追加 | ✅ 已完成 | 2026-03-12 | 集成到 SessionsView + useSessionWS |
| 1.5 | 侧边栏布局重构 | ✅ 已完成 | 2026-03-12 | 上下分栏：ChannelTree + KnowhowSidebar |

#### Phase 2：Know-how 后端核心

| # | 任务 | 状态 | 完成日期 | 备注 |
|:---|:---|:---|:---|:---|
| 2.1 | SQLite `knowhow` 表迁移 | ✅ 已完成 | 2026-03-12 | migration v2 |
| 2.2 | `KnowhowStore` 文件读写模块 | ✅ 已完成 | 2026-03-12 | CRUD + increment_usage |
| 2.3 | LLM 摘要提取 Prompt + 接口 | ✅ 已完成 | 2026-03-12 | litellm + JSON mode |
| 2.4 | Know-how REST API（6 端点） | ✅ 已完成 | 2026-03-12 | extract/CRUD 全部实现 |
| 2.5 | MemorySearchEngine 扩展 | ✅ 已完成 | 2026-03-12 | _discover_files + file_filter |

#### Phase 3：Know-how 检索注入 + 前端

| # | 任务 | 状态 | 完成日期 | 备注 |
|:---|:---|:---|:---|:---|
| 3.1 | ContextBuilder Know-how 注入 | ✅ 已完成 | 2026-03-12 | Memory 与 Skills 之间注入 |
| 3.2 | `MessageSelector.vue` 对话框多选 | ✅ 已完成 | 2026-03-12 | 集成到 SessionsView toolbar |
| 3.3 | `KnowhowPreview.vue` 预览与保存 | ✅ 已完成 | 2026-03-12 | Modal + LLM 提取预览 |
| 3.4 | `KnowhowSidebar.vue` 侧边栏 | ✅ 已完成 | 2026-03-12 | 搜索 + 标签 + 升级提示 |
| 3.5 | `KnowhowView.vue` 详情页 | ✅ 已完成 | 2026-03-12 | 查看/编辑/归档/删除 |

#### Phase 4：增强与打磨

| # | 任务 | 状态 | 完成日期 | 备注 |
|:---|:---|:---|:---|:---|
| 4.1 | Know-how Agent 工具 | ✅ 已完成 | 2026-03-12 | knowhow_search + knowhow_save |
| 4.2 | `usage_count` 统计 | ✅ 已完成 | 2026-03-12 | 检索命中时递增，API 返回热门 |
| 4.3 | Know-how → Skill 升级建议 | ✅ 已完成 | 2026-03-12 | usage_count >= 10 时 suggest_upgrade |
| 4.4 | 端到端测试 | ✅ 已完成 | 2026-03-12 | 15 新测试全部通过 |

#### 总览

| Phase | 总任务 | 已完成 | 进度 |
|:---|:---|:---|:---|
| Phase 1: Session 渠道视图 | 5 | 5 | 100% |
| Phase 2: Know-how 后端核心 | 5 | 5 | 100% |
| Phase 3: Know-how 检索 + 前端 | 5 | 5 | 100% |
| Phase 4: 增强与打磨 | 4 | 4 | 100% |
| **总计** | **19** | **19** | **100%** |

#### 状态说明

| 图标 | 含义 |
|:---|:---|
| ⬜ 未开始 | 尚未启动 |
| 🔵 进行中 | 开发中 |
| 🟡 待验证 | 代码完成，等待测试/review |
| ✅ 已完成 | 测试通过，合入主分支 |
| ⛔ 阻塞 | 被依赖项阻塞或遇到问题 |
