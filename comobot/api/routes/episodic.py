"""Episodic memory API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from comobot.api.deps import get_current_user, get_db
from comobot.db.connection import Database

router = APIRouter(prefix="/api/memory/episodic")


def _get_store(db: Database):
    """Build an EpisodicMemoryStore from the DB."""
    from pathlib import Path

    from comobot.agent.episodic.store import EpisodicMemoryStore

    workspace = Path.home() / ".comobot" / "workspace"
    return EpisodicMemoryStore(workspace, db)


@router.get("/stats")
async def episodic_stats(
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """Get episodic memory statistics."""
    store = _get_store(db)
    return await store.stats()


@router.get("")
async def list_episodic_memories(
    type: str | None = Query(None, description="Filter by type: task/fact/preference/feedback"),
    status: str = Query("active", description="Filter by status: active/archived/merged"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """List episodic memories with optional filtering."""
    store = _get_store(db)
    return await store.list_all(
        type_filter=type,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get("/{memory_id}")
async def get_episodic_memory(
    memory_id: str,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """Get a single episodic memory by ID."""
    store = _get_store(db)
    result = await store.get(memory_id)
    if not result:
        raise HTTPException(status_code=404, detail="Memory not found")
    return result


class MemoryUpdateBody(BaseModel):
    content: str | None = None
    tags: list[str] | None = None


@router.put("/{memory_id}")
async def update_episodic_memory(
    memory_id: str,
    body: MemoryUpdateBody,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """Update an episodic memory's content or tags."""
    store = _get_store(db)
    existing = await store.get(memory_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Memory not found")

    updated = await store.update(memory_id, content=body.content, tags=body.tags)
    if not updated:
        raise HTTPException(status_code=400, detail="No fields to update")
    return {"id": memory_id, "updated": True}


@router.delete("/{memory_id}")
async def delete_episodic_memory(
    memory_id: str,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """Archive (soft-delete) an episodic memory."""
    store = _get_store(db)
    existing = await store.get(memory_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Memory not found")

    await store.delete(memory_id)
    return {"id": memory_id, "status": "archived"}
