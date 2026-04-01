"""Task planning API endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from comobot.api.deps import get_current_user, get_db
from comobot.db.connection import Database

router = APIRouter(prefix="/api/plans")


@router.get("/{session_key:path}")
async def get_active_plan(
    session_key: str,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """Get the active plan for a session."""
    row = await db.fetchone(
        "SELECT * FROM task_plans WHERE session_key = ? "
        "AND status IN ('planning', 'executing') "
        "ORDER BY created_at DESC LIMIT 1",
        (session_key,),
    )
    if not row:
        return None
    result = dict(row)
    try:
        result["steps"] = json.loads(result.get("steps", "[]"))
    except (json.JSONDecodeError, TypeError):
        result["steps"] = []
    return result


@router.post("/{plan_id}/approve")
async def approve_plan(
    plan_id: str,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """Approve a plan for execution (when approval_required is enabled)."""
    row = await db.fetchone("SELECT * FROM task_plans WHERE id = ?", (plan_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Plan not found")
    if row["status"] != "planning":
        raise HTTPException(
            status_code=400, detail=f"Plan status is '{row['status']}', not 'planning'"
        )

    await db.execute(
        "UPDATE task_plans SET status = 'executing' WHERE id = ?",
        (plan_id,),
    )
    return {"id": plan_id, "status": "executing"}


@router.post("/{plan_id}/cancel")
async def cancel_plan(
    plan_id: str,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """Cancel an active plan."""
    row = await db.fetchone("SELECT * FROM task_plans WHERE id = ?", (plan_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Plan not found")
    if row["status"] in ("done", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Plan already {row['status']}")

    await db.execute(
        "UPDATE task_plans SET status = 'cancelled' WHERE id = ?",
        (plan_id,),
    )
    return {"id": plan_id, "status": "cancelled"}


class PlanListItem(BaseModel):
    id: str
    session_key: str
    goal: str
    status: str
    revision_count: int
    created_at: str
    completed_at: str | None


@router.get("")
async def list_plans(
    session_key: str | None = None,
    status: str | None = None,
    limit: int = 20,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """List task plans with optional filtering."""
    sql = "SELECT id, session_key, goal, status, revision_count, created_at, completed_at FROM task_plans"
    conditions: list[str] = []
    params: list = []

    if session_key:
        conditions.append("session_key = ?")
        params.append(session_key)
    if status:
        conditions.append("status = ?")
        params.append(status)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = await db.fetchall(sql, tuple(params))
    return [dict(r) for r in rows] if rows else []
