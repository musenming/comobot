"""Audit log and live log endpoints."""

import re
from pathlib import Path

from fastapi import APIRouter, Depends, Query

from comobot.api.deps import get_current_user, get_db
from comobot.db.connection import Database

router = APIRouter(prefix="/api/logs")

# Loguru format: 2026-03-22 16:24:29.918 | INFO     | module:func:line - message
_LOGURU_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)"  # timestamp
    r"\s*\|\s*(\w+)"  # level
    r"\s*\|\s*([\w.]+):(\w+):(\d+)"  # module:func:line
    r"\s*-\s*(.*)",  # message
)


def _get_log_dir() -> Path:
    log_dir = Path.home() / ".comobot" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


@router.get("")
async def get_logs(
    level: str | None = Query(None),
    module: str | None = Query(None),
    limit: int = Query(100, le=1000),
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    sql = "SELECT * FROM audit_log WHERE 1=1"
    params: list = []
    if level:
        sql += " AND level = ?"
        params.append(level)
    if module:
        sql += " AND module = ?"
        params.append(module)
    sql += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    return await db.fetchall(sql, tuple(params))


@router.get("/gateway")
async def get_gateway_logs(
    limit: int = Query(500, le=5000),
    search: str | None = Query(None),
    level: str | None = Query(None),
    _user: str = Depends(get_current_user),
):
    """Read and parse gateway.log file."""
    log_file = _get_log_dir() / "gateway.log"
    if not log_file.exists():
        return []

    # Read last N lines efficiently
    lines = log_file.read_text(errors="replace").splitlines()

    # Parse loguru-formatted lines and plain lines
    entries: list[dict] = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        m = _LOGURU_RE.match(raw)
        if m:
            entry = {
                "timestamp": m.group(1),
                "level": m.group(2).strip().lower(),
                "module": m.group(3),
                "func": m.group(4),
                "lineno": int(m.group(5)),
                "message": m.group(6),
                "raw": raw,
            }
        else:
            # Non-loguru line (e.g. startup banner, third-party output)
            entry = {
                "timestamp": "",
                "level": "info",
                "module": "",
                "func": "",
                "lineno": 0,
                "message": raw,
                "raw": raw,
            }
        entries.append(entry)

    # Apply filters
    if level:
        entries = [e for e in entries if e["level"] == level.lower()]
    if search:
        q = search.lower()
        entries = [e for e in entries if q in e["raw"].lower()]

    # Return last `limit` entries (newest at end)
    return entries[-limit:]
