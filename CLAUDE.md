# comobot

Lightweight personal AI assistant framework with multi-channel support.

## Project Structure

- `comobot/` - Core Python package (87 Python files)
  - `agent/` - Agent loop, context, memory, skills, subagent
    - `tools/` - Built-in tools (shell, filesystem, web, spawn, mcp, cron, message)
  - `api/` - FastAPI REST API and gateway
    - `routes/` - API route handlers
  - `bus/` - Event bus and queue
  - `channels/` - Chat integrations: Telegram, Slack, DingTalk, Feishu, Discord, QQ, Email, Matrix, WhatsApp, Mochat
  - `cli/` - CLI entry point (`comobot` command via Typer)
  - `config/` - Config schema (Pydantic) and loader
  - `cron/` - Scheduled tasks (with SQLite store)
  - `db/` - Database layer (SQLite + WAL mode)
  - `heartbeat/` - Proactive wake-up service
  - `orchestrator/` - Optional orchestration layer on AgentLoop
  - `providers/` - LLM providers (litellm, openai-codex, custom, key rotator)
  - `security/` - Authentication, encryption, access control
  - `session/` - Session management (with SQLite backend)
  - `skills/` - Built-in skills (memory, cron, github, tmux, weather, clawhub, summarize, skill-creator)
  - `templates/` - Prompt templates (AGENTS.md, SOUL.md, TOOLS.md, USER.md, HEARTBEAT.md)
  - `utils/` - Shared helpers
- `bridge/` - TypeScript WhatsApp bridge (Node.js)
- `web/` - Vue 3 + Naive UI frontend
- `tests/` - Pytest test suite (138 tests)

## Development Setup

```bash
python3.11 -m venv .venv        # or python3.12; 3.11+ required for oauth-cli-kit
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
```

Dev tools: `ruff` (lint/format), `pytest` (tests)

## Key Commands

```bash
# Lint
.venv/bin/ruff check .

# Format
.venv/bin/ruff format .

# Tests
.venv/bin/pytest tests/ -v

# Run CLI
.venv/bin/comobot --help
.venv/bin/comobot agent          # Interactive chat
.venv/bin/comobot gateway        # Start gateway (API + channels)
.venv/bin/comobot status         # Show status
.venv/bin/comobot onboard        # Initialize config
```

## Code Style

- Line length: 100 (ruff configured in pyproject.toml)
- Ruff rules: E, F, I, N, W (E501 ignored)
- Python >=3.11 required (oauth-cli-kit does not support 3.10)
- Build system: hatchling

## Config

- User config: `~/.comobot/config.json`
- Workspace: `~/.comobot/workspace/`
- Data dir: `~/.comobot/`
- Default gateway port: 18790

## Git Workflow

- Main branch: `main`
- Pre-commit hook runs ruff lint + format check automatically
- Remote: git@github.com:musenming/comobot.git

## Architecture Notes

- FastAPI shares asyncio loop with AgentLoop (uvicorn.Server embedded)
- SQLite with WAL mode for structured data (cron store, sessions, db layer)
- Orchestrator is optional on AgentLoop (no impact when not set)
- Config files + skill MDs stay as files (not in DB)
- LLM provider registry pattern: add ProviderSpec + config field to add new providers

## Notes

- `websockets>=16.0` requires Python >=3.10
- Matrix channel needs optional deps: `pip install -e ".[matrix]"`
- WhatsApp bridge needs Node.js >=18
- See `INSTALL.md` for full installation guide
