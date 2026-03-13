"""FastAPI application factory for comobot."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from comobot.db.connection import Database
from comobot.security.auth import AuthManager
from comobot.security.crypto import CredentialVault


def create_app(
    db: Database,
    vault: CredentialVault | None = None,
    auth: AuthManager | None = None,
    **kwargs,
) -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="comobot",
        description="Comobot Web Control Panel API",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Store shared state
    app.state.db = db
    app.state.vault = vault
    app.state.auth = auth

    # Store extra kwargs (agent, channels, bus, etc.)
    for key, value in kwargs.items():
        setattr(app.state, key, value)

    # Register routes
    from comobot.api.routes.auth import router as auth_router
    from comobot.api.routes.channels import router as channels_router
    from comobot.api.routes.chat import router as chat_router
    from comobot.api.routes.cron import router as cron_router
    from comobot.api.routes.dashboard import router as dashboard_router
    from comobot.api.routes.health import router as health_router
    from comobot.api.routes.knowhow import router as knowhow_router
    from comobot.api.routes.logs import router as logs_router
    from comobot.api.routes.providers import router as providers_router
    from comobot.api.routes.sessions import router as sessions_router
    from comobot.api.routes.settings import router as settings_router
    from comobot.api.routes.setup import router as setup_router
    from comobot.api.routes.skills import router as skills_router
    from comobot.api.routes.webhook import router as webhook_router
    from comobot.api.routes.workflows import router as workflows_router
    from comobot.api.routes.ws import router as ws_router

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(chat_router)
    app.include_router(setup_router)
    app.include_router(webhook_router)
    app.include_router(dashboard_router)
    app.include_router(workflows_router)
    app.include_router(providers_router)
    app.include_router(sessions_router)
    app.include_router(knowhow_router)
    app.include_router(channels_router)
    app.include_router(cron_router)
    app.include_router(logs_router)
    app.include_router(settings_router)
    app.include_router(skills_router)
    app.include_router(ws_router)

    # Serve Vue frontend static files if built
    static_dir = None
    candidates = [
        Path(__file__).parent.parent / "web" / "dist",
        Path(__file__).parent.parent.parent / "web" / "dist",
    ]
    # PyInstaller bundles assets under sys._MEIPASS
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.insert(0, Path(meipass) / "web" / "dist")
    for candidate in candidates:
        if candidate.exists():
            static_dir = candidate
            break
    if static_dir:
        # SPA catch-all: serve index.html for non-API, non-static paths
        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404)
            # Try serving as a static file first
            file_path = static_dir / full_path
            if full_path and file_path.is_file():
                return FileResponse(file_path)
            index = static_dir / "index.html"
            if index.exists():
                return FileResponse(index)
            raise HTTPException(status_code=404)

        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app
