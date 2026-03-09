# Comobot 安装升级 PRD（macOS / Windows 一键安装 + 源码不可见）

## 1. 文档信息

- 文档版本：v1.0
- 日期：2026-03-09
- 适用项目：`comobot`
- 目标读者：产品、后端、客户端/运维、发布工程

---

## 2. 背景与目标

`comobot` 是 7×24 小智能体产品，当前仓库已具备基础安装脚本（`scripts/install.sh`、`scripts/install.ps1`、`scripts/install.bat`）与 Docker 运行能力，但仍存在“开发者安装思路”偏重的问题：

1. 安装包来源是仓库 zip，用户端能看到项目源码。
2. 安装时执行 `pip install -e`，本质是可编辑源码安装。
3. 依赖策略偏开发态（如前端在用户机本地 `npm build`）。
4. 版本升级、回滚、签名校验与失败恢复流程不完整。

本次升级目标：

1. 在 macOS / Windows 提供稳定的一键安装与一键升级。
2. 自动完成依赖准备、虚拟环境创建与激活（对用户无感）。
3. 用户侧不暴露原始源码（可读 `.py` / TS 源文件）。
4. 具备可运维能力：日志、健康检查、更新回滚、故障诊断。

---

## 3. 现状分析（基于当前代码）

### 3.1 技术栈与入口

- Python 主体：`pyproject.toml`，入口命令 `comobot = comobot.cli.commands:app`。
- 核心运行：`comobot gateway`（默认端口 `18790`）。
- 数据目录：`~/.comobot`。
- WhatsApp 桥：`bridge/`（Node + TypeScript，`node >=20`）。

### 3.2 当前安装脚本能力

- 已有跨平台脚本：
  - macOS/Linux：`scripts/install.sh`
  - Windows：`scripts/install.ps1` + `scripts/install.bat`
- 已覆盖：Python/Node 安装、创建 venv、服务启动、打开浏览器。

### 3.3 关键问题与风险

1. **源码可见**：下载 GitHub zip 并 `pip install -e`，源码完全落盘可读。
2. **依赖版本不一致风险**：
	- `bridge/package.json` 要求 `node >=20`；
	- 安装脚本仍按 `Node 18` 处理。
3. **本地构建链过重**：用户机器构建前端，失败率高且耗时。
4. **供应链安全薄弱**：缺少安装包哈希/签名强校验。
5. **升级可控性不足**：缺少原子更新、自动回滚与灰度机制。

---

## 4. 范围定义

### 4.1 In Scope

1. macOS 与 Windows 一键安装器升级。
2. 安装器自动创建并激活内部虚拟环境。
3. 闭源分发（用户看不到原始源码）。
4. 一键升级、失败回滚与日志诊断。

### 4.2 Out of Scope

1. Linux 桌面一键安装体验优化（保留现有脚本，后续迭代）。
2. 模型能力与业务功能改动。
3. Web 功能重构。

---

## 5. 目标用户与核心场景

### 5.1 目标用户

1. 非技术用户：只希望“下载→双击→可用”。
2. 轻技术用户：能看日志，但不希望维护 Python/Node 环境。

### 5.2 核心场景

1. 首次安装：一条命令或双击安装包完成部署。
2. 日常升级：点击“检查更新/一键升级”，不中断或最小中断。
3. 故障恢复：升级失败自动回滚到上一个可用版本。

---

## 6. 总体方案（推荐）

## 6.1 分发形态

采用“双层分发”：

1. **安装器层**（平台原生）：
	- macOS：`pkg`（可选 notarization）。
	- Windows：`MSI`（可选代码签名）。
2. **运行时层**（闭源运行包）：
	- Python 主程序编译产物（不含原始 `.py`）。
	- 预构建前端静态文件（`web/dist`）。
	- 预构建 WhatsApp bridge（二进制或最小化运行包）。

> 说明：用户侧允许存在配置、模板、日志文件；禁止分发可直接阅读的核心业务源码。

## 6.2 源码不可见策略

推荐方案（优先级从高到低）：

1. **方案 A（推荐）**：Nuitka 编译 `comobot` 为平台二进制（`standalone`）。
2. **方案 B**：PyInstaller + 字节码归档（保护弱于 A，仅作为过渡）。
3. **方案 C**：关键模块 Cython 化 + wheel 分发（改造成本较高）。

本项目建议采用 **A + 发布签名校验**：

1. CI 构建 `comobot-core` 二进制。
2. 安装器仅下发二进制与资源包，不下发仓库源码。
3. 更新包携带 `SHA256` 与签名文件，安装端强校验。

## 6.3 “一键安装 + 虚拟环境”设计

为了满足“安装依赖 + 激活虚拟环境 + 一键安装”，同时兼顾闭源：

1. 安装器在应用目录创建内部 venv（用户无感）：
	- macOS：`~/Library/Application Support/comobot/runtime/.venv`
	- Windows：`%LOCALAPPDATA%\Comobot\runtime\.venv`
2. venv 中仅安装运行时 wheel/依赖，不安装源码 editable 包。
3. 安装器生成启动器（launcher）：
	- 启动前自动激活 venv（脚本内完成）。
	- 执行 `comobot gateway`（或编译后二进制入口）。
4. 用户入口为桌面图标/开始菜单，不需手动执行 `source activate`。

---

## 7. 安装与升级流程设计

## 7.1 首次安装流程

1. 环境检测：系统版本、磁盘空间、端口占用、管理员权限。
2. 运行时准备：
	- 若采用嵌入式运行包，则无需用户预装 Python/Node；
	- 若采用轻量运行包，则自动下载并安装受控版本。
3. 创建目录结构：
	- `app/`（程序）
	- `runtime/`（venv、依赖）
	- `data/`（配置、工作区、数据库、日志）
4. 初始化配置：生成 `config.json`（若不存在）。
5. 注册开机自启（可选开关，默认关闭）。
6. 启动健康检查：`/api/health` 成功后提示安装完成。

## 7.2 升级流程（原子升级）

1. 检查更新（版本清单 + 签名验证）。
2. 下载新包至临时目录并校验 `SHA256`。
3. 停服务 → 备份当前版本到 `releases/<old_version>`。
4. 切换软链接/目录指针到新版本。
5. 启动并做健康检查：
	- 成功：清理旧版本（保留最近 N 个）。
	- 失败：自动回滚并上报错误日志。

## 7.3 回滚策略

1. 自动回滚：升级后 `T=120s` 内健康检查失败触发。
2. 手动回滚：`comobot-launcher --rollback <version>`。
3. 数据回滚：仅在 schema 变更时提供迁移回退脚本。

---

## 8. 目录与工件规范

## 8.1 本地目录建议

macOS：

- 应用：`/Applications/Comobot.app` 或 `~/Applications/Comobot.app`
- 运行时：`~/Library/Application Support/comobot/runtime/`
- 数据：`~/.comobot/`

Windows：

- 应用：`%ProgramFiles%\Comobot\`
- 运行时：`%LOCALAPPDATA%\Comobot\runtime\`
- 数据：`%USERPROFILE%\.comobot\`

## 8.2 发布工件

1. `comobot-core-<ver>-<os>-<arch>.tar.zst`（闭源核心运行包）
2. `comobot-installer-<ver>-macos.pkg`
3. `comobot-installer-<ver>-windows.msi`
4. `checksums.txt` + `checksums.txt.sig`
5. `manifest.json`（版本、渠道、最小兼容版本）

---

## 9. 安全与合规要求

1. 安装包签名校验（MSI 代码签名、macOS 签名/公证）。
2. 更新包必须校验哈希与签名，不允许明文替换。
3. 凭证仅存储于用户数据目录，禁止打包到程序目录。
4. 日志默认脱敏（API Key、Token、Cookie）。
5. 在许可文档中明确：comobot 早期产品基于 nanobot 研发。

---

## 10. 与当前仓库的改造点

## 10.1 脚本层改造

1. `scripts/install.sh`：
	- 去除 `pip install -e` 源码安装。
	- 去除用户侧 `npm build`。
	- 增加包签名校验与失败回滚。
2. `scripts/install.ps1`：
	- 同步上述策略。
	- 加入 Windows 服务/计划任务标准化启动。
3. `scripts/install.bat`：保留为 PowerShell 引导器。

## 10.2 CI/CD 改造

1. 新增多平台构建流水线：
	- 构建闭源核心包（Nuitka）。
	- 构建前端静态资源并注入运行包。
	- 生成安装器（pkg/msi）。
2. 发布阶段生成 `manifest + checksum + signature`。
3. 增加 smoke test：安装、启动、健康检查、卸载、升级回滚。

## 10.3 版本策略

1. 语义化版本：`MAJOR.MINOR.PATCH`。
2. 安装器支持“稳定版/灰度版”渠道。
3. 最小支持升级跨度：最近 3 个小版本。

---

## 11. 非功能性指标（NFR）

1. 安装成功率：
	- macOS ≥ 98%
	- Windows ≥ 97%
2. 首次安装耗时（50M 网络）：
	- P50 ≤ 6 分钟
	- P90 ≤ 10 分钟
3. 升级失败自动回滚成功率 ≥ 99%。
4. 用户侧不可见原始源码达成率 100%。

---

## 12. 里程碑计划

### M1（1 周）：方案冻结 + 原型

1. 确认 Nuitka 可编译范围。
2. 确认安装目录与权限模型。
3. 打通最小闭源包启动。

### M2（1-2 周）：安装器联调

1. macOS `pkg` 与 Windows `msi` 打包。
2. 自动创建 venv + 启动器接入。
3. 健康检查与日志采集。

### M3（1 周）：升级回滚与安全

1. 原子升级与回滚。
2. checksum + signature 验证。
3. 灰度发布策略。

### M4（1 周）：验收发布

1. 全量 smoke test。
2. 文档与 FAQ 更新。
3. 正式发布 `v0.x`。

---

## 13. 验收标准（DoD）

1. 用户在 macOS / Windows 上可“一键安装并启动”。
2. 安装过程中自动完成依赖准备与内部虚拟环境激活。
3. 用户安装目录中不包含可直接阅读的原始 Python/TS 源码。
4. 一键升级可用，失败可自动回滚。
5. 安装、升级、回滚均有可追踪日志。
6. 安装文档与故障排查文档同步上线。

---

## 14. 风险与应对

1. **Python 动态特性导致编译兼容问题**：
	- 应对：先做模块白名单编译，保留少量兼容层。
2. **杀软误报（Windows）**：
	- 应对：代码签名、减少自修改行为、提供白名单说明。
3. **跨平台依赖差异**：
	- 应对：CI 多平台矩阵 + 预发通道灰度。
4. **升级中断导致不可用**：
	- 应对：原子切换 + 自动回滚 + 健康探针。

---

## 15. 建议的下一步实施清单（工程任务）

1. 新增 `release/manifest.json` 规范与签名脚本。
2. 调整 `scripts/install.sh` / `scripts/install.ps1` 为“安装闭源工件”模式。
3. 引入 `build-nuitka` 流水线与平台安装器打包流水线。
4. 增加 `comobot-launcher`（统一启动/升级/回滚命令）。
5. 新增 `doc/install_runbook.md`（安装失败与回滚手册）。

---

## 16. 结论

该升级方案在不改变 `comobot` 核心业务能力的前提下，完成从“开发者安装”到“产品级安装”的转型，重点满足：

1. macOS / Windows 一键安装。
2. 自动依赖与虚拟环境管理。
3. 用户不可见原始源码。
4. 可持续升级、可回滚、可运维。

