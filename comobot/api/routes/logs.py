"""Audit log and live log endpoints."""

from fastapi import APIRouter, Depends, Query

from comobot.api.deps import get_current_user, get_db
from comobot.db.connection import Database

router = APIRouter(prefix="/api/logs")


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
