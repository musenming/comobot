"""Chat API endpoints for web-based conversation."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from comobot.api.deps import get_current_user, get_db
from comobot.db.connection import Database

router = APIRouter(prefix="/api/chat")

SESSION_PREFIX = "web:"


class ChatSendRequest(BaseModel):
    message: str
    session_id: str | None = None


@router.get("/sessions")
async def list_chat_sessions(
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """List web chat sessions."""
    rows = await db.fetchall(
        "SELECT id, session_key, created_at, updated_at "
        "FROM sessions WHERE session_key LIKE ? ORDER BY updated_at DESC LIMIT 50",
        (f"{SESSION_PREFIX}%",),
    )
    results = []
    for row in rows or []:
        item = dict(row)
        msg_count = await db.fetchone(
            "SELECT COUNT(*) as c FROM messages WHERE session_id = ?",
            (row["id"],),
        )
        item["message_count"] = msg_count["c"] if msg_count else 0

        # Preview: last user message
        last_msg = await db.fetchone(
            "SELECT content FROM messages WHERE session_id = ? AND role = 'user' "
            "ORDER BY id DESC LIMIT 1",
            (row["id"],),
        )
        item["preview"] = (last_msg["content"] or "")[:80] if last_msg else ""

        # Title: first user message
        first_msg = await db.fetchone(
            "SELECT content FROM messages WHERE session_id = ? AND role = 'user' "
            "ORDER BY id ASC LIMIT 1",
            (row["id"],),
        )
        item["title"] = (first_msg["content"] or "")[:60] if first_msg else "New Chat"
        results.append(item)
    return results


@router.get("/sessions/{session_key}/messages")
async def get_chat_messages(
    session_key: str,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """Get messages for a web chat session."""
    full_key = (
        f"{SESSION_PREFIX}{session_key}"
        if not session_key.startswith(SESSION_PREFIX)
        else session_key
    )
    session = await db.fetchone("SELECT id FROM sessions WHERE session_key = ?", (full_key,))
    if not session:
        return []
    return await db.fetchall(
        "SELECT id, role, content, tool_calls, created_at "
        "FROM messages WHERE session_id = ? ORDER BY id",
        (session["id"],),
    )


@router.post("/send")
async def send_message(
    req: ChatSendRequest,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """Send a message and get a response (non-streaming fallback)."""

    session_key = req.session_id or f"{SESSION_PREFIX}{uuid.uuid4().hex[:12]}"
    if not session_key.startswith(SESSION_PREFIX):
        session_key = f"{SESSION_PREFIX}{session_key}"

    # Create session if not exists
    session = await db.fetchone("SELECT id FROM sessions WHERE session_key = ?", (session_key,))
    if not session:
        await db.execute("INSERT INTO sessions (session_key) VALUES (?)", (session_key,))
        session = await db.fetchone("SELECT id FROM sessions WHERE session_key = ?", (session_key,))

    # Store user message
    await db.execute(
        "INSERT INTO messages (session_id, role, content) VALUES (?, 'user', ?)",
        (session["id"], req.message),
    )

    return {
        "session_key": session_key,
        "status": "queued",
    }


@router.delete("/sessions/{session_key}")
async def delete_chat_session(
    session_key: str,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """Delete a web chat session and its messages."""
    full_key = (
        f"{SESSION_PREFIX}{session_key}"
        if not session_key.startswith(SESSION_PREFIX)
        else session_key
    )
    session = await db.fetchone("SELECT id FROM sessions WHERE session_key = ?", (full_key,))
    if session:
        await db.execute("DELETE FROM messages WHERE session_id = ?", (session["id"],))
        await db.execute("DELETE FROM sessions WHERE id = ?", (session["id"],))
    return {"ok": True}
