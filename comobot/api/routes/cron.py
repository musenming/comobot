"""Cron job management endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from comobot.api.deps import get_current_user, get_db
from comobot.db.connection import Database

router = APIRouter(prefix="/api/cron")


class CronCreate(BaseModel):
    name: str
    expression: str
    command: str
    description: str = ""


class CronUpdate(BaseModel):
    name: str | None = None
    expression: str | None = None
    command: str | None = None
    description: str | None = None


@router.get("")
async def list_cron_jobs(
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    return await db.fetchall("SELECT * FROM cron_jobs ORDER BY created_at DESC")


@router.post("")
async def create_cron_job(
    body: CronCreate,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    cursor = await db.execute(
        "INSERT INTO cron_jobs (name, expression, command, description) VALUES (?, ?, ?, ?)",
        (body.name, body.expression, body.command, body.description),
    )
    return {"id": cursor.lastrowid, "name": body.name}


@router.put("/{job_id}")
async def update_cron_job(
    job_id: int,
    body: CronUpdate,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    updates = []
    params = []
    if body.name is not None:
        updates.append("name = ?")
        params.append(body.name)
    if body.expression is not None:
        updates.append("expression = ?")
        params.append(body.expression)
    if body.command is not None:
        updates.append("command = ?")
        params.append(body.command)
    if body.description is not None:
        updates.append("description = ?")
        params.append(body.description)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    params.append(job_id)
    await db.execute(f"UPDATE cron_jobs SET {', '.join(updates)} WHERE id = ?", tuple(params))
    return {"id": job_id, "updated": True}


@router.post("/{job_id}/run")
async def manual_run(
    job_id: int,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    job = await db.fetchone("SELECT * FROM cron_jobs WHERE id = ?", (job_id,))
    if not job:
        raise HTTPException(status_code=404, detail="Cron job not found")
    # Mark as manually triggered
    await db.execute(
        "UPDATE cron_jobs SET last_run_at = datetime('now'), last_status = 'running' WHERE id = ?",
        (job_id,),
    )
    return {"id": job_id, "status": "triggered"}


@router.put("/{job_id}/toggle")
async def toggle_cron_job(
    job_id: int,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    job = await db.fetchone("SELECT enabled FROM cron_jobs WHERE id = ?", (job_id,))
    if not job:
        raise HTTPException(status_code=404, detail="Cron job not found")
    new_state = 0 if job["enabled"] else 1
    await db.execute("UPDATE cron_jobs SET enabled = ? WHERE id = ?", (new_state, job_id))
    return {"id": job_id, "enabled": bool(new_state)}


@router.delete("/{job_id}")
async def delete_cron_job(
    job_id: int,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    await db.execute("DELETE FROM cron_jobs WHERE id = ?", (job_id,))
    return {"deleted": True}
