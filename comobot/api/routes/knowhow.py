"""Know-how CRUD and extraction API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from comobot.api.deps import get_current_user, get_db
from comobot.db.connection import Database

router = APIRouter(prefix="/api/knowhow")


class ExtractRequest(BaseModel):
    session_key: str
    message_ids: list[int]


class SaveRequest(BaseModel):
    preview: dict
    session_key: str
    message_ids: list[int]
    raw_messages: list[dict] | None = None


class UpdateRequest(BaseModel):
    title: str | None = None
    tags: list[str] | None = None
    status: str | None = None


def _get_store(db: Database):
    """Get or create KnowhowStore from app state."""
    from pathlib import Path

    from comobot.knowhow.store import KnowhowStore

    workspace = Path.home() / ".comobot" / "workspace"
    return KnowhowStore(workspace, db)


@router.post("/extract")
async def extract(
    req: ExtractRequest,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """Submit selected messages for LLM-based Know-how extraction preview."""
    # Fetch messages from DB
    if not req.message_ids:
        raise HTTPException(400, "message_ids cannot be empty")

    placeholders = ",".join("?" * len(req.message_ids))
    rows = await db.fetchall(
        f"SELECT id, role, content FROM messages WHERE id IN ({placeholders}) ORDER BY id",
        tuple(req.message_ids),
    )
    if not rows:
        raise HTTPException(404, "No messages found for given IDs")

    messages = [{"role": r["role"], "content": r["content"]} for r in rows]

    # Get the model from agent config if available
    from comobot.knowhow.extractor import extract_knowhow

    preview = await extract_knowhow(messages)
    return {
        "preview": preview,
        "raw_messages": messages,
    }


@router.post("")
async def create(
    req: SaveRequest,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """Confirm and save a Know-how entry."""
    store = _get_store(db)

    # If raw_messages not provided, fetch from DB
    raw_messages = req.raw_messages
    if not raw_messages and req.message_ids:
        placeholders = ",".join("?" * len(req.message_ids))
        rows = await db.fetchall(
            f"SELECT role, content FROM messages WHERE id IN ({placeholders}) ORDER BY id",
            tuple(req.message_ids),
        )
        raw_messages = [{"role": r["role"], "content": r["content"]} for r in rows or []]

    result = await store.create(
        preview=req.preview,
        raw_messages=raw_messages or [],
        source_session=req.session_key,
        message_ids=req.message_ids,
    )
    return result


@router.get("")
async def list_knowhow(
    status: str = "active",
    tags: str | None = None,
    sort: str = "updated_at",
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """List Know-how entries with optional filtering."""
    store = _get_store(db)
    tag_list = tags.split(",") if tags else None
    return await store.list_all(status=status, tags=tag_list, sort=sort)


@router.get("/{knowhow_id}")
async def get_knowhow(
    knowhow_id: str,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """Get a single Know-how entry."""
    store = _get_store(db)
    result = await store.get(knowhow_id)
    if not result:
        raise HTTPException(404, "Know-how not found")
    return result


@router.put("/{knowhow_id}")
async def update_knowhow(
    knowhow_id: str,
    req: UpdateRequest,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """Update a Know-how entry's title, tags, or status."""
    store = _get_store(db)
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(400, "No fields to update")
    result = await store.update(knowhow_id, **fields)
    if not result:
        raise HTTPException(404, "Know-how not found")
    return result


@router.delete("/{knowhow_id}")
async def delete_knowhow(
    knowhow_id: str,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """Delete a Know-how entry and its Markdown file."""
    store = _get_store(db)
    deleted = await store.delete(knowhow_id)
    if not deleted:
        raise HTTPException(404, "Know-how not found")
    return {"deleted": True}
