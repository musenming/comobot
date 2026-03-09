# Comobot 安装方案升级计划

## 一、当前问题分析

### 1. 404 错误原因

用户执行的命令：
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/musenming/comobot-install/main/docs/scripts/install.sh | sh)"
```

**问题拆解：**

| 问题 | 说明 |
|------|------|
| 仓库名错误 | 实际仓库是 `musenming/comobot`，命令中写的是 `musenming/comobot-install` |
| 路径不匹配 | 安装脚本在 `docs/scripts/install.sh`，但脚本内注释写的 URL 是 `scripts/install.sh`（无 `docs/` 前缀） |
| GitHub Pages 未生效 | `docs/` 目录下的文件通过 GitHub Pages 发布需要在仓库 Settings 中启用并配置 source |
| `raw.githubusercontent.com` 不走 Pages | `raw.githubusercontent.com` 直接读取仓库文件，与 GitHub Pages 无关。Pages 走的是 `<user>.github.io/<repo>/` 域名 |
| 命令语法冗余 | `curl ... | sh` 外面又套了 `/bin/bash -c "$(...)"` ，应该二选一 |

### 2. 安装脚本与 Release 流程脱节

- `release.yml` 用 Nuitka 编译出 **单文件二进制**（`comobot-x.x.x-macos-x64.tar.gz` 等），上传到 GitHub Releases
- 但安装脚本 `install.sh` 下载的是 **源码 zip**（`zipball_url`），然后 `pip install -e .` 从源码安装
- **两条路径完全不一致**：编译好的二进制白白浪费，安装脚本还在走源码安装

### 3. 脚本功能过重

当前安装脚本试图做太多事情：安装 Python、安装 Node.js、构建前端、配置自启动、创建桌面快捷方式。对于二进制分发方案来说，用户不需要安装 Python 和 Node.js。

---

## 二、推荐方案：基于 GitHub Releases 的二进制分发

### 核心思路

```
用户一键命令 → 下载安装脚本 → 脚本从 GitHub Releases 下载编译好的二进制 → 解压到目标目录 → 加入 PATH → 完成
```

**不再**依赖 GitHub Pages，**不再**要求用户安装 Python/Node.js。

### 2.1 文件结构调整

```
comobot/
├── scripts/                          # 移到根目录（从 docs/scripts/ 移出）
│   ├── install.sh                    # macOS / Linux 安装脚本
│   └── install.ps1                   # Windows 安装脚本
├── docs/                             # 留给文档，不放脚本
├── .github/
│   └── workflows/
│       └── release.yml               # 编译 + 发布（已有，需微调）
```

**理由：** `raw.githubusercontent.com` URL 越短越好，且 `scripts/` 在根目录下更符合开源项目惯例。

### 2.2 安装命令（用户看到的）

**macOS / Linux：**
```bash
curl -fsSL https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.sh | bash
```

**Windows (PowerShell)：**
```powershell
irm https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.ps1 | iex
```

### 2.3 安装脚本重写（核心逻辑）

#### install.sh 主流程

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO="musenming/comobot"
INSTALL_DIR="$HOME/.comobot/bin"

# 1. 检测系统架构
detect_platform() {
    OS=$(uname -s | tr '[:upper:]' '[:lower:]')     # darwin / linux
    ARCH=$(uname -m)                                  # x86_64 / arm64

    case "$OS" in
        darwin) PLATFORM="macos" ;;
        linux)  PLATFORM="linux" ;;
        *)      error "不支持的操作系统: $OS" ;;
    esac

    case "$ARCH" in
        x86_64|amd64) ARCH="x64" ;;
        arm64|aarch64) ARCH="arm64" ;;
        *)             error "不支持的架构: $ARCH" ;;
    esac
}

# 2. 从 GitHub Releases API 获取最新版本的下载 URL
get_download_url() {
    RELEASE_INFO=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest")
    VERSION=$(echo "$RELEASE_INFO" | grep '"tag_name"' | sed 's/.*"v\(.*\)".*/\1/')
    ASSET_NAME="comobot-${VERSION}-${PLATFORM}-${ARCH}.tar.gz"
    DOWNLOAD_URL=$(echo "$RELEASE_INFO" | grep "browser_download_url" | grep "$ASSET_NAME" | cut -d'"' -f4)

    if [[ -z "$DOWNLOAD_URL" ]]; then
        error "未找到适合 ${PLATFORM}-${ARCH} 的安装包，请检查 Releases 页面"
    fi
}

# 3. 下载 + 解压 + 安装
install() {
    mkdir -p "$INSTALL_DIR"
    TMP=$(mktemp -d)
    curl -fsSL "$DOWNLOAD_URL" -o "$TMP/comobot.tar.gz"
    tar -xzf "$TMP/comobot.tar.gz" -C "$TMP"
    cp "$TMP/comobot/comobot" "$INSTALL_DIR/comobot"
    chmod +x "$INSTALL_DIR/comobot"
    rm -rf "$TMP"
}

# 4. 添加到 PATH
setup_path() {
    SHELL_RC=""
    case "$SHELL" in
        */zsh)  SHELL_RC="$HOME/.zshrc" ;;
        */bash) SHELL_RC="$HOME/.bashrc" ;;
        *)      SHELL_RC="$HOME/.profile" ;;
    esac

    PATH_LINE="export PATH=\"$INSTALL_DIR:\$PATH\""
    if ! grep -q "$INSTALL_DIR" "$SHELL_RC" 2>/dev/null; then
        echo "" >> "$SHELL_RC"
        echo "# Comobot" >> "$SHELL_RC"
        echo "$PATH_LINE" >> "$SHELL_RC"
    fi
}

# 5. 验证安装
verify() {
    export PATH="$INSTALL_DIR:$PATH"
    if command -v comobot &>/dev/null; then
        echo "✅ Comobot 安装成功！版本: $(comobot --version 2>/dev/null || echo $VERSION)"
        echo "   运行 'comobot --help' 开始使用"
        echo "   请重新打开终端或执行: source $SHELL_RC"
    else
        echo "⚠️  安装完成但验证失败，请检查 $INSTALL_DIR"
    fi
}
```

#### install.ps1 主流程

```powershell
$REPO = "musenming/comobot"
$INSTALL_DIR = "$env:LOCALAPPDATA\comobot"

# 1. 获取最新版本下载链接
$release = Invoke-RestMethod "https://api.github.com/repos/$REPO/releases/latest"
$asset = $release.assets | Where-Object { $_.name -like "*windows-x64*" } | Select-Object -First 1
$url = $asset.browser_download_url

# 2. 下载解压
$tmp = "$env:TEMP\comobot-install"
Invoke-WebRequest $url -OutFile "$tmp.tar.gz"
tar -xzf "$tmp.tar.gz" -C $env:TEMP
Copy-Item "$env:TEMP\comobot\comobot.exe" "$INSTALL_DIR\comobot.exe" -Force

# 3. 加入用户 PATH
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$INSTALL_DIR*") {
    [Environment]::SetEnvironmentVariable("Path", "$INSTALL_DIR;$userPath", "User")
}

# 4. 验证
& "$INSTALL_DIR\comobot.exe" --version
```

### 2.4 release.yml 需要的改动

当前 workflow 已经基本正确，需要补充以下内容：

#### a) 添加 ARM64 构建（macOS Apple Silicon）

```yaml
matrix:
  include:
    - os: ubuntu-latest
      target: linux-x64
    - os: macos-latest        # GitHub Actions macos-latest 已经是 ARM64
      target: macos-arm64
    - os: macos-13            # Intel Mac
      target: macos-x64
    - os: windows-latest
      target: windows-x64
```

#### b) tar.gz 文件命名保持一致

确保产出命名为 `comobot-{version}-{target}.tar.gz`，与安装脚本匹配：
- `comobot-0.1.0-macos-arm64.tar.gz`
- `comobot-0.1.0-macos-x64.tar.gz`
- `comobot-0.1.0-linux-x64.tar.gz`
- `comobot-0.1.0-windows-x64.tar.gz`

#### c) 添加 SHA256 校验文件

在 release job 中生成 checksums 文件：
```yaml
- name: Generate checksums
  run: |
    cd dist
    sha256sum *.tar.gz > checksums.txt
```

上传 `checksums.txt` 到 Release Assets，安装脚本可选验证。

### 2.5 首次配置引导（onboard）

安装完二进制后，用户第一次运行 `comobot` 时：

```bash
comobot          # 自动进入 onboard 引导
comobot onboard  # 手动触发配置
```

引导流程（已有 `comobot onboard` 命令）：
1. 创建 `~/.comobot/config.json`
2. 设置 LLM provider API Key
3. 选择要启用的 channel（Telegram/Slack/...）
4. 启动 gateway

---

## 三、实施步骤

### Step 1：移动安装脚本
```bash
git mv docs/scripts/install.sh scripts/install.sh
git mv docs/scripts/install.ps1 scripts/install.ps1
git mv docs/scripts/install.bat scripts/install.bat   # 可选保留
rmdir docs/scripts  # 如果空了
```

### Step 2：重写 `scripts/install.sh`
- 删除 Python/Node.js 安装逻辑
- 改为从 GitHub Releases 下载预编译二进制
- 只做：下载 → 解压 → 放到 PATH → 验证
- 可选：添加 `--version` 参数指定版本

### Step 3：重写 `scripts/install.ps1`
- 同上，改为二进制分发
- 删除 `install.bat`（PowerShell 5.1+ 在 Win10 已内置，bat 入口不再需要）

### Step 4：更新 `release.yml`
- 添加 macOS ARM64 构建
- 添加 checksums
- 确认产物命名规范

### Step 5：发布测试版本
```bash
git tag v0.1.0-rc1
git push origin v0.1.0-rc1
```
等 CI 完成后，在不同平台测试安装命令。

### Step 6：更新 README / INSTALL.md
在文档中提供一键安装命令：

```markdown
## 安装

### macOS / Linux
```bash
curl -fsSL https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.sh | bash
```

### Windows (PowerShell)
```powershell
irm https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.ps1 | iex
```
```

---

## 四、可选增强（后续迭代）

| 功能 | 说明 |
|------|------|
| Homebrew Tap | 创建 `musenming/homebrew-tap` 仓库，macOS 用户可 `brew install musenming/tap/comobot` |
| 自动更新 | `comobot update` 命令，检查新版本并自动下载替换二进制 |
| GitHub Pages 文档站 | `docs/` 用于放项目文档网站（MkDocs/VitePress），与安装脚本分离 |
| Linux 包管理器 | `.deb` / `.rpm` 包发布，通过 PPA 或 COPR 分发 |
| 安装脚本 CDN 加速 | 使用 `https://install.comobot.dev` 自定义域名 + CDN，避免 raw.githubusercontent.com 在某些地区被墙 |
| 离线安装包 | 提供包含所有依赖的完整离线包，适合内网环境 |

---

## 五、FAQ

**Q: 为什么不用 GitHub Pages 托管安装脚本？**
A: `raw.githubusercontent.com` 直接从仓库读文件，无需额外配置。GitHub Pages 需要启用、配置 source、等待部署，且 URL 格式不同（`musenming.github.io/comobot/scripts/install.sh`）。对于安装脚本这种单文件场景，raw URL 更简单可靠。

**Q: 为什么不继续用源码安装？**
A: 源码安装要求用户有 Python 3.11+、pip、venv，增加了安装复杂度和失败概率。预编译二进制零依赖，解压即用。

**Q: Windows 用户没有 curl/tar 怎么办？**
A: Windows 10 1803+ 自带 curl，1903+ 自带 tar。PowerShell 的 `Invoke-WebRequest` 和 `Expand-Archive` 也可作为替代。install.ps1 使用 PowerShell 原生 cmdlet，不依赖外部工具。

**Q: Apple Silicon (M1/M2/M3) 用户怎么办？**
A: 在 release.yml 中添加 `macos-arm64` 构建目标。`macos-latest` runner 在 GitHub Actions 上已经是 ARM64。安装脚本通过 `uname -m` 自动检测架构。
