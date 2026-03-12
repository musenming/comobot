"""Cron job management endpoints."""

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from comobot.api.deps import get_current_user

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


def _get_cron_service(request: Request):
    """Get the CronService from app state."""
    cron = getattr(request.app.state, "cron", None)
    if cron is None:
        raise HTTPException(status_code=503, detail="Cron service not available")
    return cron


def _format_schedule_display(schedule) -> str:
    """Format schedule for frontend display."""
    if schedule.kind == "cron" and schedule.expr:
        return schedule.expr
    elif schedule.kind == "at" and schedule.at_ms:
        return datetime.fromtimestamp(schedule.at_ms / 1000, tz=timezone.utc).isoformat()
    elif schedule.kind == "every" and schedule.every_ms:
        sec = schedule.every_ms / 1000
        if sec < 60:
            return f"every {int(sec)}s"
        elif sec < 3600:
            return f"every {int(sec / 60)}m"
        else:
            return f"every {int(sec / 3600)}h"
    return ""


def _format_next_run(next_run_at_ms: int | None) -> str | None:
    """Convert next_run_at_ms to ISO string for frontend."""
    if next_run_at_ms is None:
        return None
    return datetime.fromtimestamp(next_run_at_ms / 1000, tz=timezone.utc).isoformat()


def _format_last_run(last_run_at_ms: int | None) -> str | None:
    """Convert last_run_at_ms to ISO string for frontend."""
    if last_run_at_ms is None:
        return None
    return datetime.fromtimestamp(last_run_at_ms / 1000, tz=timezone.utc).isoformat()


def _job_to_dict(job) -> dict:
    """Convert a CronJob to a frontend-friendly dict."""
    return {
        "id": job.id,
        "name": job.name,
        "enabled": job.enabled,
        "schedule": {
            "kind": job.schedule.kind,
            "expr": job.schedule.expr,
            "atMs": job.schedule.at_ms,
            "everyMs": job.schedule.every_ms,
            "tz": job.schedule.tz,
        },
        "schedule_display": _format_schedule_display(job.schedule),
        "payload": {
            "kind": job.payload.kind,
            "message": job.payload.message,
            "deliver": job.payload.deliver,
            "channel": job.payload.channel,
            "to": job.payload.to,
        },
        "payload_summary": job.payload.message,
        "next_run_at": _format_next_run(job.state.next_run_at_ms),
        "last_run_at": _format_last_run(job.state.last_run_at_ms),
        "last_status": job.state.last_status,
        "last_error": job.state.last_error,
        "created_at": datetime.fromtimestamp(
            job.created_at_ms / 1000, tz=timezone.utc
        ).isoformat()
        if job.created_at_ms
        else None,
    }


@router.get("")
async def list_cron_jobs(
    request: Request,
    _user: str = Depends(get_current_user),
):
    cron = _get_cron_service(request)
    jobs = await cron.list_jobs(include_disabled=True)
    results = [_job_to_dict(job) for job in jobs]
    # Sort: enabled + pending jobs first ("online"), completed/disabled last ("offline")
    results.sort(key=lambda j: (
        0 if j["enabled"] and j.get("next_run_at") else 1,
        j.get("next_run_at") or "",
    ))
    return results


@router.post("")
async def create_cron_job(
    body: CronCreate,
    request: Request,
    _user: str = Depends(get_current_user),
):
    from comobot.cron.types import CronSchedule

    cron = _get_cron_service(request)
    schedule = CronSchedule(kind="cron", expr=body.expression)
    job = await cron.add_job(
        name=body.name,
        schedule=schedule,
        message=body.command,
    )
    return {"id": job.id, "name": job.name}


@router.put("/{job_id}")
async def update_cron_job(
    job_id: str,
    body: CronUpdate,
    request: Request,
    _user: str = Depends(get_current_user),
):
    cron = _get_cron_service(request)
    # Load the job, update fields, and save
    jobs = await cron.list_jobs(include_disabled=True)
    target = None
    for j in jobs:
        if str(j.id) == str(job_id):
            target = j
            break
    if not target:
        raise HTTPException(status_code=404, detail="Cron job not found")

    if body.name is not None:
        target.name = body.name
    if body.expression is not None:
        from comobot.cron.types import CronSchedule

        target.schedule = CronSchedule(kind="cron", expr=body.expression)
    if body.command is not None:
        target.payload.message = body.command

    target.updated_at_ms = int(time.time() * 1000)
    await cron._save_store()
    return {"id": job_id, "updated": True}


@router.post("/{job_id}/run")
async def manual_run(
    job_id: str,
    request: Request,
    _user: str = Depends(get_current_user),
):
    cron = _get_cron_service(request)
    success = await cron.run_job(str(job_id), force=True)
    if not success:
        raise HTTPException(status_code=404, detail="Cron job not found")
    return {"id": job_id, "status": "triggered"}


@router.put("/{job_id}/toggle")
async def toggle_cron_job(
    job_id: str,
    request: Request,
    _user: str = Depends(get_current_user),
):
    cron = _get_cron_service(request)
    jobs = await cron.list_jobs(include_disabled=True)
    target = None
    for j in jobs:
        if str(j.id) == str(job_id):
            target = j
            break
    if not target:
        raise HTTPException(status_code=404, detail="Cron job not found")

    new_state = not target.enabled
    result = await cron.enable_job(str(job_id), new_state)
    if not result:
        raise HTTPException(status_code=404, detail="Cron job not found")
    return {"id": job_id, "enabled": new_state}


@router.delete("/{job_id}")
async def delete_cron_job(
    job_id: str,
    request: Request,
    _user: str = Depends(get_current_user),
):
    cron = _get_cron_service(request)
    removed = await cron.remove_job(str(job_id))
    if not removed:
        raise HTTPException(status_code=404, detail="Cron job not found")
    return {"deleted": True}
