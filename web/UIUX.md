# Comobot 前端 UI/UX 需求文档

> 版本: 1.0 | 日期: 2026-03-06 | 状态: 设计规范
>
> **产品定位**：轻量级、开箱即用的智能体自动化工作流平台。通过极简交互承载复杂的大模型个性化能力，让用户构建、沉淀并最终拥有专属的数字认知模型。
>
> **设计标杆**：Apple 官网排版 × Manus.ai 交互 × ChatGPT 信息流 → 无界面沉浸感 + 极简科技风。

---

## 目录

1. [技术基座](#1-技术基座)
2. [设计系统](#2-设计系统)
3. [布局骨架](#3-布局骨架)
4. [微交互与动效规范](#4-微交互与动效规范)
5. [双主题系统](#5-双主题系统)
6. [页面规范：登录页](#6-页面规范登录页)
7. [页面规范：初始化向导](#7-页面规范初始化向导)
8. [页面规范：仪表盘](#8-页面规范仪表盘)
9. [页面规范：Createflow 工作流编排](#9-页面规范createflow-工作流编排)
10. [页面规范：渠道管理](#10-页面规范渠道管理)
11. [页面规范：模型管理](#11-页面规范模型管理)
12. [页面规范：会话查看](#12-页面规范会话查看)
13. [页面规范：定时任务](#13-页面规范定时任务)
14. [页面规范：日志监控](#14-页面规范日志监控)
15. [页面规范：系统设置](#15-页面规范系统设置)
16. [通用组件库](#16-通用组件库)
17. [响应式与自适应](#17-响应式与自适应)
18. [可访问性](#18-可访问性)

---

## 1. 技术基座

### 1.1 现有技术栈

| 层级 | 选型 | 用途 |
|------|------|------|
| 框架 | Vue 3 + Vite 7 | 响应式 SPA |
| 组件库 | Naive UI 2.43+ | 基础 UI 组件（需大幅扩展主题覆盖） |
| 状态管理 | Pinia 3 | 全局状态（auth、theme、dashboard） |
| 路由 | Vue Router 4 | 客户端路由 + 鉴权守卫 |
| 流程图 | @vue-flow/core | Workflow 编辑器节点画布 |
| HTTP | axios 1.x | API 请求封装 |
| 语言 | TypeScript 5.x | 全量类型检查 |

### 1.2 待补充依赖

| 包名 | 用途 | 优先级 |
|------|------|--------|
| `three` + `@types/three` | ComoBrain WebGL 球体渲染 | 中期 |
| `@unovis/vue` 或 `echarts` | Sparklines / 趋势图表 | 高 |
| `highlight.js` 或 `shiki` | 代码块语法高亮 | 高 |
| `marked` 或 `markdown-it` | Markdown 渲染 | 高 |
| `date-fns` | 日期格式化 | 高 |
| `@vueuse/core` | 响应式工具集（useStorage、useDark 等） | 高 |

### 1.3 路由结构（完整）

```
/login              → 登录页
/setup              → 初始化向导（首次启动）
/                   → 仪表盘 Dashboard
/workflows          → Createflow — 工作流列表
/workflows/new      → 工作流编辑器（新建）
/workflows/:id/edit → 工作流编辑器（编辑）
/channels           → 渠道管理
/providers          → 模型管理
/sessions           → 会话查看
/sessions/:key      → 单个会话详情
/cron               → 定时任务
/logs               → 日志监控
/settings           → 系统设置
```

---

## 2. 设计系统

### 2.1 色彩体系

#### 2.1.1 浅色模式（Light Mode）

```
背景层级：
  --bg-base:       #FFFFFF   主工作区背景
  --bg-subtle:     #F8F8F8   侧边栏/次级区域
  --bg-muted:      #F0F0F0   悬浮/禁用态

卡片与边框：
  --surface:       #FFFFFF   卡片背景
  --border:        #E8E8E8   边框（0.5px 极细）
  --shadow:        rgba(0, 0, 0, 0.06)  卡片投影

文字层级：
  --text-primary:  #0A0A0A   主文字
  --text-secondary:#6B6B6B   次要文字
  --text-muted:    #A0A0A0   占位文字

强调色（点缀，不泛滥）：
  --accent:        #0A0A0A   主操作按钮
  --accent-green:  #16A34A   成功 / 在线
  --accent-yellow: #CA8A04   警告 / 暂停
  --accent-red:    #DC2626   错误 / 离线
  --accent-blue:   #2563EB   信息 / 链接
```

#### 2.1.2 深色模式（Dark Mode）— 当前默认

```
背景层级：
  --bg-base:       #09090B   主工作区（科技感深黑）
  --bg-subtle:     #0D0D10   侧边栏
  --bg-muted:      #141418   悬浮/禁用态

卡片与边框：
  --surface:       #111115   卡片背景
  --surface-glass: rgba(17,17,21,0.7)  毛玻璃效果（Backdrop blur 12px）
  --border:        rgba(255,255,255,0.08)  极细白色描边
  --shadow:        rgba(0, 0, 0, 0.4)  卡片投影

文字层级：
  --text-primary:  #FAFAFA   主文字
  --text-secondary:#A1A1AA   次要文字
  --text-muted:    #52525B   占位文字

强调色（同浅色，亮度调高）：
  --accent:        #FFFFFF   主操作
  --accent-green:  #22C55E   成功 / 在线（呼吸灯用）
  --accent-yellow: #EAB308   警告
  --accent-red:    #EF4444   错误
  --accent-blue:   #3B82F6   信息
```

#### 2.1.3 Naive UI 主题覆盖（完整版）

```typescript
// src/theme/index.ts
export const darkThemeOverrides = {
  common: {
    primaryColor: '#FAFAFA',
    primaryColorHover: '#E4E4E7',
    primaryColorPressed: '#A1A1AA',
    primaryColorSuppl: '#FAFAFA',
    bodyColor: '#09090B',
    cardColor: '#111115',
    modalColor: '#111115',
    popoverColor: '#1C1C22',
    tableColor: '#111115',
    tableColorHover: '#1C1C22',
    inputColor: '#1C1C22',
    inputColorDisabled: '#141418',
    textColorBase: '#FAFAFA',
    textColor1: '#FAFAFA',
    textColor2: '#A1A1AA',
    textColor3: '#52525B',
    borderColor: 'rgba(255,255,255,0.08)',
    borderRadius: '10px',
    borderRadiusSmall: '6px',
    fontFamily: '"Inter", "PingFang SC", -apple-system, sans-serif',
    fontFamilyMono: '"JetBrains Mono", "Fira Code", monospace',
  },
  Button: {
    colorPrimary: '#FAFAFA',
    colorHoverPrimary: '#E4E4E7',
    textColorPrimary: '#09090B',
    borderRadiusMedium: '8px',
  },
  Menu: {
    itemColorActive: 'rgba(255,255,255,0.06)',
    itemColorHover: 'rgba(255,255,255,0.04)',
    itemTextColorActive: '#FAFAFA',
    itemIconColorActive: '#FAFAFA',
    borderRadius: '8px',
  },
  Layout: {
    siderColor: '#0D0D10',
    headerColor: '#0D0D10',
  },
}

export const lightThemeOverrides = {
  common: {
    primaryColor: '#0A0A0A',
    primaryColorHover: '#3F3F46',
    bodyColor: '#FFFFFF',
    cardColor: '#FFFFFF',
    modalColor: '#FFFFFF',
    inputColor: '#F4F4F5',
    textColorBase: '#0A0A0A',
    borderColor: '#E8E8E8',
    borderRadius: '10px',
    fontFamily: '"Inter", "PingFang SC", -apple-system, sans-serif',
  },
}
```

### 2.2 字体排版

#### 字体引入

```html
<!-- index.html -->
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet" />
```

#### 字号层级（Type Scale）

```css
--text-xs:   11px / 1.5  /* Badge、元数据 */
--text-sm:   13px / 1.5  /* 次要文字、表格单元 */
--text-base: 14px / 1.6  /* 正文、表单标签 */
--text-md:   16px / 1.5  /* 小标题 */
--text-lg:   20px / 1.4  /* 页面标题 */
--text-xl:   28px / 1.3  /* 大数字统计 */
--text-2xl:  40px / 1.2  /* Hero 数字 */
```

#### 字重规则

- **300 Light**：副标题、描述文案（提升轻盈感）
- **400 Regular**：正文、表单内容
- **500 Medium**：表格列头、菜单项、按钮
- **600 Semibold**：页面标题、卡片强调数字

### 2.3 间距系统（8px 基准网格）

```
--space-1:  4px
--space-2:  8px
--space-3:  12px
--space-4:  16px
--space-5:  20px
--space-6:  24px
--space-8:  32px
--space-10: 40px
--space-12: 48px
--space-16: 64px
```

- 卡片内边距：`24px`
- 页面内容区内边距：`40px`（PC） / `20px`（移动端）
- 区块间距：`24px ~ 40px`（根据视觉层级调整）
- 侧边栏宽度：`220px`（展开）/ `60px`（收起）

### 2.4 圆角与投影

```css
/* 圆角（越小越精致，避免过度圆润） */
--radius-sm:  6px   /* 标签、Badge */
--radius-md:  10px  /* 输入框、按钮 */
--radius-lg:  14px  /* 卡片 */
--radius-xl:  20px  /* 弹出层、抽屉 */

/* 深色模式投影（科技感，少用扩散，多用 inset 描边） */
--shadow-sm: 0 1px 3px rgba(0,0,0,0.3);
--shadow-md: 0 4px 16px rgba(0,0,0,0.4);
--shadow-lg: 0 8px 32px rgba(0,0,0,0.5);
```

---

## 3. 布局骨架

### 3.1 主应用框架

```
┌────────────────────────────────────────────────────────┐
│  顶栏 TopBar（可选，移动端/折叠时显示）  高度 56px       │
├──────────┬─────────────────────────────────────────────┤
│          │                                             │
│ 侧边栏   │  主内容区                                   │
│ Sidebar  │  Content Area                               │
│ 220px    │  flex: 1                                    │
│          │  padding: 40px                              │
│          │                                             │
│          │  ┌─────────────────────────┐               │
│          │  │  页面标题区（28-40px）   │               │
│          │  │  page-header             │               │
│          │  └─────────────────────────┘               │
│          │                                             │
│          │  ┌─────────────────────────┐               │
│          │  │  页面内容               │               │
│          │  │  page-body               │               │
│          │  └─────────────────────────┘               │
│          │                                             │
└──────────┴─────────────────────────────────────────────┘
```

### 3.2 侧边栏（Sidebar）详细规范

```
┌──────────────────────────┐
│  ● comobot              │  ← Logo + 产品名，字重 600，14px
│    副标题/版本号          │  ← 灰色，12px，可选
├──────────────────────────┤
│  ● Dashboard            │  ← 激活项：左侧 2px 白色竖条 + 微弱背景色
│  ○ Createflow           │  ← 普通项：hover 时背景 rgba(255,255,255,0.04)
│  ○ Channels             │
│  ○ Providers            │
│  ─────────────          │  ← 分隔线（可将菜单分组）
│  ○ Sessions             │
│  ○ Cron Jobs            │
│  ○ Logs                 │
│  ○ Settings             │
├──────────────────────────┤
│  [系统状态指示器]         │  ← 底部：Agent 在线状态（绿点呼吸灯）
│  ○ Logout               │  ← 退出按钮（text style，hover 红色）
└──────────────────────────┘
```

**行为**：
- 桌面端（≥1024px）：默认展开，可点击 Logo 区折叠为图标模式（60px）。折叠时 tooltip 显示菜单名。
- 平板端（768-1023px）：默认折叠图标模式，点击汉堡菜单展开为浮层 overlay。
- 移动端（<768px）：侧边栏收起，顶栏显示汉堡菜单，点击展开全屏抽屉。

**动效**：侧边栏展开/收起宽度过渡 `width: 200ms cubic-bezier(0.4,0,0.2,1)`，内容区 `margin-left` 同步过渡。

### 3.3 页面标题区规范

每个内页统一采用：

```html
<div class="page-header">
  <div class="page-header-left">
    <h1 class="page-title">{{ title }}</h1>
    <p class="page-desc">{{ description }}</p>  <!-- 可选 -->
  </div>
  <div class="page-header-right">
    <!-- 主操作按钮，如「+ 新建」 -->
  </div>
</div>
```

```css
.page-title { font-size: 20px; font-weight: 600; color: var(--text-primary); margin: 0; }
.page-desc  { font-size: 13px; color: var(--text-secondary); margin: 4px 0 0; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 32px; }
```

---

## 4. 微交互与动效规范

### 4.1 核心原则

- **拒绝闪烁**：所有状态切换必须有过渡，最小时长 150ms。
- **克制用动效**：仅在 `hover`、`enter/leave`、`loading` 三种场景使用，不做装饰性动效。
- **硬件加速**：优先用 `transform` 和 `opacity` 驱动动效，避免触发重排（layout）。

### 4.2 统一 Easing 曲线

```css
--ease-default:   cubic-bezier(0.4, 0, 0.2, 1);   /* 大多数状态切换 */
--ease-enter:     cubic-bezier(0, 0, 0.2, 1);      /* 元素进入（减速入场） */
--ease-exit:      cubic-bezier(0.4, 0, 1, 1);      /* 元素离开（加速退场） */
--ease-bounce:    cubic-bezier(0.34, 1.56, 0.64, 1); /* 轻弹（慎用） */
```

### 4.3 时长规范

```
50ms  — 即时反馈（颜色/背景 hover）
150ms — 小元素切换（按钮 active、开关切换）
200ms — 侧边栏折叠、卡片展开
300ms — 抽屉滑入/滑出、模态框出现
400ms — 页面切换淡入淡出
```

### 4.4 具体动效清单

| 场景 | 动效 | 规格 |
|------|------|------|
| 按钮 Hover | 背景色过渡 + 轻微上移（translateY -1px） | 150ms ease-default |
| 按钮 Active | 恢复原位（translateY 0） + 压暗背景 | 80ms ease-exit |
| 卡片 Hover | 边框亮度提升（opacity 0.08→0.16） + 微弱阴影增强 | 200ms ease-default |
| 侧边栏折叠 | width 过渡，内部图标/文字同步 fade | 200ms ease-default |
| 抽屉滑出 | 从右侧 translateX(100%) → translateX(0) + 背景遮罩 fadeIn | 300ms ease-enter |
| 模态框出现 | scale(0.96) + opacity(0) → scale(1) + opacity(1) | 200ms ease-enter |
| 页面路由切换 | opacity 0→1（keep-alive 保留滚动） | 200ms ease-enter |
| Loading 状态 | 骨架屏 shimmer（从左到右渐变扫描） | 1.5s linear 循环 |
| 呼吸灯（在线状态） | opacity 1→0.3→1 | 2s ease-in-out 无限 |
| Toast 通知 | 从右上角 translateX(120%) → translateX(0) | 300ms ease-enter |

### 4.5 骨架屏规范

数据加载期间替代空白，减少视觉跳动：

```css
.skeleton {
  background: linear-gradient(
    90deg,
    var(--bg-muted) 25%,
    rgba(255,255,255,0.04) 50%,
    var(--bg-muted) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite linear;
}
@keyframes shimmer {
  from { background-position: 200% 0; }
  to   { background-position: -200% 0; }
}
```

---

## 5. 双主题系统

### 5.1 主题切换实现

```typescript
// src/stores/theme.ts
import { defineStore } from 'pinia'
import { usePreferredDark, useStorage } from '@vueuse/core'

export const useThemeStore = defineStore('theme', () => {
  const prefersDark = usePreferredDark()
  const userPref = useStorage<'dark' | 'light' | 'system'>('comobot-theme', 'system')

  const isDark = computed(() => {
    if (userPref.value === 'system') return prefersDark.value
    return userPref.value === 'dark'
  })

  function toggle() {
    userPref.value = isDark.value ? 'light' : 'dark'
  }
  return { isDark, userPref, toggle }
})
```

### 5.2 主题切换 UI

- 侧边栏底部放置主题切换图标按钮（太阳/月亮 icon）。
- 切换动画：页面整体 `opacity` 短暂 fade（100ms）后切换 Naive UI theme。
- 系统跟随时，偏好设置中标注"跟随系统"。

---

## 6. 页面规范：登录页

### 6.1 布局

```
全屏居中（flex + align-items: center）
背景：--bg-base（深色：#09090B）
    + 可选：极其微弱的噪点纹理或极低对比度的网格线（opacity 0.02）

卡片宽度：400px（移动端：92vw）
卡片：--surface 背景 + border var(--border) + border-radius 20px
      box-shadow: 0 0 0 1px var(--border), var(--shadow-lg)
```

### 6.2 内容组成

```
┌──────────────────────────────────────┐
│                                      │
│   ◉  comobot                        │  ← Logo 图标 + 产品名，居中
│      Intelligent Agent Platform      │  ← 副标题，13px，灰色，居中
│                                      │
│   Username                           │
│   ┌────────────────────────────────┐ │  ← 输入框 border-radius: 10px
│   │ admin                          │ │
│   └────────────────────────────────┘ │
│                                      │
│   Password                           │
│   ┌───────────────────────────┐ 👁  │  ← 密码可见切换图标
│   │ ••••••••••••••            │    │
│   └───────────────────────────┘    │
│                                      │
│   ┌────────────────────────────────┐ │  ← 主按钮：纯白/纯黑，全宽
│   │          Sign In               │ │     loading 时显示旋转光标
│   └────────────────────────────────┘ │
│                                      │
└──────────────────────────────────────┘
```

### 6.3 交互细节

- 输入框 focus：border-color → `var(--text-primary)` + 轻微 glow（`box-shadow: 0 0 0 3px rgba(255,255,255,0.1)`）
- 回车触发登录（已实现）
- 错误提示：输入框下方红色文字（非模态框打断），同时输入框 border-color → `var(--accent-red)`
- 登录成功：按钮短暂绿色 → 路由跳转（200ms fade）

---

## 7. 页面规范：初始化向导

### 7.1 布局

全屏顶部进度条（LinearProgress）+ 居中步骤卡片（宽度 560px）。

### 7.2 步骤进度指示

```
── Step 1 ─────── Step 2 ─────── Step 3 ─────── Step 4 ──
   Admin             LLM          Telegram        Done
   [当前步骤高亮白色，已完成步骤绿色，未开始灰色]
```

- 步骤圆圈直径 32px，数字居中，连接线为细线
- 步骤切换：卡片内容 `transform: translateX` 滑动过渡（300ms）

### 7.3 Step 1：管理员密码

- 输入：新密码 + 确认密码（两个输入框）
- 实时强度指示条（4 段：Weak / Fair / Good / Strong）
- 密码规则提示（8 位以上，颜色满足强度后变绿）

### 7.4 Step 2：LLM 提供者

- 顶部 Provider 选择器（卡片形式，Radio Group）：
  - OpenAI / Anthropic Claude / Google Gemini / DeepSeek / 本地（Ollama/vLLM）
  - 每项配一个小图标（或首字母 Avatar）
- 下方动态表单：
  - API Key 输入框（默认遮挡，👁 切换）
  - API Base URL（高级选项，默认折叠）
  - 模型选择（下拉）
- 「Test Connection」按钮：点击后出现加载旋转，成功显示绿色 ✓ + 延迟数

### 7.5 Step 3：Telegram Bot

- Bot Token 输入框
- 模式选择（Radio：Polling / Webhook）
- Webhook 模式时展开：Webhook URL 输入 + Secret Token（自动生成，可复制）
- 白名单 User ID：Tag 输入框（回车添加，× 删除）

### 7.6 Step 4：完成

- 大号绿色 ✓ 图标（动效：stroke-dashoffset 绘制 300ms）
- 「Start Agent」按钮（高亮主色）
- 简要配置摘要（灰色小字展示已配置项）

---

## 8. 页面规范：仪表盘

### 8.1 整体结构

```
page-header
  Title: Dashboard    Sub: System overview

[状态卡片行 — 6 个统计卡片]

[趋势图区域 — 近 7 天折线图]

[快捷状态墙 — 两列：活跃 Workflows + Cron 警告]
```

### 8.2 统计卡片（6 个）

每个卡片规范：
- 宽：弹性 `grid-cols-3`（桌面）/ `grid-cols-2`（平板）/ `grid-cols-1`（移动）
- 内边距：`24px`
- 内容：
  - 顶部：图标（16px，灰色）+ 标签文字（13px，灰色）
  - 中间：大数字（32px，font-weight 600）
  - 底部：环比变化（`+12% vs last 7 days`，绿/红色标注趋势箭头）

| 卡片 | 图标 | 内容 |
|------|------|------|
| Sessions | 消息泡泡 | 历史会话总数 |
| Messages | 文字行 | 总消息条数 |
| Active Workflows | 闪电 | 启用的工作流数 |
| Total Workflows | 节点图 | 工作流总数 |
| Cron Jobs | 时钟 | 定时任务数 |
| Errors (24h) | 警告三角 | 近 24h 错误数（>0 时红色数字）|

### 8.3 趋势图（Sparklines）

- 位置：统计卡片下方，宽幅卡片（全宽 or 50/50 双列）
- 样式：极简折线图（不含坐标轴文字，仅 Y 轴刻度线），颜色与强调色一致
- 内容建议：
  - 左卡：近 7 天消息量趋势
  - 右卡：近 7 天 Token 消耗趋势
- 图表 tooltip：hover 时显示当天精确数值（Naive UI Tooltip 样式）

### 8.4 快捷状态墙

```
┌─────────────────────────┐  ┌──────────────────────────┐
│  Running Workflows       │  │  Recent Cron Warnings    │
│  ─────────────────────── │  │  ─────────────────────── │
│  ● 智能客服 Bot          │  │  ⚠ daily-summary         │
│    Active · 23 runs/day  │  │    Last run failed 2h ago│
│  ● 每日摘要推送          │  │  ✓ weekly-report         │
│    Active · next 08:00   │  │    OK · 5min ago         │
└─────────────────────────┘  └──────────────────────────┘
```

- 状态指示：绿点（在线/成功）、黄点（警告）、红点（错误）、灰点（已停用）
- 每行点击可跳转至对应详情页

### 8.5 Agent 状态条（顶部或侧边栏底部）

实时显示：Agent 运行中（绿色呼吸灯 + "Agent Online"）/ 离线（灰色）。通过 `GET /api/dashboard` + WebSocket `/ws/status` 实时更新。

---

## 9. 页面规范：Createflow 工作流编排

### 9.1 列表页（`/workflows`）

#### 整体结构

```
page-header
  Title: Createflow   Sub: Build and manage your automation workflows
  [+ New Workflow] 按钮

[模式切换 Tab：模板模式 | 高级模式]

[工作流卡片网格]
```

#### 工作流卡片

```
┌──────────────────────────────────────────────┐
│  ⚡ 智能客服 Bot                [● 已启用 ▼] │  ← 名称 + 状态开关（下拉：启用/停用/删除）
│  接收用户消息并智能回复                       │  ← 描述，灰色，2 行截断
│  ─────────────────────────────────────────── │
│  Trigger: Telegram 命令 /chat                │  ← 触发类型徽章
│  Template: 智能客服                           │  ← 模板标签（无模板：自定义）
│  Last run: 3 minutes ago · 15 total runs      │  ← 执行统计
│  ─────────────────────────────────────────── │
│  [Edit]  [Duplicate]  [Run Now]              │  ← 操作区，低调 text 按钮
└──────────────────────────────────────────────┘
```

- 卡片 hover：边框亮度提升 + 微弱阴影，Cursor: pointer
- 启用/停用开关：即时调用 `PUT /api/workflows/{id}` 切换 enabled，Toast 反馈

#### 新建按钮点击后

弹出「选择模式」对话框（320×360px 居中模态）：

```
如何开始？

  ┌──────────────┐  ┌──────────────┐
  │  📋 模板模式  │  │  🎨 高级模式  │
  │  快速配置    │  │  自定义流程图 │
  │  推荐新手    │  │  推荐高级用户 │
  └──────────────┘  └──────────────┘
```

### 9.2 模板模式（三步配置）

点击「模板模式」后，宽抽屉（640px）从右滑出：

```
抽屉标题：新建工作流

Step 1: 选择场景模板
  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
  │  🤖 智能客服  │ │  📄 定时摘要  │ │  📤 消息转发  │
  └──────────────┘ └──────────────┘ └──────────────┘
  ┌──────────────┐ ┌──────────────┐
  │  📎 文档助手  │ │  ✏️ 自定义    │
  └──────────────┘ └──────────────┘

Step 2: 填写参数（根据模板动态渲染表单）
  工作流名称  [_______________]
  System Prompt  [多行文本框]
  模型选择  [下拉 - 从 providers 获取]
  [模板特有字段]

[取消]  [创建并启用]
```

### 9.3 高级模式（流程图编辑器）

路由：`/workflows/new` 或 `/workflows/:id/edit`

#### 9.3.1 整体布局（三列）

```
┌─────────────────────────────────────────────────────────────┐
│  顶栏：[← 返回] 工作流名称  [保存] [运行测试]              │
├──────────────┬───────────────────────────────┬──────────────┤
│  节点面板    │  画布（Vue Flow）             │  配置面板    │
│  Nodes Panel │  Canvas                       │  Config      │
│  180px       │  flex: 1                      │  300px       │
│              │                               │  (选中节点时)│
│  ● Trigger   │                               │              │
│  ● LLM Call  │    [节点] ──── [节点]         │  节点属性编辑│
│  ● Tool      │        └──── [条件] ─── ...   │              │
│  ● Condition │                               │              │
│  ● Response  │                               │              │
│  ● Delay     │                               │              │
│  ● SubAgent  │                               │              │
└──────────────┴───────────────────────────────┴──────────────┘
│  底部：实时测试面板（可折叠）                               │
└─────────────────────────────────────────────────────────────┘
```

#### 9.3.2 节点面板（左侧）

- 节点以卡片方式排列，可拖拽至画布
- 每个节点卡片：图标 + 名称 + 1 行描述
- 节点颜色编码：
  - Trigger：蓝色边框
  - LLM Call：紫色边框
  - Tool：橙色边框
  - Condition：黄色边框
  - Response：绿色边框
  - Delay：灰色边框
  - SubAgent：粉色边框

#### 9.3.3 画布（中间）

- 背景：深色模式下 `#09090B` + 极细点阵（`--bg-base` 点，opacity 0.4）
- 节点：圆角矩形，顶部彩色标题栏，内容区白色文字
- 连线：圆滑贝塞尔曲线，hover 时高亮白色
- 操作：拖拽节点、拖拽连线、右键菜单（删除节点/断开连线）
- 工具栏（画布右下）：缩放 + / -、Fit View、全屏

#### 9.3.4 节点配置面板（右侧）

点击节点后右侧面板展开（300ms 动效），显示该节点的可配置属性：

| 节点类型 | 配置项 |
|---------|--------|
| Trigger | 触发方式（消息/Cron/Webhook/手动）、触发命令、渠道筛选 |
| LLM Call | 模型选择（下拉）、System Prompt（多行）、温度、最大 Token |
| Tool | 工具类型、参数（动态表单）|
| Condition | 条件表达式输入框（支持变量自动补全）|
| Response | 目标渠道、消息模板（支持 `{{variable}}` 语法高亮）|
| Delay | 等待秒数 |
| SubAgent | 任务描述、最大迭代次数 |

#### 9.3.5 底部测试面板

```
┌─────────────────────────────────────────────────────────────┐
│  Live Debug  [折叠▲]                                        │
│  ─────────────────────────────────────────────────────────  │
│  输入模拟消息：[____________________________] [Run]        │
│                                                             │
│  执行日志：                                                  │
│  ● Trigger   ✓ 触发成功  message="测试"  2ms               │
│  ● LLM Call  ⟳ 正在推理...                                 │
│  ● Response  (等待)                                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 10. 页面规范：渠道管理

### 10.1 多渠道状态墙

```
page-header
  Title: Channels   Sub: Manage your communication channels
  [+ Configure New Channel]

[渠道卡片网格 — 3列（桌面）/ 2列（平板）/ 1列（移动）]
```

### 10.2 渠道卡片

```
┌──────────────────────────────────────────────────────┐
│  [渠道图标 40px]   Telegram                ● 在线   │  ← 呼吸灯状态
│                    Bot: @MyComobotBot                 │
│  ─────────────────────────────────────────────────── │
│  Mode: Webhook    |  White List: 3 users              │
│  Last message: 2 min ago                             │
│  ─────────────────────────────────────────────────── │
│  [Configure]   [Test]   [Disable]                   │
└──────────────────────────────────────────────────────┘
```

- 呼吸灯：`--accent-green` 圆点（8px），CSS `animation: breathe 2s ease-in-out infinite`
- 未配置渠道：卡片以虚线边框 + 灰色文字显示「未配置」，点击「Configure」打开配置抽屉

### 10.3 配置抽屉

从右侧滑出（宽度 480px，PC 端），全屏（移动端）：

```
抽屉标题：配置 Telegram

[渠道特有字段动态渲染]
─────────────────────
Bot Token *      [•••••••••••••••] 👁
Webhook URL      [https://...]
Secret Token     [auto-generated]  [复制]
White List       [Tag 输入器：添加 User ID]

[高级设置 — 折叠]
  Polling interval / Timeout 等

─────────────────────
[Cancel]    [Save & Apply]

[Test Connection 按钮]  → 发送握手请求，实时反馈日志
```

- 敏感 Token 默认遮挡（`type="password"`），👁 图标切换明文
- Save 成功：抽屉关闭 + Toast「配置已同步」+ 卡片状态更新（配合 WebSocket 推送）
- 「配置同步中」微动效：卡片出现旋转同步图标（500ms）后消失

---

## 11. 页面规范：模型管理

### 11.1 布局

```
page-header
  Title: Providers   Sub: Configure your AI model providers

[Provider 卡片列表]

[+ Add Provider 按钮]（悬浮在列表底部）
```

### 11.2 Provider 卡片

```
┌────────────────────────────────────────────────────────────┐
│  [OpenAI Logo]  OpenAI               ● 4 keys · Active    │
│  gpt-4o · gpt-4o-mini · gpt-3.5-turbo                    │  ← 支持的模型标签
│  ─────────────────────────────────────────────────────── │
│  Key Rotation: round_robin   Cooldown: 60s               │
│  Last used: 2 min ago  |  Requests today: 1,234          │
│  ─────────────────────────────────────────────────────── │
│  [Edit]   [Test]   [Disable]   [Remove]                  │
└────────────────────────────────────────────────────────────┘
```

### 11.3 添加/编辑 Provider 抽屉（480px）

```
Provider Type:  [选择卡片：OpenAI / Claude / Gemini / 本地]

API Keys (支持多 Key):
  ┌─────────────────────────────────────────────┐
  │  Key #1:  [sk-••••••••••]  👁  [Delete]      │
  │  Key #2:  [sk-••••••••••]  👁  [Delete]      │
  └─────────────────────────────────────────────┘
  [+ Add Another Key]

Key Rotation Strategy:  [Round Robin ▼]
API Base URL:  [可选，用于本地端点]
Default Model: [下拉]

[Test Connection]  → 显示: ✓ Latency: 320ms | Model: gpt-4o
[Cancel]  [Save]
```

---

## 12. 页面规范：会话查看

### 12.1 布局（双栏）

```
┌────────────────────────────────────────────────────────────┐
│  page-header: Sessions   [搜索框] [渠道筛选] [日期筛选]    │
├─────────────────────────┬──────────────────────────────────┤
│  会话列表（左栏）        │  会话详情（右栏）                │
│  300px                  │  flex: 1                        │
│                          │                                  │
│  ┌──────────────────────┐ │  [用户信息栏]                  │
│  │ @telegramUser1       │ │  ─────────────                │
│  │ Telegram · 5 msgs    │ │  [对话气泡流]                  │
│  │ 2 min ago            │ │                                │
│  └──────────────────────┘ │  user: 帮我总结一下今天的新闻  │
│  ┌──────────────────────┐ │  assistant: 好的，以下是...    │
│  │ user@email.com       │ │                                │
│  │ Email · 12 msgs      │ │  [关键记忆 Badge 展示]         │
│  │ 1 hour ago           │ │                                │
└─────────────────────────┴──────────────────────────────────┘
```

### 12.2 对话气泡

- 用户消息：右对齐，白色背景（浅色模式），`--surface` 背景（深色模式），圆角右上无圆角
- 助手消息：左对齐，`--bg-muted` 背景，圆角左上无圆角
- 工具调用（tool role）：折叠展示，点击展开 JSON 详情（代码块格式）
- Markdown 渲染：代码块带语法高亮 + 「Copy」按钮，表格支持横向滚动

### 12.3 关键记忆 Badge

在助手消息下方，如果系统提取了关键记忆节点，显示小 Badge：

```
🔖 已提取记忆：「用户偏好简洁摘要格式」
```

---

## 13. 页面规范：定时任务

### 13.1 布局

```
page-header
  Title: Cron Jobs   Sub: Scheduled automation tasks
  [+ New Cron Job]

[任务列表 — 表格]
```

### 13.2 任务表格

| 列 | 内容 |
|----|------|
| 状态 | 绿/黄/红/灰点 + 文字（Active / Paused / Failed / Disabled）|
| 名称 | 任务名称 + 描述（小字）|
| 计划 | Cron 表达式 + 人类可读解析（`0 8 * * *` → `每天 08:00`）|
| 下次运行 | 倒计时格式（`in 2h 34m`）|
| 上次执行 | 相对时间 + 状态（✓ OK / ✗ Failed）|
| 操作 | [Run Now] [Edit] [Pause/Resume] [Delete] |

### 13.3 Cron 表达式解析显示

在输入框下方实时解析并展示人类可读说明：

```
Cron: [0 8 * * 1-5]
      ↓
      每个工作日（周一至周五）08:00 执行
      下次: 明天 08:00 (14h 23m 后)
```

---

## 14. 页面规范：日志监控

### 14.1 布局

```
page-header
  Title: Logs   Sub: Real-time system audit log
  [WebSocket 状态指示：● 实时连接中]

[过滤工具栏：Level筛选 | Module筛选 | 搜索关键词 | 时间范围]

[日志列表 — 类终端阅读器]
```

### 14.2 日志列表样式

```
字体：monospace（JetBrains Mono / Fira Code）
背景：比页面背景略深（深色：#060608）
行高：28px
每行：时间戳(灰) | Level(彩色Badge) | Module(青色) | Event | Detail
```

| Level | 颜色 |
|-------|------|
| info | 蓝色 `#3B82F6` |
| warn | 黄色 `#EAB308` |
| error | 红色 `#EF4444` |

### 14.3 实时推送

- WebSocket 连接 `/ws/logs`，新日志从底部插入，自动滚动（用户手动上滚时暂停自动滚动，显示「↓ 新消息」Badge）
- 连接断开时：顶部显示警告 Banner，自动重连

### 14.4 搜索与过滤

- 关键词搜索：实时过滤（前端 filter），高亮匹配文字
- 点击 Error 日志行：展开侧滑抽屉，显示完整 JSON Detail 格式化内容

---

## 15. 页面规范：系统设置

### 15.1 布局（左侧分类 Tab + 右侧内容区）

```
┌──────────────┬──────────────────────────────────────────────┐
│  设置分类     │  设置内容区                                   │
│             │                                                │
│  ● 通用      │  [通用设置表单]                               │
│  ○ Agent     │                                               │
│  ○ 安全      │                                               │
│  ○ 存储      │                                               │
│  ○ 账户      │                                               │
└──────────────┴──────────────────────────────────────────────┘
```

### 15.2 通用设置

- UI 主题（Light / Dark / System）
- 语言（中文 / English）
- 时区

### 15.3 Agent 设置

- 编辑 SOUL.md（Monaco Editor 或 Textarea，支持 Markdown 预览）
- 编辑 USER.md（同上）
- 查看 MEMORY.md（只读，带「清空记忆」危险操作按钮）
- 并发控制阈值（数字输入）

### 15.4 安全设置

- 修改管理员密码（旧密码 + 新密码 + 确认）
- JWT Token 有效期配置
- Prompt 注入防护开关

### 15.5 账户设置

- 修改管理员用户名

### 15.6 危险区域

所有危险操作（清空数据、重置配置等）放在页面最底部「危险区域」分区，红色边框卡片，操作前二次确认弹窗（输入 `DELETE` 确认）。

---

## 16. 通用组件库

以下为需统一封装的业务组件，避免重复代码：

### 16.1 StatusBadge

```vue
<StatusBadge status="online" />   → ● Online  (绿色)
<StatusBadge status="offline" />  → ● Offline (灰色)
<StatusBadge status="error" />    → ● Error   (红色)
<StatusBadge status="paused" />   → ● Paused  (黄色)
```

内部：圆点（8px，带呼吸灯动画） + 文字（13px）。

### 16.2 CopyButton

点击复制文字到剪贴板，图标从「复制」变为「✓ 已复制」（1.5s 后恢复）。

### 16.3 SecretInput

输入框封装：默认 `type="password"` + 右侧 👁 切换按钮。API Token 类字段统一使用。

### 16.4 MarkdownRenderer

渲染 Markdown 文本，支持：
- `highlight.js` 代码高亮（主题跟随深/浅色模式）
- 代码块「Copy」按钮
- 表格横向滚动容器包裹
- `<a>` 标签 `target="_blank" rel="noopener"`

### 16.5 PageLayout

统一页面布局包裹组件，包含 Sidebar + 内容区，所有已登录页面复用：

```vue
<PageLayout title="Dashboard" description="System overview">
  <template #actions>
    <NButton>+ New</NButton>
  </template>
  <!-- 页面内容 -->
</PageLayout>
```

### 16.6 EmptyState

数据为空时的占位组件：

```
        [图标 64px，灰色]
        暂无数据
        [描述文字，灰色小字]
        [可选：操作按钮]
```

### 16.7 ConfirmDialog

危险操作确认弹窗：

```vue
<ConfirmDialog
  title="删除工作流"
  description="此操作不可撤销，确认删除「智能客服 Bot」？"
  danger
  @confirm="handleDelete"
/>
```

### 16.8 DataTable（扩展 NDataTable）

统一封装：
- Loading 时显示骨架屏（非 spinner）
- 空数据时显示 EmptyState 组件
- 操作列按钮样式统一（text 样式，间距 8px）

---

## 17. 响应式与自适应

### 17.1 断点定义

```css
--bp-sm:  640px   /* 手机横屏 */
--bp-md:  768px   /* 平板 */
--bp-lg:  1024px  /* 桌面 */
--bp-xl:  1280px  /* 宽屏 */
```

### 17.2 各断点适配规则

| 断点 | 侧边栏 | 内容区 padding | 卡片列数 |
|------|--------|--------------|--------|
| < 768px | 抽屉（汉堡菜单） | 16px | 1 列 |
| 768-1023px | 折叠图标（60px）| 24px | 2 列 |
| ≥ 1024px | 展开（220px）| 40px | 3 列 |

### 17.3 工作流编辑器移动端

工作流编辑器（画布）在移动端不可用，显示提示：「请在桌面端访问工作流编辑器」。列表页和配置抽屉正常可用。

---

## 18. 可访问性

### 18.1 基础规范

- 所有交互元素有 `aria-label` 或可见文字标签
- 颜色对比度满足 WCAG 2.1 AA 标准（深色模式下文字对比度 ≥ 4.5:1）
- 键盘导航：Tab 顺序符合视觉从上到下、从左到右的顺序
- Focus 样式：不使用 `outline: none`，替换为自定义高对比度 focus ring

### 18.2 Focus Ring 规范

```css
:focus-visible {
  outline: 2px solid var(--text-primary);
  outline-offset: 2px;
  border-radius: var(--radius-sm);
}
```

### 18.3 图标可访问性

纯装饰图标：`aria-hidden="true"`
功能性图标按钮：需要 `aria-label="操作描述"`

---

## 附录 A：Naive UI 全局主题注入位置

`src/App.vue` 中的 `NConfigProvider` 已配置深色主题。需扩展为：

```vue
<NConfigProvider
  :theme="isDark ? darkTheme : null"
  :theme-overrides="isDark ? darkThemeOverrides : lightThemeOverrides"
>
```

使用 `useThemeStore().isDark` 响应式切换，避免硬编码深色模式。

## 附录 B：CSS 变量注入方式

在 `src/assets/variables.css` 中定义所有 CSS 自定义属性，通过 `:root` 和 `.dark` class 切换：

```css
:root {
  --bg-base: #FFFFFF;
  --text-primary: #0A0A0A;
  /* ... */
}

.dark {
  --bg-base: #09090B;
  --text-primary: #FAFAFA;
  /* ... */
}
```

在 `main.ts` 中引入，在 `App.vue` 的 `onMounted` 中根据 `isDark` 切换 `document.documentElement.classList`。

## 附录 C：各页面优化优先级排序

| 优先级 | 页面/功能 | 理由 |
|--------|-----------|------|
| P0 | 全局主题系统（双主题 + CSS 变量） | 其他所有页面依赖此基础 |
| P0 | 侧边栏重设计（折叠 + 菜单分组 + Agent 状态） | 用户每次使用都看 |
| P0 | 仪表盘（统计卡片 + 趋势图） | 主页，第一印象 |
| P1 | 渠道管理（卡片 + 配置抽屉 + 呼吸灯） | 核心配置功能 |
| P1 | 模型管理（多 Key 展示 + 测试按钮） | 核心配置功能 |
| P1 | 登录页重设计 | 入口体验 |
| P2 | Createflow 列表页（工作流卡片重设计） | 核心功能 |
| P2 | 会话查看（对话气泡 + Markdown 渲染） | 高频查看 |
| P2 | 日志监控（终端风格 + 实时推送） | 运维必需 |
| P3 | 工作流编辑器 UX 优化（节点样式 + 配置面板） | 复杂功能 |
| P3 | 定时任务（Cron 解析显示） | 辅助功能 |
| P3 | 系统设置（分类 Tab + 危险区域） | 低频使用 |
