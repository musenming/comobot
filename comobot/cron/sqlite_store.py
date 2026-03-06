"""SQLite-backed storage for cron jobs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from loguru import logger

from comobot.cron.types import CronJob, CronJobState, CronPayload, CronSchedule, CronStore

if TYPE_CHECKING:
    from comobot.db.connection import Database


class SQLiteCronStore:
    """Stores cron jobs in SQLite instead of jobs.json."""

    def __init__(self, db: Database):
        self.db = db

    async def load(self) -> CronStore:
        """Load all cron jobs from SQLite."""
        rows = await self.db.fetchall("SELECT * FROM cron_jobs ORDER BY id")
        jobs: list[CronJob] = []
        for row in rows:
            try:
                schedule_data = json.loads(row["schedule"])
                payload_data = json.loads(row["payload"])
                jobs.append(
                    CronJob(
                        id=str(row["id"]),
                        name=row["name"],
                        enabled=bool(row["enabled"]),
                        schedule=CronSchedule(
                            kind=schedule_data.get("kind", "every"),
                            at_ms=schedule_data.get("atMs"),
                            every_ms=schedule_data.get("everyMs"),
                            expr=schedule_data.get("expr"),
                            tz=schedule_data.get("tz"),
                        ),
                        payload=CronPayload(
                            kind=payload_data.get("kind", "agent_turn"),
                            message=payload_data.get("message", ""),
                            deliver=payload_data.get("deliver", False),
                            channel=payload_data.get("channel"),
                            to=payload_data.get("to"),
                        ),
                        state=CronJobState(
                            next_run_at_ms=_parse_ms(row.get("next_run_at")),
                            last_run_at_ms=_parse_ms(row.get("last_run_at")),
                            last_status=row.get("last_status"),
                            last_error=row.get("last_error"),
                        ),
                        created_at_ms=_parse_ms(row.get("created_at")) or 0,
                        updated_at_ms=_parse_ms(row.get("created_at")) or 0,
                    )
                )
            except Exception as e:
                logger.warning("Failed to parse cron job row {}: {}", row.get("id"), e)
        return CronStore(jobs=jobs)

    async def save(self, store: CronStore) -> None:
        """Save all cron jobs to SQLite (full sync)."""
        # Get existing IDs
        existing = await self.db.fetchall("SELECT id FROM cron_jobs")
        existing_ids = {str(row["id"]) for row in existing}
        current_ids = {j.id for j in store.jobs}

        # Delete removed jobs
        for removed_id in existing_ids - current_ids:
            await self.db.execute("DELETE FROM cron_jobs WHERE id = ?", (int(removed_id),))

        # Upsert remaining jobs
        for job in store.jobs:
            schedule_json = json.dumps(
                {
                    "kind": job.schedule.kind,
                    "atMs": job.schedule.at_ms,
                    "everyMs": job.schedule.every_ms,
                    "expr": job.schedule.expr,
                    "tz": job.schedule.tz,
                }
            )
            payload_json = json.dumps(
                {
                    "kind": job.payload.kind,
                    "message": job.payload.message,
                    "deliver": job.payload.deliver,
                    "channel": job.payload.channel,
                    "to": job.payload.to,
                }
            )

            if job.id in existing_ids:
                await self.db.execute(
                    "UPDATE cron_jobs SET name=?, schedule=?, payload=?, enabled=?, "
                    "next_run_at=?, last_run_at=?, last_status=?, last_error=? "
                    "WHERE id=?",
                    (
                        job.name,
                        schedule_json,
                        payload_json,
                        int(job.enabled),
                        _format_ms(job.state.next_run_at_ms),
                        _format_ms(job.state.last_run_at_ms),
                        job.state.last_status,
                        job.state.last_error,
                        int(job.id),
                    ),
                )
            else:
                await self.db.execute(
                    "INSERT INTO cron_jobs (name, schedule, payload, enabled, "
                    "next_run_at, last_run_at, last_status, last_error) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        job.name,
                        schedule_json,
                        payload_json,
                        int(job.enabled),
                        _format_ms(job.state.next_run_at_ms),
                        _format_ms(job.state.last_run_at_ms),
                        job.state.last_status,
                        job.state.last_error,
                    ),
                )
                # Update the job id to the auto-generated SQLite id
                row = await self.db.fetchone(
                    "SELECT id FROM cron_jobs WHERE name=? ORDER BY id DESC LIMIT 1",
                    (job.name,),
                )
                if row:
                    job.id = str(row["id"])

    async def add_job(self, job: CronJob) -> str:
        """Insert a single job and return the new ID."""
        schedule_json = json.dumps(
            {
                "kind": job.schedule.kind,
                "atMs": job.schedule.at_ms,
                "everyMs": job.schedule.every_ms,
                "expr": job.schedule.expr,
                "tz": job.schedule.tz,
            }
        )
        payload_json = json.dumps(
            {
                "kind": job.payload.kind,
                "message": job.payload.message,
                "deliver": job.payload.deliver,
                "channel": job.payload.channel,
                "to": job.payload.to,
            }
        )
        cursor = await self.db.execute(
            "INSERT INTO cron_jobs (name, schedule, payload, enabled, "
            "next_run_at, last_run_at, last_status, last_error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job.name,
                schedule_json,
                payload_json,
                int(job.enabled),
                _format_ms(job.state.next_run_at_ms),
                _format_ms(job.state.last_run_at_ms),
                job.state.last_status,
                job.state.last_error,
            ),
        )
        return str(cursor.lastrowid)

    async def update_job(self, job: CronJob) -> None:
        """Update a single job in place."""
        schedule_json = json.dumps(
            {
                "kind": job.schedule.kind,
                "atMs": job.schedule.at_ms,
                "everyMs": job.schedule.every_ms,
                "expr": job.schedule.expr,
                "tz": job.schedule.tz,
            }
        )
        payload_json = json.dumps(
            {
                "kind": job.payload.kind,
                "message": job.payload.message,
                "deliver": job.payload.deliver,
                "channel": job.payload.channel,
                "to": job.payload.to,
            }
        )
        await self.db.execute(
            "UPDATE cron_jobs SET name=?, schedule=?, payload=?, enabled=?, "
            "next_run_at=?, last_run_at=?, last_status=?, last_error=? "
            "WHERE id=?",
            (
                job.name,
                schedule_json,
                payload_json,
                int(job.enabled),
                _format_ms(job.state.next_run_at_ms),
                _format_ms(job.state.last_run_at_ms),
                job.state.last_status,
                job.state.last_error,
                int(job.id),
            ),
        )

    async def remove_job(self, job_id: str) -> bool:
        """Delete a job by ID."""
        cursor = await self.db.execute("DELETE FROM cron_jobs WHERE id = ?", (int(job_id),))
        return cursor.rowcount > 0


def _parse_ms(value) -> int | None:
    """Parse a datetime string or timestamp to ms."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    # ISO datetime string from SQLite
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(str(value))
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def _format_ms(ms: int | None) -> str | None:
    """Format ms timestamp to ISO datetime string for SQLite."""
    if ms is None:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
