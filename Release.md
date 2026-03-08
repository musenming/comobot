## 打包与发布

以下命令面向维护者，用于将代码打包为上述三种分发形式。

### 前置准备

```bash
# 确保在项目根目录
cd /path/to/comobot

# 激活虚拟环境（用于本地测试）
source .venv/bin/activate

# 确认当前版本（pyproject.toml 中的 version 字段）
grep '^version' pyproject.toml
```

---

### 打包方式一：脚本安装包

脚本安装依赖 GitHub Releases 提供源码 zip。打包步骤：

#### 1. 构建前端（需在发布前完成）

```bash
cd web
npm ci
npm run build          # 输出到 web/dist/
cd ..
```

#### 2. 创建 GitHub Release（打 tag 触发）

```bash
# 修改 pyproject.toml 中的 version，然后提交
git add pyproject.toml
git commit -m "chore: bump version to v1.x.x"

# 打 tag（会触发 GitHub Actions 自动构建 Docker 镜像 + 创建 Release）
git tag v1.x.x
git push origin main --tags
```

> Actions 工作流 `.github/workflows/docker-publish.yml` 会自动：
> - 构建 Docker 镜像并推送到 GHCR
> - 打包 `comobot-docker.zip` 并挂载到 Release

#### 3. 安装脚本分发

安装脚本通过 GitHub raw URL 直接分发，无需额外静态托管：

```
https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.sh
https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.ps1
https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.bat
```

脚本随代码仓库自动更新，推送到 `main` 分支即生效。

#### 4. 验证脚本可用性

```bash
# 本地测试安装脚本（沙箱环境）
bash scripts/install.sh

# 或用 Docker 模拟干净环境测试
docker run --rm -it ubuntu:22.04 bash -c \
  "apt-get update -qq && apt-get install -y curl && \
   bash <(curl -fsSL https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.sh)"
```

---

### 打包方式二：Docker 镜像

#### 本地构建（测试用）

```bash
# 构建镜像（多平台需要 buildx）
docker build -t comobot:local .

# 验证镜像正常启动
docker run --rm -p 18790:18790 -v /tmp/comobot-test:/root/.comobot comobot:local

# 检查镜像大小
docker images comobot:local
```

#### 多平台构建并推送到 GHCR

```bash
# 登录 GHCR（需要 GitHub Token，scope: write:packages）
echo $GITHUB_TOKEN | docker login ghcr.io -u <github-username> --password-stdin

# 创建并使用 buildx builder（首次）
docker buildx create --name comobot-builder --use
docker buildx inspect --bootstrap

# 构建 amd64 + arm64 并直接推送
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag ghcr.io/musenming/comobot:latest \
  --tag ghcr.io/musenming/comobot:v1.x.x \
  --push \
  .
```

#### 打包 Docker 用户分发包（`comobot-docker.zip`）

```bash
mkdir -p dist/comobot-docker

cp docker-compose.yml dist/comobot-docker/
cp docker/start.command dist/comobot-docker/
cp docker/start.bat dist/comobot-docker/
chmod +x dist/comobot-docker/start.command

cat > dist/comobot-docker/README.txt <<'EOF'
Comobot - Docker 快速启动包
============================

前提：安装 Docker Desktop https://www.docker.com/products/docker-desktop/

启动：
  macOS   → 双击 start.command
  Windows → 双击 start.bat

浏览器将自动打开 http://localhost:18790，按向导完成配置。

停止：在终端执行 docker compose down
EOF

cd dist
zip -r comobot-docker.zip comobot-docker/
echo "Generated: dist/comobot-docker.zip ($(du -sh comobot-docker.zip | cut -f1))"
```

#### 手动上传到 GitHub Release

```bash
# 使用 GitHub CLI 上传附件到指定 Release
gh release upload v1.x.x dist/comobot-docker.zip --clobber
```

---

### 打包方式三：GitHub Actions 自动发布（CI/CD）

**工作流文件**：`.github/workflows/docker-publish.yml`

**触发条件**：推送任意 `v*` 格式的 tag

完整发布流程：

```bash
# 1. 确保本地代码已提交并通过测试
git status          # 应为 clean
.venv/bin/pytest tests/ -v

# 2. 确认 pyproject.toml 版本号已更新
grep '^version' pyproject.toml   # 例如 version = "1.2.0"

# 3. 打 tag 并推送（触发 Actions）
VERSION="v1.2.0"
git tag $VERSION
git push origin $VERSION

# 4. 查看 Actions 执行状态
gh run list --workflow=docker-publish.yml

# 5. 查看具体日志
gh run view --log

# 6. 验证 Release 和镜像
gh release view $VERSION
docker pull ghcr.io/musenming/comobot:$VERSION
docker pull ghcr.io/musenming/comobot:latest
```

**Actions 自动完成**：
1. 检出代码
2. 配置 QEMU + buildx（多平台支持）
3. 登录 GHCR（使用 `GITHUB_TOKEN`，无需配置 Secret）
4. 构建 `linux/amd64` + `linux/arm64` 镜像并推送
5. 打包 `comobot-docker.zip`（含 docker-compose.yml + start 脚本 + README）
6. 创建 GitHub Release，自动生成 Release Notes，附上 `comobot-docker.zip`

---

## 发布检查清单

```
发布前：
  [ ] pyproject.toml version 已更新
  [ ] CHANGELOG 或 commit message 清晰
  [ ] pytest tests/ -v 全部通过
  [ ] ruff check . 无报错
  [ ] web/dist/ 已构建（前端资源最新）

打 tag 后：
  [ ] gh run list 确认 Actions 运行中
  [ ] Actions 绿色通过
  [ ] gh release view v* 确认 Release 存在
  [ ] comobot-docker.zip 已挂载到 Release
  [ ] ghcr.io/musenming/comobot:latest 镜像可拉取
  [ ] 安装脚本可通过 GitHub raw URL 访问

发布后验证：
  [ ] Docker: docker compose up -d → 浏览器打开向导
  [ ] 脚本: bash <(curl -fsSL https://raw.githubusercontent.com/musenming/comobot/main/scripts/install.sh)
```

---

## 开发调试

```bash
# Lint
.venv/bin/ruff check .

# 自动修复
.venv/bin/ruff check . --fix

# 格式化
.venv/bin/ruff format .

# 测试
.venv/bin/pytest tests/ -v

# 单个测试
.venv/bin/pytest tests/test_commands.py -v

# 启动（开发模式）
.venv/bin/comobot gateway

# 前端热重载（开发模式）
# Terminal 1: .venv/bin/comobot gateway
# Terminal 2: cd web && npm run dev → http://localhost:5173
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `COMOBOT_PORT` | `18790` | 网关 HTTP 端口 |
| `COMOBOT_SECRET_KEY` | 自动生成 | 凭据加密密钥 |
| `COMOBOT_AGENTS__DEFAULTS__MODEL` | `anthropic/claude-opus-4-5` | 默认 LLM 模型 |

## 故障排除

| 现象 | 解决方案 |
|------|----------|
| `ModuleNotFoundError: nh3` | `pip install -e ".[matrix]"` |
| `websockets` 安装失败 | 确认 Python >= 3.10 |
| Docker 镜像启动后无法访问 | 检查 18790 端口是否被占用：`lsof -i :18790` |
| macOS `.command` 被 Gatekeeper 拦截 | 右键文件 → 打开 → 允许 |
| Windows 脚本执行策略报错 | 以管理员身份运行 PowerShell，执行 `Set-ExecutionPolicy RemoteSigned` |
| install.sh 下载失败 | 检查网络，或从 GitHub Releases 手动下载源码 zip |
