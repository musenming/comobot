"""Dashboard API endpoint."""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from comobot.api.deps import get_current_user, get_db
from comobot.db.connection import Database

router = APIRouter(prefix="/api")


class WorkflowBrief(BaseModel):
    id: int
    name: str
    enabled: bool = True
    last_run_at: Optional[str] = None


class CronWarning(BaseModel):
    id: str
    name: str
    status: str = "ok"
    last_run_at: Optional[str] = None
    last_status: str = "ok"


class DashboardResponse(BaseModel):
    total_sessions: int = 0
    total_messages: int = 0
    total_workflows: int = 0
    active_workflows: int = 0
    cron_jobs: int = 0
    recent_errors: int = 0
    message_trend: list[int] = []
    running_workflows: list[WorkflowBrief] = []
    cron_warnings: list[CronWarning] = []


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    sessions = await db.fetchone("SELECT COUNT(*) as c FROM sessions")
    messages = await db.fetchone("SELECT COUNT(*) as c FROM messages")
    workflows = await db.fetchone("SELECT COUNT(*) as c FROM workflows")
    active_wf = await db.fetchone("SELECT COUNT(*) as c FROM workflows WHERE enabled = 1")
    cron = await db.fetchone("SELECT COUNT(*) as c FROM cron_jobs")
    errors = await db.fetchone(
        "SELECT COUNT(*) as c FROM audit_log WHERE level = 'error' "
        "AND timestamp > datetime('now', '-24 hours')"
    )

    # 7-day message trend
    message_trend = []
    for i in range(6, -1, -1):
        row = await db.fetchone(
            "SELECT COUNT(*) as c FROM messages "
            "WHERE created_at > datetime('now', ?) AND created_at <= datetime('now', ?)",
            (f"-{i + 1} days", f"-{i} days"),
        )
        message_trend.append(row["c"] if row else 0)

    # Running workflows
    running_workflows = []
    wf_rows = await db.fetchall(
        "SELECT id, name, enabled FROM workflows WHERE enabled = 1 ORDER BY updated_at DESC LIMIT 10"
    )
    for wf in wf_rows or []:
        last_run = await db.fetchone(
            "SELECT started_at FROM workflow_runs WHERE workflow_id = ? "
            "ORDER BY started_at DESC LIMIT 1",
            (wf["id"],),
        )
        running_workflows.append(
            WorkflowBrief(
                id=wf["id"],
                name=wf["name"],
                enabled=bool(wf["enabled"]),
                last_run_at=last_run["started_at"] if last_run else None,
            )
        )

    # Cron warnings
    cron_warnings = []
    cron_rows = await db.fetchall(
        "SELECT id, name, enabled, last_run_at, last_status FROM cron_jobs ORDER BY last_run_at DESC LIMIT 10"
    )
    for cj in cron_rows or []:
        status = "ok"
        if not cj.get("enabled"):
            status = "disabled"
        elif cj.get("last_status") == "failed":
            status = "failed"
        cron_warnings.append(
            CronWarning(
                id=str(cj["id"]),
                name=cj["name"],
                status=status,
                last_run_at=cj.get("last_run_at"),
                last_status=cj.get("last_status", "ok"),
            )
        )

    return DashboardResponse(
        total_sessions=sessions["c"] if sessions else 0,
        total_messages=messages["c"] if messages else 0,
        total_workflows=workflows["c"] if workflows else 0,
        active_workflows=active_wf["c"] if active_wf else 0,
        cron_jobs=cron["c"] if cron else 0,
        recent_errors=errors["c"] if errors else 0,
        message_trend=message_trend,
        running_workflows=running_workflows,
        cron_warnings=cron_warnings,
    )
