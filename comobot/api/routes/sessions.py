"""Session and message viewing endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query

from comobot.api.deps import get_current_user, get_db
from comobot.db.connection import Database

router = APIRouter(prefix="/api/sessions")


def _compact_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.split())


def _clip(value: str, size: int) -> str:
    text = _compact_text(value)
    if len(text) <= size:
        return text
    return text[: size - 1].rstrip() + "…"


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


@router.get("/by-channel")
async def sessions_by_channel(
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """List sessions grouped by channel type."""
    rows = await db.fetchall("""
        SELECT
            s.id,
            s.session_key,
            s.created_at,
            s.updated_at,
            COUNT(m.id) AS message_count,
            au.alias AS chat_label
        FROM sessions s
        LEFT JOIN messages m ON m.session_id = s.id
        LEFT JOIN allowed_users au
            ON au.channel = SUBSTR(s.session_key, 1, INSTR(s.session_key, ':') - 1)
           AND au.user_id = SUBSTR(s.session_key, INSTR(s.session_key, ':') + 1)
        GROUP BY s.id
        ORDER BY s.updated_at DESC
    """)

    channels: dict[str, list] = {}
    for row in rows or []:
        key = row["session_key"]
        if ":" not in key:
            continue

        last_msg_row = await db.fetchone(
            "SELECT content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (row["id"],),
        )
        first_user_row = await db.fetchone(
            "SELECT content FROM messages "
            "WHERE session_id = ? AND role = 'user' AND LENGTH(TRIM(COALESCE(content, ''))) > 0 "
            "ORDER BY id ASC LIMIT 1",
            (row["id"],),
        )

        last_message_text = _compact_text(last_msg_row["content"] if last_msg_row else "")
        summary_source = (
            first_user_row["content"]
            if first_user_row and first_user_row["content"]
            else last_message_text
        )

        colon = key.index(":")
        ch_type = key[:colon]
        chat_id = key[colon + 1 :]
        channels.setdefault(ch_type, []).append(
            {
                "session_key": key,
                "chat_id": chat_id,
                "chat_label": row["chat_label"] or chat_id,
                "last_message_at": row["updated_at"],
                "message_count": row["message_count"],
                "summary": _clip(summary_source, 42) or (row["chat_label"] or chat_id),
                "last_message_preview": _clip(last_message_text, 72),
            }
        )

    display_names = {
        "telegram": "Telegram Bot",
        "feishu": "Feishu",
        "slack": "Slack",
        "dingtalk": "DingTalk",
        "discord": "Discord",
        "web": "Web Chat",
        "email": "Email",
        "matrix": "Matrix",
        "qq": "QQ",
        "whatsapp": "WhatsApp",
    }
    return {
        "channels": [
            {
                "channel_type": ct,
                "display_name": display_names.get(ct, ct.title()),
                "sessions": sessions,
            }
            for ct, sessions in channels.items()
        ]
    }


@router.get("/{session_key:path}/messages")
async def get_messages(
    session_key: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=0),
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    session = await db.fetchone("SELECT id FROM sessions WHERE session_key = ?", (session_key,))
    if not session:
        return []
    if limit > 0:
        # Fetch the *latest* N messages (sub-query DESC), then return in chronological order.
        return await db.fetchall(
            "SELECT * FROM ("
            "  SELECT id, role, content, tool_calls, tool_call_id, created_at "
            "  FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ? OFFSET ?"
            ") ORDER BY id",
            (session["id"], limit, offset),
        )
    return await db.fetchall(
        "SELECT id, role, content, tool_calls, tool_call_id, created_at "
        "FROM messages WHERE session_id = ? ORDER BY id",
        (session["id"],),
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
