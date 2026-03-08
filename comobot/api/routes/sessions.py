"""Session and message viewing endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query

from comobot.api.deps import get_current_user, get_db
from comobot.db.connection import Database

router = APIRouter(prefix="/api/sessions")


@router.get("")
async def list_sessions(
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    rows = await db.fetchall(
        "SELECT id, session_key, created_at, updated_at, last_consolidated "
        "FROM sessions ORDER BY updated_at DESC LIMIT 100"
    )
    results = []
    for row in rows or []:
        item = dict(row)
        msg_count = await db.fetchone(
            "SELECT COUNT(*) as c FROM messages WHERE session_id = ?",
            (row["id"],),
        )
        item["message_count"] = msg_count["c"] if msg_count else 0

        # Get channel from session_key pattern (e.g., "telegram:123")
        key = row["session_key"] or ""
        item["channel"] = key.split(":")[0] if ":" in key else ""

        # Preview: last message content
        last_msg = await db.fetchone(
            "SELECT content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (row["id"],),
        )
        preview = (last_msg["content"] or "")[:100] if last_msg else ""
        item["preview"] = preview
        results.append(item)
    return results


@router.get("/{session_key:path}/messages")
async def get_messages(
    session_key: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    session = await db.fetchone("SELECT id FROM sessions WHERE session_key = ?", (session_key,))
    if not session:
        return []
    return await db.fetchall(
        "SELECT id, role, content, tool_calls, tool_call_id, created_at "
        "FROM messages WHERE session_id = ? ORDER BY id LIMIT ? OFFSET ?",
        (session["id"], limit, offset),
    )


@router.get("/{session_key:path}")
async def get_session(
    session_key: str,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    session = await db.fetchone("SELECT * FROM sessions WHERE session_key = ?", (session_key,))
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    result = dict(session)
    msg_count = await db.fetchone(
        "SELECT COUNT(*) as c FROM messages WHERE session_id = ?",
        (session["id"],),
    )
    result["message_count"] = msg_count["c"] if msg_count else 0
    return result
