# Comobot Web 全栈开发计划

> 版本: 1.0 | 日期: 2026-03-06 | 基于 UIUX.md 需求规范

## 概述

当前前端仅有基础骨架：11 个 View（6 个 stub）、1 个 Pinia store（auth）、硬编码深色主题、无 CSS 变量系统。后端 API 存在多处缺口（无 WebSocket、渠道配置不可管理、设置接口简陋）。本计划将前端从原型升级为符合 UIUX.md 规范的完整产品，并同步补齐后端接口。

---

## Phase 1 (P0): 基础设施 — 设计系统 + 侧边栏 + 仪表盘

> 所有后续页面的基础，需最先完成

### 1.1 安装前端依赖

**类型**: 前端配置

| 文件 | 操作 |
|------|------|
| `web/package.json` | 新增: `@vueuse/core`, `echarts`, `highlight.js`, `marked`, `date-fns`, `cronstrue` |
| `web/index.html` | 添加 Inter 字体 preconnect link tags，更新 `<title>` |

### 1.2 CSS 变量系统

**类型**: 前端

| 文件 | 操作 |
|------|------|
| `src/assets/variables.css` | **新建** — 全部 Design Token：`:root`（浅色）+ `.dark`（深色）颜色体系、字号层级（11-40px）、8px 基准间距、圆角（6-20px）、投影、缓动曲线、骨架屏 shimmer 动画、呼吸灯动画 |
| `src/style.css` | 修改 — 移除硬编码 `#000`/`#fff`，引用 CSS 变量 |
| `src/main.ts` | 修改 — 导入 variables.css |

### 1.3 主题系统

**类型**: 前端

| 文件 | 操作 |
|------|------|
| `src/stores/theme.ts` | **新建** — Pinia store：`usePreferredDark` + `useStorage('comobot-theme', 'system')`，`isDark` 计算属性，`toggle()` 方法 |
| `src/theme/index.ts` | **新建** — 导出 `darkThemeOverrides` / `lightThemeOverrides`（值来自 UIUX.md §2.1.3） |
| `src/App.vue` | 修改 — `NConfigProvider` 切换为响应式双主题；`onMounted` 中同步 `document.documentElement.classList` |

### 1.4 通用组件（第一批 — 布局基础）

**类型**: 前端

| 文件 | 说明 |
|------|------|
| `src/components/AppSidebar.vue` | **新建** — 可折叠侧边栏（220px↔60px），Logo + 版本号，菜单分组 + 分隔线，激活项左侧 2px 白条，底部 Agent 呼吸灯 + 主题切换 + Logout |
| `src/components/PageLayout.vue` | **新建** — 统一布局包裹（Sidebar + Content + page-header），Props: `title`, `description`，Slots: `#actions`, `#default` |
| `src/components/StatusBadge.vue` | **新建** — 8px 彩色圆点（带呼吸灯动画）+ 文字标签，Props: `status: 'online'\|'offline'\|'error'\|'paused'` |
| `src/components/EmptyState.vue` | **新建** — 居中空数据占位（64px 图标 + 标题 + 描述 + 可选操作按钮） |
| `src/components/SkeletonCard.vue` | **新建** — Shimmer 骨架屏（CSS from UIUX.md §4.5） |

**AppSidebar 行为规范**:
- 桌面端（≥1024px）：默认展开，Logo 区点击折叠为图标模式
- 平板端（768-1023px）：默认折叠图标模式
- 手机端（<768px）：隐藏，顶栏汉堡菜单打开全屏抽屉
- 展开/折叠 width 过渡 200ms cubic-bezier(0.4,0,0.2,1)

### 1.5 仪表盘重做

**类型**: 全栈

**后端修改**:

| 文件 | 操作 |
|------|------|
| `comobot/api/routes/dashboard.py` | 修改 — 扩展响应字段：`message_trend`（7 天每日消息数数组）、`running_workflows`（名称+状态+日均运行数列表）、`cron_warnings`（名称+上次状态+上次运行时间列表）。新增 SQL 聚合 messages.created_at 分组查询 |

**前端修改**:

| 文件 | 操作 |
|------|------|
| `src/components/StatCard.vue` | **新建** — 统计卡片：顶部（16px 图标 + 13px 灰色标签）、中间（32px 大数字）、底部（趋势箭头 + 百分比） |
| `src/components/SparklineChart.vue` | **新建** — Echarts 极简折线图封装（无坐标轴文字，tooltip hover 显示） |
| `src/views/DashboardView.vue` | 重写 — PageLayout 包裹，6 张 StatCard（grid-cols-3/2/1 响应式），趋势图区域（消息量 + Token 消耗），快捷状态墙（运行工作流 + Cron 警告双列） |

### 1.6 全部已有 View 接入 PageLayout

**类型**: 前端

| 文件 | 操作 |
|------|------|
| `src/views/WorkflowsView.vue` | 修改 — 移除内联 Sidebar，用 PageLayout 包裹 |
| `src/views/WorkflowEditorView.vue` | 修改 — 不使用 PageLayout（全屏画布），仅替换硬编码颜色为 CSS 变量 |
| `src/views/ChannelsView.vue` | 修改 — PageLayout + EmptyState 替换 "Coming soon" |
| `src/views/ProvidersView.vue` | 同上 |
| `src/views/SessionsView.vue` | 同上 |
| `src/views/CronView.vue` | 同上 |
| `src/views/LogsView.vue` | 同上 |
| `src/views/SettingsView.vue` | 同上 |

### 1.7 路由切换动效

**类型**: 前端

| 文件 | 操作 |
|------|------|
| `src/App.vue` | 修改 — `<router-view>` 包裹 `<Transition name="fade">`，opacity 0→1，200ms ease-enter |

---

## Phase 2 (P1): 核心配置 — 渠道 + 模型 + 登录

### 2.1 后端 — 渠道配置 CRUD

**类型**: 后端

| 文件 | 操作 |
|------|------|
| `comobot/api/routes/channels.py` | 修改 — 增加以下端点 |

**新增端点**:
| 端点 | 说明 |
|------|------|
| `GET /api/channels` 增强 | 返回字段扩展：`configured`(bool), `status`(online/offline), `last_activity_at` |
| `GET /api/channels/{type}/config` | 渠道配置详情（Token 脱敏显示前缀） |
| `PUT /api/channels/{type}/config` | 更新渠道配置（写 config.json + vault 加密存储敏感字段） |
| `POST /api/channels/{type}/test` | 渠道连通性测试（如 Telegram `getMe`），返回测试日志 |

**依赖**: 读取 `comobot/config/schema.py` 各渠道字段定义，调用 `comobot/config/loader.py` 保存配置

### 2.2 前端 — 渠道管理页

**类型**: 前端

| 文件 | 操作 |
|------|------|
| `src/components/SecretInput.vue` | **新建** — `type="password"` 输入框 + 右侧 👁 切换明文 |
| `src/components/CopyButton.vue` | **新建** — 点击复制到剪贴板，图标变 ✓（1.5s 恢复） |
| `src/components/ChannelCard.vue` | **新建** — 渠道图标(40px) + 名称 + 呼吸灯状态 + 模式/白名单摘要 + 操作按钮 |
| `src/components/ChannelConfigDrawer.vue` | **新建** — 右侧 480px 抽屉：渠道特有字段动态表单 + SecretInput + Tag 输入器（白名单）+ 高级设置折叠 + Test Connection + Save |
| `src/views/ChannelsView.vue` | 实现 — 3 列卡片网格，未配置渠道虚线边框，"Configure New Channel" 按钮 |

### 2.3 后端 — 模型提供者增强

**类型**: 后端

| 文件 | 操作 |
|------|------|
| `comobot/api/routes/providers.py` | 修改 — 增强/新增端点 |

**端点变更**:
| 端点 | 说明 |
|------|------|
| `GET /api/providers` 增强 | 返回扩展：每个 provider 的 Key 数量、轮询策略、上次使用时间、今日请求数 |
| `POST /api/providers/{provider}/test` 增强 | 真实 LLM API 调用（trivial prompt），返回 `{status, latency_ms, model}` |
| `GET /api/providers/{provider}/keys` | 列出某 provider 所有 Key（脱敏显示前缀） |

### 2.4 前端 — 模型管理页

**类型**: 前端

| 文件 | 操作 |
|------|------|
| `src/components/ProviderCard.vue` | **新建** — Logo/图标 + 名称 + Key 数量 · Active 状态 + 支持模型标签 + 轮询策略 + 使用统计 + 操作按钮 |
| `src/components/ProviderDrawer.vue` | **新建** — 480px 抽屉：Provider 类型卡片选择器 + 多 Key 管理（添加/删除）+ 轮询策略下拉 + API Base URL + 默认模型 + Test Connection（延迟显示） |
| `src/views/ProvidersView.vue` | 实现 — 卡片列表 + "Add Provider" 按钮 |

### 2.5 登录页重设计

**类型**: 前端

| 文件 | 操作 |
|------|------|
| `src/views/LoginView.vue` | 重写 — 全屏居中 400px 卡片（`--surface` 背景 + `--border` 边框 + 20px 圆角 + `--shadow-lg`），Logo + "comobot" + 副标题居中，输入框 focus glow（`box-shadow: 0 0 0 3px rgba(255,255,255,0.1)`），错误提示内联显示（红色文字 + 红色边框），登录成功按钮短暂变绿→路由跳转 |

### 2.6 初始化向导增强

**类型**: 前端

| 文件 | 操作 |
|------|------|
| `src/views/SetupView.vue` | 修改 — 顶部步骤进度条（32px 圆圈 + 连线，颜色状态），步骤滑动过渡（translateX 300ms），Step 1 密码强度指示条（4 段），Step 2 Provider 卡片 Radio Group，Step 3 增加 Webhook 模式字段 + Secret Token + 白名单 Tag 输入，Step 4 动画打勾（stroke-dashoffset 300ms）|

---

## Phase 3 (P2): 内容页 — 工作流列表 + 会话 + 日志

### 3.1 工作流列表卡片化

**类型**: 全栈

**后端修改**:
| 文件 | 操作 |
|------|------|
| `comobot/api/routes/workflows.py` | 修改 — `GET /api/workflows` 列表接口 JOIN workflow_runs 返回 `last_run_at`, `total_runs`；新增 `POST /api/workflows/{id}/duplicate`；手动执行接口已有 |

**前端修改**:
| 文件 | 操作 |
|------|------|
| `src/components/WorkflowCard.vue` | **新建** — 名称 + 状态开关下拉 + 描述(2行截断) + 触发类型 Badge + 模板标签 + 执行统计 + 操作按钮(Edit/Duplicate/Run Now) |
| `src/views/WorkflowsView.vue` | 重写 — 卡片网格替代表格，新建按钮→模式选择 Modal（模板/高级），模板模式使用 640px 抽屉 |

### 3.2 后端 — 会话接口增强

**类型**: 后端

| 文件 | 操作 |
|------|------|
| `comobot/api/routes/sessions.py` | 修改 — 增强/新增端点 |

**端点变更**:
| 端点 | 说明 |
|------|------|
| `GET /api/sessions` 增强 | 返回扩展：`message_count`, `channel`(从 session_key 解析), `last_message_preview`；支持 `?channel=` 和 `?search=` 过滤 |
| `GET /api/sessions/{session_key}` | **新增** — 单会话元数据 |
| `GET /api/sessions/{key}/messages` 增强 | 支持 `?offset=&limit=` 分页 |

### 3.3 会话查看页

**类型**: 前端

| 文件 | 操作 |
|------|------|
| `src/components/ChatBubble.vue` | **新建** — 用户消息右对齐（`--surface` 背景），助手消息左对齐（`--bg-muted` 背景），工具调用折叠展示（点击展开 JSON） |
| `src/components/MarkdownRenderer.vue` | **新建** — `marked` 解析 + `highlight.js` 代码高亮（主题跟随深/浅色），代码块 CopyButton，表格横向滚动，链接 `target="_blank"` |
| `src/views/SessionsView.vue` | 实现 — 双栏布局：左栏 300px 会话列表（头像/渠道图标 + 名称 + 消息数 + 相对时间），右栏对话气泡流 + 记忆 Badge |
| `src/router/index.ts` | 修改 — 添加 `/sessions/:key` 路由 |

### 3.4 后端 — WebSocket 实时推送

**类型**: 后端

| 文件 | 操作 |
|------|------|
| `comobot/api/routes/ws.py` | **新建** — WebSocket 端点 |
| `comobot/api/app.py` | 修改 — 注册 ws router |
| `comobot/db/audit.py` | 修改 — AuditLogger 增加 asyncio.Queue 供 WS 消费 |

**WebSocket 端点**:
| 端点 | 说明 |
|------|------|
| `WS /ws/logs?token=<jwt>` | 实时日志流。连接时发送最近 50 条，后续增量推送。格式同 `GET /api/logs` 单条 |
| `WS /ws/status?token=<jwt>` | Agent/渠道状态推送。`{type: "agent_status", data: {online, active_sessions}}` 和 `{type: "channel_status", data: {channel, status}}` |

### 3.5 日志监控页

**类型**: 前端

| 文件 | 操作 |
|------|------|
| `src/composables/useWebSocket.ts` | **新建** — 可复用 WS composable：自动重连、连接状态 ref、类型化消息处理 |
| `src/views/LogsView.vue` | 实现 — 终端风格（monospace JetBrains Mono，背景 `#060608`，行高 28px），过滤工具栏（Level/Module/关键词/时间），WS 连接状态指示，新日志底部插入 + 自动滚动（手动上滚暂停 + "↓新消息" Badge），Error 行点击展开详情抽屉 |

---

## Phase 4 (P3): 高级功能 — 编辑器 + 定时任务 + 设置

### 4.1 工作流编辑器 UX 优化

**类型**: 前端

| 文件 | 操作 |
|------|------|
| `src/views/WorkflowEditorView.vue` | 修改 — 左侧节点面板 180px（可拖拽卡片，色彩编码：蓝=Trigger/紫=LLM/橙=Tool/黄=Condition/绿=Response/灰=Delay/粉=SubAgent），节点样式（圆角矩形 + 彩色标题栏），画布背景点阵，右侧配置面板 300ms 滑入，底部可折叠测试面板（输入模拟消息 + Run + 逐节点执行日志），画布工具栏（缩放±/Fit View/全屏） |

### 4.2 后端 — 定时任务 CRUD

**类型**: 后端

| 文件 | 操作 |
|------|------|
| `comobot/api/routes/cron.py` | 修改 — 新增端点 |

**新增端点**:
| 端点 | 说明 |
|------|------|
| `POST /api/cron` | 创建定时任务（name, schedule, payload, enabled） |
| `PUT /api/cron/{id}` | 更新定时任务字段 |
| `POST /api/cron/{id}/run` | 手动触发执行 |
| `PUT /api/cron/{id}/toggle` | 启停切换 |

### 4.3 定时任务页

**类型**: 前端

| 文件 | 操作 |
|------|------|
| `src/components/CronExpressionInput.vue` | **新建** — Cron 表达式输入 + 实时人类可读解析（cronstrue）+ 下次运行倒计时显示 |
| `src/components/DataTable.vue` | **新建** — NDataTable 增强封装：Loading 显示骨架屏、空数据显示 EmptyState、操作列统一 text 按钮样式 |
| `src/components/ConfirmDialog.vue` | **新建** — 危险操作确认弹窗：红色样式，可选 "输入 DELETE 确认" 模式 |
| `src/views/CronView.vue` | 实现 — 表格列（状态点+文字/名称+描述/Cron 表达式+可读解析/下次运行倒计时/上次执行状态/操作按钮），"New Cron Job" 弹窗/抽屉 |

### 4.4 后端 — 设置接口扩展

**类型**: 后端

| 文件 | 操作 |
|------|------|
| `comobot/api/routes/settings.py` | 修改 — 新增端点 |

**新增端点**:
| 端点 | 说明 |
|------|------|
| `GET /api/settings` 增强 | 返回完整设置：version, agent 配置, gateway 配置 |
| `GET/PUT /api/settings/agent` | Agent 默认配置（model, temperature, max_tokens 等）读写 |
| `GET/PUT /api/settings/soul` | SOUL.md 内容读写 |
| `GET/PUT /api/settings/user` | USER.md 内容读写 |
| `GET /api/settings/memory` | MEMORY.md 只读查看 |
| `DELETE /api/settings/memory` | 清空 MEMORY.md（危险操作） |

### 4.5 系统设置页

**类型**: 前端

| 文件 | 操作 |
|------|------|
| `src/views/SettingsView.vue` | 实现 — 左侧分类 Tab（通用/Agent/安全/账户）+ 右侧内容区 |

**各分类内容**:
- **通用**: 主题切换（Light/Dark/System）、语言、时区
- **Agent**: SOUL.md 编辑器（textarea + markdown 预览）、USER.md 编辑器、MEMORY.md 只读查看 + "清空记忆"危险按钮、并发控制
- **安全**: 修改密码表单（旧密码+新密码+确认）、JWT 有效期
- **账户**: 修改用户名
- **危险区域**: 底部红色边框卡片，"重置配置"/"清空数据" + ConfirmDialog

---

## Phase 5: 打磨 — 响应式 + 无障碍 + 实时状态

### 5.1 响应式断点适配

| 断点 | 侧边栏 | 内容区 padding | 卡片列数 |
|------|--------|---------------|---------|
| < 768px | 抽屉（汉堡菜单） | 16px | 1 列 |
| 768-1023px | 折叠图标（60px） | 24px | 2 列 |
| ≥ 1024px | 展开（220px） | 40px | 3 列 |

- WorkflowEditorView: 手机端显示"请在桌面端访问工作流编辑器"
- SessionsView: 手机端双栏堆叠为单栏

### 5.2 无障碍（WCAG 2.1 AA）

- 所有图标按钮添加 `aria-label`
- 全局 `:focus-visible` ring: `2px solid var(--text-primary), offset 2px`
- 装饰图标 `aria-hidden="true"`
- Tab 键顺序符合视觉从上到下、从左到右
- 深色模式文字对比度 ≥ 4.5:1

### 5.3 WebSocket 实时状态集成

- `AppSidebar` → `ws/status` → Agent 在线呼吸灯（绿色 opacity 1→0.3→1，2s 循环）
- `DashboardView` → 实时统计数字更新
- `ChannelsView` → 渠道在线/离线状态实时推送

### 5.4 微交互打磨

| 场景 | 动效规格 |
|------|----------|
| 按钮 Hover | 背景过渡 + translateY(-1px)，150ms ease-default |
| 按钮 Active | translateY(0) + 压暗背景，80ms ease-exit |
| 卡片 Hover | border opacity 0.08→0.16 + 阴影增强，200ms |
| 侧边栏折叠 | width 过渡，200ms cubic-bezier(0.4,0,0.2,1) |
| 抽屉滑出 | translateX(100%)→0 + 遮罩 fadeIn，300ms ease-enter |
| Modal 出现 | scale(0.96)+opacity(0)→scale(1)+opacity(1)，200ms |
| Toast 通知 | 右上角 translateX(120%)→0，300ms ease-enter |
| Loading | 骨架屏 shimmer 扫描，1.5s linear 循环 |

### 5.5 骨架屏加载态

所有数据加载页面使用 SkeletonCard 替代空白/spinner:
Dashboard, Channels, Providers, Sessions, Logs, Cron

---

## 文件清单汇总

### 新建前端文件（~24 个）

| 文件路径 | 说明 |
|----------|------|
| `src/assets/variables.css` | CSS Design Token |
| `src/stores/theme.ts` | 主题 Pinia store |
| `src/theme/index.ts` | Naive UI 主题覆盖对象 |
| `src/composables/useWebSocket.ts` | WebSocket composable |
| `src/components/AppSidebar.vue` | 可折叠侧边栏 |
| `src/components/PageLayout.vue` | 统一页面布局 |
| `src/components/StatusBadge.vue` | 状态徽章（呼吸灯） |
| `src/components/EmptyState.vue` | 空数据占位 |
| `src/components/SkeletonCard.vue` | 骨架屏 |
| `src/components/StatCard.vue` | 仪表盘统计卡片 |
| `src/components/SparklineChart.vue` | Echarts 趋势折线图 |
| `src/components/SecretInput.vue` | 密码/Token 输入框 |
| `src/components/CopyButton.vue` | 点击复制按钮 |
| `src/components/ChannelCard.vue` | 渠道卡片 |
| `src/components/ChannelConfigDrawer.vue` | 渠道配置抽屉 |
| `src/components/ProviderCard.vue` | Provider 卡片 |
| `src/components/ProviderDrawer.vue` | Provider 配置抽屉 |
| `src/components/WorkflowCard.vue` | 工作流卡片 |
| `src/components/ChatBubble.vue` | 对话气泡 |
| `src/components/MarkdownRenderer.vue` | Markdown 渲染器 |
| `src/components/CronExpressionInput.vue` | Cron 表达式输入 |
| `src/components/DataTable.vue` | 增强数据表 |
| `src/components/ConfirmDialog.vue` | 危险操作确认弹窗 |

### 新建后端文件（1 个）

| 文件路径 | 说明 |
|----------|------|
| `comobot/api/routes/ws.py` | WebSocket 端点（/ws/logs, /ws/status） |

### 修改后端文件（9 个）

| 文件路径 | 修改内容 |
|----------|----------|
| `comobot/api/app.py` | 注册 ws router |
| `comobot/api/routes/dashboard.py` | 趋势数据 + 运行工作流 + Cron 警告 |
| `comobot/api/routes/channels.py` | 配置 CRUD + 连通性测试 |
| `comobot/api/routes/providers.py` | 增强列表 + 真实 LLM 测试 + Key 列表 |
| `comobot/api/routes/sessions.py` | 增强列表 + 单会话详情 + 分页 |
| `comobot/api/routes/workflows.py` | 运行统计 + duplicate 端点 |
| `comobot/api/routes/cron.py` | 完整 CRUD（创建/更新/触发/启停） |
| `comobot/api/routes/settings.py` | Agent 配置 + 文件读写 + 记忆管理 |
| `comobot/db/audit.py` | asyncio.Queue 供 WS 订阅 |

### 修改前端文件（~13 个）

| 文件路径 | 修改内容 |
|----------|----------|
| `web/package.json` | 新增依赖 |
| `web/index.html` | Inter 字体 + title |
| `src/main.ts` | 导入 variables.css |
| `src/style.css` | CSS 变量替换 |
| `src/App.vue` | 双主题 + Transition |
| `src/router/index.ts` | 添加 /sessions/:key 路由 |
| `src/views/LoginView.vue` | 完全重设计 |
| `src/views/SetupView.vue` | 步骤增强 |
| `src/views/DashboardView.vue` | 完全重写 |
| `src/views/WorkflowsView.vue` | 卡片化重写 |
| `src/views/WorkflowEditorView.vue` | UX 优化 |
| 6 个 stub View | 完整实现 |

---

## 验证方式

1. **前端开发**: `cd web && npm run dev` → 逐页验证 UI 效果、主题切换、响应式
2. **后端测试**: `.venv/bin/pytest tests/ -v` → 确保已有 138 个测试不被破坏
3. **全栈联调**: `.venv/bin/comobot gateway` → 访问 `http://localhost:18790`，端到端测试
4. **代码质量**: `.venv/bin/ruff check .` + `cd web && npx vue-tsc --noEmit`
5. **WebSocket**: 浏览器 DevTools → Network → WS tab 验证 `/ws/logs` 和 `/ws/status`

---

## 各板块完成进度

| 板块 | 子项 | 状态 |
|------|------|------|
| **Phase 1: 基础设施** | | |
| | 1.1 安装前端依赖 | ✅ 已完成 |
| | 1.2 CSS 变量系统 | ✅ 已完成 |
| | 1.3 主题系统（Store + Overrides + App.vue） | ✅ 已完成 |
| | 1.4 通用组件（Sidebar / PageLayout / StatusBadge / EmptyState / Skeleton） | ✅ 已完成 |
| | 1.5 仪表盘重做（后端趋势数据 + StatCard + Sparkline + View 重写） | ✅ 已完成 |
| | 1.6 全部 View 接入 PageLayout | ✅ 已完成 |
| | 1.7 路由切换动效 | ✅ 已完成 |
| **Phase 2: 核心配置** | | |
| | 2.1 后端 — 渠道配置 CRUD | ✅ 已完成 |
| | 2.2 前端 — 渠道管理页（ChannelCard + ConfigDrawer + SecretInput + CopyButton） | ✅ 已完成 |
| | 2.3 后端 — 模型提供者增强 | ✅ 已完成 |
| | 2.4 前端 — 模型管理页（ProviderCard + ProviderDrawer） | ✅ 已完成 |
| | 2.5 登录页重设计 | ✅ 已完成 |
| | 2.6 初始化向导增强 | ✅ 已完成 |
| **Phase 3: 内容页** | | |
| | 3.1 工作流列表卡片化（含后端运行统计） | ✅ 已完成 |
| | 3.2 后端 — 会话接口增强 | ✅ 已完成 |
| | 3.3 会话查看页（ChatBubble + MarkdownRenderer） | ✅ 已完成 |
| | 3.4 后端 — WebSocket 实时推送（ws.py） | ✅ 已完成 |
| | 3.5 日志监控页（useWebSocket + 终端风格） | ✅ 已完成 |
| **Phase 4: 高级功能** | | |
| | 4.1 工作流编辑器 UX 优化 | ✅ 已完成 |
| | 4.2 后端 — 定时任务 CRUD | ✅ 已完成 |
| | 4.3 定时任务页（CronExpressionInput + DataTable + ConfirmDialog） | ✅ 已完成 |
| | 4.4 后端 — 设置接口扩展 | ✅ 已完成 |
| | 4.5 系统设置页 | ✅ 已完成 |
| **Phase 5: 打磨** | | |
| | 5.1 响应式断点适配 | ✅ 已完成 |
| | 5.2 无障碍（WCAG 2.1 AA） | ✅ 已完成 |
| | 5.3 WebSocket 实时状态集成 | ✅ 已完成 |
| | 5.4 微交互打磨 | ✅ 已完成 |
| | 5.5 骨架屏加载态 | ✅ 已完成 |
