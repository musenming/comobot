# comobot

Lightweight personal AI assistant framework with multi-channel support.

## Project Structure

> 详细结构见 [`structure.md`](structure.md)

- `comobot/` - Core Python package (93 files, ~17K lines)
  - `agent/` - Agent loop, context, memory, memory_search, skills, subagent, tools/
  - `api/` - FastAPI REST API + WebSocket (`app.py`, `deps.py`, `routes/`)
  - `bus/` - Event bus and async queue
  - `channels/` - 11 chat integrations (Telegram, Slack, DingTalk, Feishu, Discord, QQ, Email, Matrix, WhatsApp, Mochat)
  - `cli/` - CLI entry point (`comobot` command via Typer)
  - `config/` - Config schema (Pydantic) and loader
  - `cron/` - Scheduled tasks (SQLite store)
  - `db/` - Database layer (SQLite + WAL, versioned migrations)
  - `heartbeat/` - Proactive wake-up service
  - `knowhow/` - Know-how experience learning system (store, extractor, LLM-based extraction)
  - `orchestrator/` - Optional workflow orchestration on AgentLoop
  - `providers/` - LLM providers (litellm, openai-codex, custom, key rotator, transcription)
  - `security/` - JWT auth, AES-GCM encryption
  - `session/` - Session management (SQLite backend)
  - `skills/` - 9 built-in skills (memory, cron, github, tmux, weather, clawhub, skill-vetter, summarize, skill-creator)
  - `templates/` - Prompt templates (AGENTS, SOUL, TOOLS, USER, IDENTITY, BOOTSTRAP, HEARTBEAT)
  - `utils/` - Shared helpers + migration tools
- `web/` - Vue 3 + Naive UI frontend (42 files: 14 views, 19 components, stores, composables)
- `bridge/` - TypeScript WhatsApp bridge (Node.js)
- `tests/` - Pytest test suite (21 files)

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

## Skills

- Frontend Design skill: see [`skills/frontend-design-3/SKILL.md`](skills/frontend-design-3/SKILL.md) — follow these guidelines when building or modifying web frontend components

## Notes

- `websockets>=16.0` requires Python >=3.10
- Matrix channel needs optional deps: `pip install -e ".[matrix]"`
- WhatsApp bridge needs Node.js >=18
- See `INSTALL.md` for full installation guide
