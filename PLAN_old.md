# comobot 开发方案

## Context

将现有 nanobot 项目（~11K 行 Python + 370 行 TypeScript 的轻量级多渠道 AI 助手框架）升级为 comobot —— 增加 Web 控制面板、可视化编排器、SQLite 存储、安全体系和一键部署能力。采用单 Agent 按 Phase 串行推进，共 5 个 Phase、42 项任务。

**用户决策**:
- **数据迁移**: 不自动迁移 `~/.nanobot/`。检测到时打印友好提示："检测到您安装了其他小助手，可将数据进行迁移"，并给出 `mv ~/.nanobot ~/.comobot` 等迁移指引
- **前端 UI**: Vue 3 组件库，极简科技风（参考 Manus / Apple 官网风格）。使用 Naive UI 组件库 + 自定义主题
- **开发节奏**: 全程自动推进，Gate 通过后直接进入下一 Phase

---

## Phase 0: 品牌重命名 (10 tasks)

**原则**: 按「目录 → 包元数据 → 代码路径 → 环境变量 → 文案 → 外围」顺序，每步后跑测试。

### 0.1 Python 包目录重命名
```bash
git mv nanobot/ comobot/
```
然后批量替换所有 `.py` 文件中的 `from nanobot.` → `from comobot.`、`import nanobot` → `import comobot`。

**关键文件** (import 最多):
- `comobot/cli/commands.py` (~20 处 nanobot import)
- `comobot/agent/loop.py` (15 处)
- `comobot/agent/subagent.py` (8 处)
- `comobot/channels/manager.py` (5 处)
- 所有 `tests/*.py` (16 个文件)

**验证**: `python -c "import comobot"` + `grep -r "from nanobot\." comobot/ tests/ --include="*.py" | wc -l` = 0

### 0.2 包元数据 (pyproject.toml)
- `name = "nanobot-ai"` → `"comobot"`
- `nanobot = "nanobot.cli.commands:app"` → `comobot = "comobot.cli.commands:app"`
- `packages = ["nanobot"]` → `["comobot"]`
- 所有 `[tool.hatch.build]` 中的 `nanobot/` → `comobot/`
- `"nanobot" = "nanobot"` → `"comobot" = "comobot"`
- `"bridge" = "nanobot/bridge"` → `"bridge" = "comobot/bridge"`
- authors → `"comobot contributors"`

**验证**: `pip install -e ".[dev]"` + `comobot --help`

### 0.3 配置路径 (~/.nanobot → ~/.comobot)
- `comobot/utils/helpers.py:16,21` — `get_data_path()` 返回 `~/.comobot`
- `comobot/config/loader.py:11` — 默认路径改为 `.comobot`
- `comobot/config/schema.py:223` — workspace 默认值 `~/.comobot/workspace`
- `comobot/session/manager.py:82` — legacy 目录
- `comobot/cli/commands.py:90` — history 文件路径
- `comobot/cli/commands.py:227` — 错误提示中的路径
- 各 channel 文件中的 media 缓存路径

**旧数据检测**: 在 `comobot/utils/helpers.py` 的 `get_data_path()` 中，如果 `~/.comobot` 不存在但 `~/.nanobot` 存在，打印提示:
```
检测到您安装了其他小助手，可将数据进行迁移:
  mv ~/.nanobot ~/.comobot
迁移后重新启动即可继续使用。
```
仅提示，不自动迁移。

### 0.4 环境变量前缀
- `comobot/config/schema.py` — `env_prefix="NANOBOT_"` → `"COMOBOT_"`

### 0.5 用户面文案
- `comobot/templates/SOUL.md` — "I am nanobot" → "I am comobot"
- `comobot/cli/commands.py` — Typer name/help、console.print 中的 "nanobot" (~20 处)
- `comobot/agent/context.py` — identity prompt 中的品牌名
- `comobot/__init__.py` — docstring

### 0.6 TypeScript Bridge
- `bridge/package.json` — name、description
- `bridge/src/index.ts` — AUTH_DIR 默认路径 `.comobot`、console log 品牌名

### 0.7 Docker / Shell 脚本
- `Dockerfile` — `mkdir -p /root/.comobot`、`ENTRYPOINT ["comobot"]`、COPY 路径
- `docker-compose.yml` — 服务名、volume 路径
- `comobot/skills/tmux/scripts/` — `NANOBOT_TMUX_SOCKET_DIR` → `COMOBOT_TMUX_SOCKET_DIR`

### 0.8 技能元数据 key
- `comobot/agent/skills.py:169-175` — `_parse_nanobot_metadata()`: 改为优先读 `"comobot"` key，fallback 读 `"nanobot"`（向后兼容）。同时重命名方法为 `_parse_skill_metadata()`
- 6 个 SKILL.md 文件: `{"nanobot":` → `{"comobot":`

### 0.9 文档全量更新
- README.md、SECURITY.md、structure.md、CLAUDE.md、LICENSE
- 模板 .md 文件中残留的 nanobot 引用
- GitHub 引用 `HKUDS/nanobot` → `musenming/comobot`

### 0.10 测试文件更新 + 全量测试
- 16 个测试文件的 import 路径和 mock 路径
- 字符串断言中的 "nanobot"

**Gate G0 验证**:
```bash
python -c "import comobot"
pytest tests/ -v                    # 全部通过
ruff check .                        # 0 errors
comobot --help                      # 品牌正确
grep -r "nanobot" --include="*.py" --include="*.toml" --include="*.ts" comobot/ tests/ bridge/ | wc -l  # 0
```

---

## Phase 1: 基础设施 (8 tasks)

### 1.1 SQLite 存储层核心
**新建文件**:
- `comobot/db/__init__.py`
- `comobot/db/connection.py` — `Database` 类: async connect/close/execute/fetchone/fetchall，WAL pragma
- `comobot/db/migrations.py` — schema_version 表 + migration_001 建所有表（PRD §6.1 的 9 张表）

**新增依赖** (pyproject.toml): `aiosqlite>=0.20.0`

**验证**: 单元测试 `tests/test_db.py` — 建表、CRUD、WAL 模式确认

### 1.2 会话存储迁移 (JSONL → SQLite)
**新建**: `comobot/session/sqlite_manager.py` — `SQLiteSessionManager` 类，与现有 `SessionManager` 相同接口
**修改**: `comobot/cli/commands.py` gateway() — 当 DB 可用时使用 SQLiteSessionManager

保留原 `SessionManager` 作为 fallback（agent 命令仍用文件模式）。

**验证**: `pytest tests/test_consolidate_offset.py tests/test_loop_save_turn.py -x`

### 1.3 Cron 存储迁移
**新建**: `comobot/cron/sqlite_store.py` — SQLite 版本的 cron 存储后端
**修改**: `comobot/cron/service.py` — 支持注入不同存储后端

**验证**: `pytest tests/test_cron_service.py -x`

### 1.4 凭证加密模块
**新建**:
- `comobot/security/__init__.py`
- `comobot/security/crypto.py` — `CredentialVault` 类: AES-256-GCM 加密/解密，密钥从环境变量或 `~/.comobot/secret.key` 加载

**新增依赖**: `cryptography>=44.0.0`

**验证**: 单元测试 — 加密→解密 roundtrip、错误 key 解密失败

### 1.5 FastAPI 后端骨架
**新建**:
- `comobot/api/__init__.py`
- `comobot/api/app.py` — `create_app()` 工厂函数，挂载路由 + CORS + 静态文件
- `comobot/api/deps.py` — 依赖注入 (db, vault, auth, agent, bus)
- `comobot/api/routes/__init__.py`
- `comobot/api/routes/health.py` — `GET /api/health`

**关键架构决策 — FastAPI 与 gateway 共进程**:

在 `cli/commands.py` gateway() 的 `run()` 函数中（当前 line 402-419），将 FastAPI 嵌入同一个 asyncio 事件循环:

```python
async def run():
    # ... 现有 cron.start(), heartbeat.start() ...

    # 新增: 创建 FastAPI 并用 uvicorn.Server 启动
    from comobot.api.app import create_app
    import uvicorn

    fastapi_app = create_app(db=db, vault=vault, agent=agent, channels=channels, bus=bus)
    uvi_config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=8080)
    server = uvicorn.Server(uvi_config)

    await asyncio.gather(
        agent.run(),
        channels.start_all(),
        server.serve(),          # 新增
    )
```

Vue 3 构建产物通过 FastAPI `StaticFiles` mount 在 `/` 路径，API 路由在 `/api` 前缀下。

**新增依赖**: `fastapi>=0.115.0`, `uvicorn[standard]>=0.34.0`

**验证**: 启动 gateway → `curl http://localhost:8080/api/health` → `{"status": "ok"}`

### 1.6 JWT 认证模块
**新建**: `comobot/security/auth.py` — `AuthManager` 类: create_admin、authenticate（返回 JWT）、verify_token
**新建**: `comobot/api/routes/auth.py` — `POST /api/auth/login`、`POST /api/auth/refresh`
**修改**: `comobot/api/deps.py` — 添加 `get_current_user` 依赖

**新增依赖**: `python-jose[cryptography]>=3.3.0`, `bcrypt>=4.0.0`

**验证**: 单元测试 — token 生成/验证/过期

### 1.7 Vue 3 前端初始化
**新建目录**: `web/`

**技术栈**: Vue 3 + TypeScript + Vite + Naive UI + Pinia + Vue Router + Vue Flow

**设计风格**: 极简科技风（参考 Manus / Apple 官网）
- 大量留白，黑白灰主色调，极少装饰元素
- 圆角卡片、毛玻璃效果、微妙阴影
- SF Pro / Inter 字体，清晰的信息层级
- Naive UI 自定义暗色主题覆盖默认样式

```bash
npm create vite@latest web -- --template vue-ts
cd web && npm install naive-ui vue-router pinia @vueflow/core @vueflow/background @vueflow/controls
```

配置 vite dev proxy (`/api` → `localhost:8080`)，建立基础路由结构 (/login, /setup, /dashboard, /workflows 等)，配置 Naive UI 全局主题。

**验证**: `cd web && npm run build` 成功

### 1.8 初始化向导
**后端**: `comobot/api/routes/setup.py` — `GET /api/setup/status` + `POST /api/setup`（仅 admin 表为空时可用）
**前端**: `web/src/views/SetupView.vue` — 4 步向导

**验证**: 浏览器走完向导 → admin 创建成功 → 可登录

**Gate G1 验证**:
```bash
pytest tests/ -v                           # 含新增的 db/crypto/auth 测试
curl http://localhost:8080/api/health      # FastAPI 运行
curl -X POST http://localhost:8080/api/auth/login  # JWT 流程
cd web && npm run build                    # 前端构建
```

---

## Phase 2: 核心功能 (13 tasks)

### 2.8-2.10 编排引擎后端（优先于前端页面）

**2.8 流程执行引擎**:
- `comobot/orchestrator/__init__.py`
- `comobot/orchestrator/engine.py` — `WorkflowEngine`: 加载 workflow definition → 解析 DAG → 拓扑排序 → 逐节点执行
- `comobot/orchestrator/nodes.py` — 7 种节点类型: Trigger, LLMCall, Tool, Condition, Response, Delay, SubAgent
- `comobot/orchestrator/variables.py` — `{{trigger.message}}` 等变量替换

**2.9 模板解析器**:
- `comobot/orchestrator/templates.py` — 预设模板定义 (smart_customer_service, scheduled_summary, message_forwarder, document_assistant)
- API: `POST /api/workflows/from-template`

**2.10 消息路由集成**:
- **修改** `comobot/agent/loop.py` `_dispatch()` 方法（line 294-314）:
  - 在获取锁之前，先检查 `self.orchestrator.match_trigger(msg)`
  - 匹配则交给编排引擎执行，不匹配则走原有 AgentLoop 路径
  - orchestrator 是可选属性，不设置时完全不影响现有行为

### 2.13 Telegram Webhook 模式
- **修改** `comobot/config/schema.py` TelegramConfig — 新增 `mode`, `webhook_url`, `secret_token` 字段
- **修改** `comobot/channels/telegram.py` start() — webhook 模式下不启动 polling，而是注册 webhook URL
- **新建** `comobot/api/routes/webhook.py` — `POST /webhook/telegram` 端点，校验 secret_token

### 2.1-2.7 Web UI 页面

每个任务 = 一个后端 route 文件 + 一个前端 view 文件:

| Task | 后端路由 | 前端页面 | 数据源 |
|------|---------|---------|--------|
| 2.1 仪表盘 | `routes/dashboard.py` | `DashboardView.vue` | sessions/messages/audit_log 聚合查询 |
| 2.2 模型管理 | `routes/providers.py` | `ProvidersView.vue` | credentials 表 + 连通性测试 |
| 2.3 渠道管理 | `routes/channels.py` | `ChannelsView.vue` | config.json + ChannelManager |
| 2.4 会话查看 | `routes/sessions.py` | `SessionsView.vue` | sessions + messages 表 |
| 2.5 定时任务 | `routes/cron.py` | `CronView.vue` | cron_jobs 表 |
| 2.6 日志监控 | `routes/logs.py` + `WS /ws/logs` | `LogsView.vue` | loguru sink → WebSocket |
| 2.7 系统设置 | `routes/settings.py` | `SettingsView.vue` | admin 表 + 文件系统 |

### 2.11-2.12 编排器前端
- **2.11 模板模式**: `TemplateWizard.vue` — 模板卡片选择 → 参数表单 → 提交
- **2.12 高级模式**: `FlowEditor.vue` — Vue Flow 拖拽节点编辑器，自定义节点组件

**Gate G2 验证**: 模板模式 E2E、高级模式 E2E、无匹配回退 AgentLoop、Telegram 双模式、全量 pytest

---

## Phase 3: 增强与加固 (6 tasks)

### 3.1 多 Key 轮询
- **修改** `comobot/config/schema.py` — ProviderConfig 新增 `api_keys: list[str]`、`strategy: str`
- **新建** `comobot/providers/key_rotator.py` — `KeyRotator`: round_robin/random/least_used 策略
- **修改** `comobot/providers/litellm_provider.py` — chat() 中调用 rotator.next_key()

### 3.2 429 退避与 Key 冷却
- **修改** `comobot/providers/litellm_provider.py` — 包装 acompletion 调用，429 时 mark_cooldown + 切 key + 指数退避

### 3.3 Per-session 并发锁
- **修改** `comobot/agent/loop.py` line 112:
  - `self._processing_lock = asyncio.Lock()` → `self._session_locks = weakref.WeakValueDictionary()`
  - `_dispatch()` 中按 `msg.session_key` 取锁（复用已有的 WeakValueDictionary 模式，参考 line 110 的 `_consolidation_locks`）

### 3.4 优雅停机
- **修改** `comobot/cli/commands.py` gateway() `run()` 函数:
  - 添加 signal handler (SIGTERM/SIGINT)
  - 收到信号 → 停止接收 → 等待 active_tasks (30s timeout) → 持久化 → 关闭连接

### 3.5 审计日志
- **新建** `comobot/db/audit.py` — `AuditLogger`: 写入 audit_log 表
- 在 AgentLoop、Provider、Auth 等关键点注入日志记录
- API: `GET /api/logs` 带 level/module/time 过滤

### 3.6 Prompt 注入防护
- **修改** `comobot/agent/context.py` — 用户输入中 `<system>` 等标记转义
- **修改** `comobot/orchestrator/variables.py` — 变量替换时转义

**Gate G3 验证**: 多 Key 分配测试、429 退避测试、并发锁测试、SIGTERM 测试、审计日志查询、注入测试

---

## Phase 4: 部署打磨 (5 tasks)

### 4.1 Docker-compose 优化
- **修改** `Dockerfile` — 多阶段构建: Node.js 前端构建 + Python 后端，构建产物 COPY 到 `comobot/web/dist/`
- **修改** `docker-compose.yml` — 单服务 `comobot`，端口 8080

### 4.2 数据库自动迁移
- **完善** `comobot/db/migrations.py` — 启动时检查 schema_version → 自动执行未运行的迁移

### 4.3 端到端测试
- **新建** `tests/test_api.py` — API 端点 + JWT 流程
- **新建** `tests/test_e2e.py` — 完整消息流、编排流程执行

### 4.4 文档更新
- README.md、structure.md、CLAUDE.md 同步最新架构

### 4.5 安全审计
- 所有 API 端点（除 /setup、/auth/login、/webhook）需 JWT
- credentials 表全部密文
- Telegram webhook 伪造请求被拒

**Gate G4 验证**: docker-compose up → 向导 → Agent 上线 → 数据持久化 → 安全检查 → PRD 42 项全部完成

---

## 跨 Phase 注意事项

### 新增依赖汇总 (pyproject.toml)
```
aiosqlite>=0.20.0
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
python-jose[cryptography]>=3.3.0
bcrypt>=4.0.0
cryptography>=44.0.0
```

### 高频修改文件（需格外注意冲突）
| 文件 | Phase 0 | Phase 1 | Phase 2 | Phase 3 |
|------|---------|---------|---------|---------|
| `cli/commands.py` | rename | +FastAPI/DB 初始化 | | +graceful shutdown |
| `agent/loop.py` | rename | | +orchestrator routing | +per-session lock |
| `config/schema.py` | rename+path+env | | +webhook/multi-key fields | +multi-key fields |
| `pyproject.toml` | rename | +dependencies | | |

### 会话间上下文恢复
| Phase | 新会话先读 |
|-------|-----------|
| 0 | `pyproject.toml`, run `pytest -x` 确认当前状态 |
| 1 | `comobot/db/connection.py`, `comobot/api/app.py`, `comobot/cli/commands.py` (gateway) |
| 2 | `comobot/api/app.py`, `comobot/orchestrator/engine.py`, `comobot/agent/loop.py` (_dispatch) |
| 3 | `comobot/agent/loop.py`, `comobot/providers/litellm_provider.py` |
| 4 | `Dockerfile`, `docker-compose.yml`, `comobot/db/migrations.py` |

### 风险缓解
1. **Phase 0 重命名**: 最高风险。分步执行，每步 `pytest -x`。先目录重命名+import，通过后再改路径/环境变量/文案
2. **FastAPI 共进程**: 通过 `uvicorn.Server` 嵌入现有 asyncio loop，不需要独立进程
3. **SQLite 并发**: WAL 模式 + busy_timeout=5000ms + 写操作集中在单个 Database 实例
4. **编排器集成**: orchestrator 设为 AgentLoop 的可选属性，不设置时零影响

### 执行节奏
- 全程自动推进，Gate 通过后直接进入下一 Phase
- 遇到阻塞（测试失败、依赖问题等）时自行修复，修复不了再暂停询问用户

### 验证方式
```bash
# 每个任务完成后
ruff check . && ruff format --check .
pytest tests/ -x

# 每个 Phase 结束后执行对应 Gate 的完整检查清单
# Gate 通过 → 更新 PRD.md 进度表 → 直接进入下一 Phase
```
