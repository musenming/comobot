# Comobot Installation Guide

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | >= 3.11 | 3.11+ required; oauth-cli-kit does not support 3.10 |
| pip | >= 22.0 | Upgraded automatically in venv |
| Node.js | >= 18 | Required for frontend and WhatsApp bridge |
| Git | any | For source installation |

## Method 1: Install from Source (Recommended for Development)

### 1. Clone the repository

```bash
git clone https://github.com/musenming/comobot.git
cd comobot
```

### 2. Create an isolated virtual environment

```bash
python3.11 -m venv .venv
# or: python3.12 -m venv .venv
```

### 3. Activate the virtual environment

```bash
source .venv/bin/activate
```

### 4. Upgrade pip

```bash
pip install --upgrade pip setuptools wheel
```

### 5. Install Comobot in editable mode (with dev tools)

```bash
pip install -e ".[dev]"
```

This installs all core dependencies plus `ruff` (linter/formatter) and `pytest` (test runner).

### 6. (Optional) Install Matrix channel support

```bash
pip install -e ".[matrix]"
```

### 7. Verify installation

```bash
comobot --help       # Should show CLI commands
comobot --version    # Should print version
```

### 8. Run tests

```bash
pytest tests/ -v
```

> **Note:** `test_matrix_channel.py` requires the `[matrix]` extra. It will error if not installed.

## Method 2: Install from PyPI

```bash
pip install comobot
```

## Method 3: Install with uv (fast)

```bash
uv tool install comobot
```

## Method 4: Docker

### Docker Compose (recommended)

```bash
docker compose run --rm comobot-cli onboard   # First-time setup
vim ~/.comobot/config.json                     # Add API keys
docker compose up -d comobot-gateway           # Start gateway
```

### Docker (manual)

```bash
docker build -t comobot .
docker run -v ~/.comobot:/root/.comobot --rm comobot onboard
vim ~/.comobot/config.json
docker run -v ~/.comobot:/root/.comobot -p 18790:18790 comobot gateway
```

## Post-Install Setup

### 1. Initialize configuration

```bash
comobot onboard
```

This creates `~/.comobot/config.json` and `~/.comobot/workspace/`.

### 2. Configure API provider

Edit `~/.comobot/config.json` and add at minimum a provider API key:

```json
{
  "providers": {
    "openrouter": {
      "apiKey": "sk-or-v1-xxx"
    }
  },
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5",
      "provider": "openrouter"
    }
  }
}
```

### 3. Start chatting

```bash
comobot agent              # Interactive mode
comobot agent -m "Hello!"  # Single message
comobot gateway            # Start gateway (API + channels + web UI)
```

## Web Frontend

The web frontend is a Vue 3 + Naive UI application in `web/`.

### Production Mode

The gateway serves the pre-built frontend automatically. Just build the frontend once, then start the gateway:

```bash
cd web
npm install
npm run build        # Outputs to web/dist/
cd ..
comobot gateway      # Serves frontend + API on port 18790
```

Open `http://localhost:18790` in your browser.

### Development Mode (Hot Reload)

For frontend development with hot reload:

```bash
# Terminal 1: Start the backend gateway
comobot gateway                  # API on port 18790

# Terminal 2: Start Vite dev server
cd web
npm install
npm run dev                      # Frontend on port 5173
```

Open `http://localhost:5173` in your browser. The Vite dev server proxies `/api` and `/ws` requests to the backend automatically.

| Service | Port | Description |
|---------|------|-------------|
| Gateway (production) | `18790` | API + built frontend (single process) |
| Vite dev server | `5173` | Frontend with hot reload (dev only) |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COMOBOT_PORT` | `18790` | Gateway HTTP port |
| `COMOBOT_SECRET_KEY` | auto-generated | Credential encryption key |

See `.env.example` for a full template.

## WhatsApp Bridge Setup

The WhatsApp bridge requires Node.js >= 18:

```bash
cd bridge
npm install
npm run build
```

Then link your device:

```bash
comobot channels login   # Scan QR with WhatsApp
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: nh3` | Install matrix extras: `pip install -e ".[matrix]"` |
| `websockets` install fails | Ensure Python >= 3.10 |
| `oauth-cli-kit` not found | May not be on all PyPI mirrors; install manually if needed |
| Pre-commit hook fails | Run `ruff check . --fix && ruff format .` |

## Development Commands

```bash
# Lint
ruff check .

# Auto-fix lint issues
ruff check . --fix

# Format
ruff format .

# Run tests
pytest tests/ -v

# Run a specific test
pytest tests/test_commands.py -v
```
