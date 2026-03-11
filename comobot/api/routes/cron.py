"""Cron job management endpoints."""

import json

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
    rows = await db.fetchall("SELECT * FROM cron_jobs ORDER BY created_at DESC")
    results = []
    for row in rows:
        item = dict(row)
        # Parse schedule and payload JSON for frontend display
        try:
            sched = json.loads(row["schedule"]) if isinstance(row["schedule"], str) else {}
        except (json.JSONDecodeError, TypeError):
            sched = {}
        try:
            payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else {}
        except (json.JSONDecodeError, TypeError):
            payload = {}

        # Provide a schedule_display for the frontend
        if sched.get("kind") == "cron" and sched.get("expr"):
            item["schedule_display"] = sched["expr"]
        elif sched.get("kind") == "at" and sched.get("atMs"):
            from datetime import datetime, timezone

            item["schedule_display"] = datetime.fromtimestamp(
                sched["atMs"] / 1000, tz=timezone.utc
            ).isoformat()
        elif sched.get("kind") == "every" and sched.get("everyMs"):
            sec = sched["everyMs"] / 1000
            if sec < 60:
                item["schedule_display"] = f"every {int(sec)}s"
            elif sec < 3600:
                item["schedule_display"] = f"every {int(sec / 60)}m"
            else:
                item["schedule_display"] = f"every {int(sec / 3600)}h"
        else:
            item["schedule_display"] = row.get("schedule", "")

        # Provide payload summary
        item["payload_summary"] = payload.get("message", "")
        results.append(item)
    return results


@router.post("")
async def create_cron_job(
    body: CronCreate,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    # Build schedule and payload JSON from user-friendly fields
    schedule_json = json.dumps({"kind": "cron", "expr": body.expression})
    payload_json = json.dumps(
        {
            "kind": "agent_turn",
            "message": body.command,
            "deliver": False,
        }
    )
    cursor = await db.execute(
        "INSERT INTO cron_jobs (name, schedule, payload) VALUES (?, ?, ?)",
        (body.name, schedule_json, payload_json),
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
        schedule_json = json.dumps({"kind": "cron", "expr": body.expression})
        updates.append("schedule = ?")
        params.append(schedule_json)
    if body.command is not None:
        payload_json = json.dumps(
            {
                "kind": "agent_turn",
                "message": body.command,
                "deliver": False,
            }
        )
        updates.append("payload = ?")
        params.append(payload_json)

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
