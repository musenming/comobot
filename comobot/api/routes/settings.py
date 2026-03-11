"""System settings endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
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
