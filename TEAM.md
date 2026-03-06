# comobot — 单 Agent 开发方案

> 单 Agent 按 Phase 顺序推进，每个 Phase 结束通过 Quality Gate 后进入下一阶段。

---

## 1. 方案概述

```
单 Agent 串行推进，按 Phase 0 → 1 → 2 → 3 → 4 顺序执行。
每个 Phase 内按任务编号顺序完成，无依赖的小任务可批量处理。
每个 Phase 结束执行 Quality Gate 自检，通过后进入下一 Phase。
```

**选择单 Agent 的理由**：

- Token 消耗低（无跨 Agent 上下文重复加载和协调通信）
- 接口天然对齐（同一 Agent 写前后端，不存在联调问题）
- 全局视野完整（改一处自然知道影响范围）
- 项目规模可控（核心 ~11K 行，新增预估 8-12K 行）

---

## 2. 工作目录与文件归属

```
comobot/
├── agent/              (改造现有模块)
├── api/                (新建 — FastAPI 后端)
│   ├── routes/
│   ├── middleware/
│   └── deps.py
├── bus/                (维持/增强)
├── channels/           (维持)
├── cli/                (维持)
├── config/             (适配 SQLite)
├── cron/               (存储迁移)
├── db/                 (新建 — SQLite 存储层)
│   ├── engine.py
│   ├── models.py
│   └── migrations/
├── heartbeat/          (维持)
├── orchestrator/       (新建 — 编排引擎)
│   ├── engine.py
│   ├── templates.py
│   └── router.py
├── providers/          (增强多 Key)
├── security/           (新建 — 认证与加密)
│   ├── crypto.py
│   └── auth.py
├── session/            (SQLite 迁移)
├── skills/             (重命名)
├── templates/          (重命名)
└── utils/              (维持)

web/                    (新建 — Vue 3 前端)
├── src/
│   ├── views/
│   ├── components/
│   ├── stores/
│   ├── api/
│   └── router/
├── package.json
└── vite.config.ts
```

---

## 3. 执行时序

```
Phase 0: 品牌重命名
├─ 0.1~0.10 全量替换 nanobot → comobot
└─ Gate G0 验收
     │
     ▼
Phase 1: 基础设施
├─ 1.1 SQLite 核心层
├─ 1.2 会话存储迁移
├─ 1.3 Cron 存储迁移
├─ 1.4 凭证加密模块
├─ 1.5 FastAPI 后端骨架
├─ 1.6 JWT 认证模块
├─ 1.7 Vue 3 前端初始化
├─ 1.8 初始化向导
└─ Gate G1 验收
     │
     ▼
Phase 2: 核心功能
├─ 后端: 2.13 Telegram Webhook
├─ 编排引擎: 2.8 → 2.9 → 2.10
├─ Web UI: 2.1 → 2.2 → 2.3 → 2.4 → 2.5 → 2.6 → 2.7
├─ 编排器前端: 2.11 → 2.12
├─ Gate G2a 中期检查 (编排器联调)
└─ Gate G2 验收
     │
     ▼
Phase 3: 增强与加固
├─ 3.1 多 Key 轮询
├─ 3.2 429 退避与 Key 冷却
├─ 3.3 Per-session 并发锁
├─ 3.4 优雅停机
├─ 3.5 审计日志
├─ 3.6 Prompt 注入防护
└─ Gate G3 验收
     │
     ▼
Phase 4: 部署打磨
├─ 4.1 docker-compose 优化
├─ 4.2 数据库自动迁移
├─ 4.3 端到端测试
├─ 4.4 文档更新
├─ 4.5 安全审计
└─ Gate G4 发布验收
```

---

## 4. Phase 内任务推荐顺序

### Phase 1 — 先后端基础，再前端

```
1.1 SQLite 核心层          ← 后续所有存储的基础
 ↓
1.2 会话存储迁移            ← 依赖 1.1
1.3 Cron 存储迁移           ← 依赖 1.1
1.4 凭证加密模块            ← 依赖 1.1（credentials 表）
 ↓
1.5 FastAPI 后端骨架        ← 依赖 1.1~1.4 提供的数据层
1.6 JWT 认证模块            ← 依赖 1.5
 ↓
1.7 Vue 3 前端初始化        ← 独立，但放在后端之后可以立即联调
1.8 初始化向导              ← 依赖 1.5~1.7
```

### Phase 2 — 先编排引擎后端，再前端页面，最后编排器 UI

```
2.8  编排执行引擎            ← 编排器核心，优先
2.9  模板解析器              ← 依赖 2.8
2.10 消息路由集成            ← 依赖 2.8
2.13 Telegram Webhook       ← 独立，可穿插
 ↓
2.1~2.7 Web UI 各页面       ← 依赖 Phase 1 的 API
 ↓
2.11 编排器模板模式 UI       ← 依赖 2.9 后端
2.12 编排器高级模式 UI       ← 依赖 2.8 后端
```

### Phase 3 — 按依赖深度排序

```
3.1 多 Key 轮询             ← Provider 层改造
3.2 429 退避                ← 依赖 3.1
3.3 Per-session 并发锁       ← AgentLoop 改造
3.4 优雅停机                ← 依赖 3.3（需等待 processing 任务）
3.5 审计日志                ← 独立
3.6 Prompt 注入防护          ← 独立
```

---

## 5. Quality Gates

每个 Gate 是进入下一 Phase 的硬性门槛。

### Gate G0 — 重命名验收

| # | 检查项 | 执行方式 | 通过标准 |
|---|--------|---------|---------|
| G0.1 | 代码可加载 | `python -c "import comobot"` | 无 ImportError |
| G0.2 | 全量测试 | `pytest tests/ -v` | 全部通过 |
| G0.3 | Lint | `ruff check .` | 0 errors |
| G0.4 | CLI 启动 | `comobot --help` | 输出帮助，品牌为 comobot |
| G0.5 | 残留扫描 | `grep -r "nanobot" --include="*.py" --include="*.toml" --include="*.ts"` | 0 匹配 |
| G0.6 | 路径验证 | 检查默认路径和 env_prefix | `~/.comobot/`、`COMOBOT_` |

### Gate G1 — 基础设施验收

| # | 检查项 | 通过标准 |
|---|--------|---------|
| G1.1 | SQLite 层单测 | 表创建、CRUD、WAL 验证通过 |
| G1.2 | 会话迁移验证 | JSONL 导入 → SQLite → 读取比对一致 |
| G1.3 | 加密模块单测 | 加密 → 解密 roundtrip 成功；错误 key 解密失败 |
| G1.4 | API 启动 | FastAPI 启动无报错，`/docs` 可访问 |
| G1.5 | JWT 流程 | login → token → 受保护端点通过；无 token 返回 401 |
| G1.6 | 前端构建 | `cd web && npm run build` 成功 |
| G1.7 | 向导页面 | 4 步向导可填参、可提交、数据落库 |
| G1.8 | 前后端联通 | 前端 → login → token → dashboard API 返回数据 |

### Gate G2a — 编排器中期检查（不阻塞，暴露问题）

| # | 检查项 | 通过标准 |
|---|--------|---------|
| G2a.1 | 编排引擎单测 | 线性流程执行通过 |
| G2a.2 | 模板解析 | "智能客服"模板 → Workflow JSON 结构正确 |
| G2a.3 | 前端编辑器 | Vue Flow 可拖拽、可连线、可保存 |
| G2a.4 | 编排 roundtrip | 前端创建 → 后端存储 → 前端加载一致 |

### Gate G2 — 核心功能验收

| # | 检查项 | 通过标准 |
|---|--------|---------|
| G2.1 | 模板模式 E2E | 选模板 → 填参 → 启用 → Telegram 收到回复 |
| G2.2 | 高级模式 E2E | 拖拽流程 → 保存 → 触发 → DAG 按序执行 |
| G2.3 | 回退验证 | 不匹配编排的消息走 AgentLoop 正常回复 |
| G2.4 | Web UI 功能 | 模型/渠道/会话/日志等页面正常工作 |
| G2.5 | Telegram 双模式 | Polling + Webhook 均正常 |
| G2.6 | 全量回归 | `pytest tests/ -v` 全部通过 |

### Gate G3 — 增强功能验收

| # | 检查项 | 通过标准 |
|---|--------|---------|
| G3.1 | 多 Key 轮询 | 3 Key 6 消息，round_robin 各 2 次 |
| G3.2 | 429 退避 | Mock 429 → 自动切 Key + 退避 |
| G3.3 | 并发锁 | 同 session 3 条消息，仅 1 条 processing |
| G3.4 | 优雅停机 | SIGTERM → 等待完成 → 持久化 → 退出 |
| G3.5 | 审计日志 | 操作日志完整可查 |
| G3.6 | Prompt 注入 | 注入测试不影响系统行为 |

### Gate G4 — 发布验收

| # | 检查项 | 通过标准 |
|---|--------|---------|
| G4.1 | 一键部署 | `docker-compose up -d` 启动无报错 |
| G4.2 | 初始化向导 | 浏览器访问自动进入向导 |
| G4.3 | 数据持久化 | 重启后数据不丢失 |
| G4.4 | 并发写入 | 100 并发无 `database is locked` |
| G4.5 | 安全检查 | 未认证 401、凭证加密、白名单拦截 |
| G4.6 | 文档同步 | README / structure.md 与实际一致 |
| G4.7 | 进度表 | PRD.md 42 项全部完成 |

---

## 6. 工作规范

### 6.1 代码规范

- 遵循 `ruff` 配置（行宽 100，规则 E/F/I/N/W）
- 新增 Python 模块必须有 `__init__.py`
- 新增 API 端点必须有 Pydantic 请求/响应模型
- 前端使用 Vue 3 Composition API + `<script setup>`

### 6.2 测试规范

- 新增 Python 模块必须有对应 `tests/test_*.py`
- 关键路径（认证、加密、编排、存储）覆盖率 > 80%
- 每个 API 端点至少正常 + 异常两个测试用例

### 6.3 任务完成流程

```
完成任务
  ├─ 运行相关单元测试
  ├─ ruff check + format
  ├─ 更新 PRD.md 进度表（状态标记）
  └─ Phase 结束时执行 Gate 检查
```

### 6.4 上下文管理策略

单 Agent 需注意上下文窗口，采用以下策略：

- **按 Phase 分会话**：每个 Phase 可以开新会话，避免上下文过长
- **Phase 交接时**：读取 PRD.md 进度表 + 相关模块代码恢复上下文
- **大文件分段处理**：重命名等批量操作按目录/模块分批进行
- **善用 CLAUDE.md**：关键决策和接口约定写入 CLAUDE.md，新会话自动加载
