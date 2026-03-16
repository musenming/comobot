"""System settings endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from comobot.api.deps import get_auth, get_current_user
from comobot.config.loader import load_config, save_config
from comobot.security.auth import AuthManager

router = APIRouter(prefix="/api/settings")

DATA_DIR = Path.home() / ".comobot"


class ChangePasswordRequest(BaseModel):
    new_password: str


class FileContentRequest(BaseModel):
    content: str


class DefaultsUpdate(BaseModel):
    model: str | None = None
    provider: str | None = None


class QMDSettingsUpdate(BaseModel):
    enabled: bool


@router.get("")
async def get_settings(_user: str = Depends(get_current_user)):
    return {"version": "0.1.0", "status": "running"}


@router.put("/password")
async def change_password(
    body: ChangePasswordRequest,
    auth: AuthManager = Depends(get_auth),
    username: str = Depends(get_current_user),
):
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    await auth.change_password(username, body.new_password)
    return {"updated": True}


# --- Agent config files ---


def _read_file(name: str) -> str:
    path = DATA_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _write_file(name: str, content: str) -> None:
    path = DATA_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@router.get("/agent")
async def get_agent_settings(_user: str = Depends(get_current_user)):
    return {
        "soul": _read_file("SOUL.md"),
        "user": _read_file("USER.md"),
    }


@router.put("/agent")
async def update_agent_settings(
    body: dict,
    _user: str = Depends(get_current_user),
):
    if "soul" in body:
        _write_file("SOUL.md", body["soul"])
    if "user" in body:
        _write_file("USER.md", body["user"])
    return {"updated": True}


@router.get("/soul")
async def get_soul(_user: str = Depends(get_current_user)):
    return {"content": _read_file("SOUL.md")}


@router.put("/soul")
async def update_soul(
    body: FileContentRequest,
    _user: str = Depends(get_current_user),
):
    _write_file("SOUL.md", body.content)
    return {"updated": True}


@router.get("/user")
async def get_user_md(_user: str = Depends(get_current_user)):
    return {"content": _read_file("USER.md")}


@router.put("/user")
async def update_user_md(
    body: FileContentRequest,
    _user: str = Depends(get_current_user),
):
    _write_file("USER.md", body.content)
    return {"updated": True}


@router.get("/agents")
async def get_agents_md(_user: str = Depends(get_current_user)):
    return {"content": _read_file("AGENTS.md")}


@router.put("/agents")
async def update_agents_md(
    body: FileContentRequest,
    _user: str = Depends(get_current_user),
):
    _write_file("AGENTS.md", body.content)
    return {"updated": True}


@router.get("/memory")
async def get_memory(_user: str = Depends(get_current_user)):
    return {"content": _read_file("workspace/MEMORY.md")}


@router.delete("/memory")
async def clear_memory(_user: str = Depends(get_current_user)):
    path = DATA_DIR / "workspace" / "MEMORY.md"
    if path.exists():
        path.write_text("# Memory\n\n", encoding="utf-8")
    return {"cleared": True}


@router.get("/defaults")
async def get_defaults(_user: str = Depends(get_current_user)):
    config = load_config()
    d = config.agents.defaults
    return {"model": d.model, "provider": d.provider}


@router.put("/defaults")
async def update_defaults(
    body: DefaultsUpdate,
    _user: str = Depends(get_current_user),
):
    config = load_config()
    if body.model is not None:
        config.agents.defaults.model = body.model
    if body.provider is not None:
        config.agents.defaults.provider = body.provider
    save_config(config)
    return {"updated": True}


# --- QMD Memory Search Backend ---


def _get_memory_backend(request: Request):
    """Get memory backend from the agent loop instance in app state."""
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        return None
    return getattr(agent, "_memory_backend", None)


@router.get("/qmd")
async def get_qmd_settings(
    request: Request,
    _user: str = Depends(get_current_user),
):
    """Get QMD status and configuration."""
    config = load_config()
    qmd_config = config.agents.defaults.memory.qmd

    # Determine running state from live backend if available
    state = "stopped"
    error = None
    backend = _get_memory_backend(request)
    if backend is not None:
        from comobot.agent.memory_backend import FallbackBackend

        if isinstance(backend, FallbackBackend):
            if backend.primary_active:
                state = "running"
            elif getattr(backend, "_starting", False):
                state = "starting"
            elif getattr(backend, "_start_error", None):
                state = "error"
                error = backend._start_error
                # Clear error after reading
                backend._start_error = None

    result = {
        "enabled": qmd_config.enabled,
        "mode": qmd_config.mode,
        "status": {
            "state": state,
            "model_memory_mb": 1200 if state == "running" else 0,
        },
    }
    if error:
        result["error"] = error
    return result


@router.put("/qmd")
async def update_qmd_settings(
    body: QMDSettingsUpdate,
    request: Request,
    _user: str = Depends(get_current_user),
):
    """Toggle QMD on/off with hot-swap.

    Enable is async: returns immediately with state='starting',
    initialization runs in background. Poll GET /qmd for status.
    Disable is synchronous (fast).
    """
    import asyncio

    from loguru import logger

    from comobot.agent.memory_backend import FallbackBackend

    config = load_config()
    config.agents.defaults.memory.qmd.enabled = body.enabled
    save_config(config)

    backend = _get_memory_backend(request)
    if backend is None:
        logger.warning("QMD toggle: no memory backend available")
        return {"ok": False, "error": "Memory backend not available", "state": "stopped"}

    if not isinstance(backend, FallbackBackend):
        logger.warning("QMD toggle: backend is not FallbackBackend, cannot hot-swap")
        return {"ok": False, "error": "Hot-swap not supported", "state": "stopped"}

    if body.enabled:
        # Mark as starting immediately, initialize in background
        backend._starting = True
        logger.info("QMD toggle: starting initialization in background...")

        async def _enable_bg():
            try:
                await backend.enable_primary()
                logger.info("QMD toggle: primary backend enabled successfully")
            except Exception as e:
                logger.error("QMD toggle failed: {}", e)
                backend._start_error = str(e)
            finally:
                backend._starting = False

        asyncio.create_task(_enable_bg())
        return {"ok": True, "state": "starting"}
    else:
        try:
            logger.info("QMD toggle: disabling primary backend...")
            await backend.disable_primary()
            logger.info("QMD toggle: primary backend disabled")
            return {"ok": True, "state": "stopped"}
        except Exception as e:
            logger.error("QMD toggle failed: {}", e)
            raise HTTPException(status_code=500, detail=f"QMD toggle failed: {e}")


@router.post("/qmd/reindex")
async def reindex_qmd(
    request: Request,
    _user: str = Depends(get_current_user),
):
    """Manually trigger QMD reindex."""
    backend = _get_memory_backend(request)
    if backend is None:
        raise HTTPException(status_code=503, detail="Memory backend not available")
    try:
        await backend.reindex()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reindex failed: {e}")
    return {"ok": True}
