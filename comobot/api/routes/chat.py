"""Chat API endpoints for web-based conversation."""

import mimetypes
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from comobot.api.deps import get_current_user, get_db
from comobot.db.connection import Database

router = APIRouter(prefix="/api/chat")

# Upload config
UPLOAD_DIR = Path.home() / ".comobot" / "uploads"
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB per file
MAX_FILES_PER_REQUEST = 10
ALLOWED_EXTENSIONS = {
    # Documents
    ".txt", ".md", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".json", ".xml", ".yaml",
    ".yml", ".html", ".htm", ".rtf", ".log",
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico",
    # Code
    ".py", ".js", ".ts", ".jsx", ".tsx", ".vue", ".css", ".scss", ".java", ".go", ".rs",
    ".cpp", ".c", ".h", ".sh", ".sql",
    # Archives
    ".zip", ".tar", ".gz",
    # Audio
    ".mp3", ".wav", ".ogg", ".m4a", ".flac",
}

SESSION_PREFIX = "web:"


class ChatSendRequest(BaseModel):
    message: str
    session_id: str | None = None


@router.post("/upload")
async def upload_chat_files(
    files: List[UploadFile],
    _user: str = Depends(get_current_user),
):
    """Upload files for chat. Returns file metadata with URLs."""
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(400, f"Maximum {MAX_FILES_PER_REQUEST} files per upload")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    for file in files:
        # Validate extension
        ext = Path(file.filename or "").suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"File type '{ext}' not allowed: {file.filename}")

        # Read and validate size
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(400, f"File too large (max {MAX_FILE_SIZE // 1024 // 1024}MB): {file.filename}")

        # Generate unique filename
        file_id = uuid.uuid4().hex[:12]
        safe_name = Path(file.filename or "file").name  # strip path components
        stored_name = f"{file_id}_{safe_name}"
        file_path = UPLOAD_DIR / stored_name
        file_path.write_bytes(content)

        # Detect MIME type
        mime = file.content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"

        results.append({
            "id": file_id,
            "name": safe_name,
            "size": len(content),
            "type": mime,
            "url": f"/api/chat/files/{stored_name}",
        })

    return results


@router.get("/files/{filename:path}")
async def serve_chat_file(filename: str, _user: str = Depends(get_current_user)):
    """Serve an uploaded chat file."""
    from fastapi.responses import FileResponse

    file_path = (UPLOAD_DIR / filename).resolve()
    if not str(file_path).startswith(str(UPLOAD_DIR.resolve())):
        raise HTTPException(403, "Forbidden")
    if not file_path.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(file_path)


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
        await db.execute(
            "INSERT INTO sessions (session_key, platform) VALUES (?, 'web')", (session_key,)
        )
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
