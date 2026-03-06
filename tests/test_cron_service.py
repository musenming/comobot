import asyncio

import pytest

from comobot.cron.service import CronService
from comobot.cron.types import CronSchedule


@pytest.mark.asyncio
async def test_add_job_rejects_unknown_timezone(tmp_path) -> None:
    service = CronService(tmp_path / "cron" / "jobs.json")

    with pytest.raises(ValueError, match="unknown timezone 'America/Vancovuer'"):
        await service.add_job(
            name="tz typo",
            schedule=CronSchedule(kind="cron", expr="0 9 * * *", tz="America/Vancovuer"),
            message="hello",
        )

    assert await service.list_jobs(include_disabled=True) == []


@pytest.mark.asyncio
async def test_add_job_accepts_valid_timezone(tmp_path) -> None:
    service = CronService(tmp_path / "cron" / "jobs.json")

    job = await service.add_job(
        name="tz ok",
        schedule=CronSchedule(kind="cron", expr="0 9 * * *", tz="America/Vancouver"),
        message="hello",
    )

    assert job.schedule.tz == "America/Vancouver"
    assert job.state.next_run_at_ms is not None


@pytest.mark.asyncio
async def test_running_service_honors_external_disable(tmp_path) -> None:
    store_path = tmp_path / "cron" / "jobs.json"
    called: list[str] = []

    async def on_job(job) -> None:
        called.append(job.id)

    service = CronService(store_path, on_job=on_job)
    job = await service.add_job(
        name="external-disable",
        schedule=CronSchedule(kind="every", every_ms=500),
        message="hello",
    )
    # Disable externally before starting the service
    external = CronService(store_path)
    updated = await external.enable_job(job.id, enabled=False)
    assert updated is not None
    assert updated.enabled is False

    await service.start()
    try:
        await asyncio.sleep(0.6)
        assert called == []
    finally:
        service.stop()
