"""Tests for SQLite storage layer."""

import pytest

from comobot.db.connection import Database
from comobot.db.migrations import run_migrations


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    await run_migrations(database)
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_connection_and_wal_mode(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    row = await database.fetchone("PRAGMA journal_mode")
    assert row["journal_mode"] == "wal"
    await database.close()


@pytest.mark.asyncio
async def test_migrations_create_tables(db):
    tables = await db.fetchall("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    table_names = {t["name"] for t in tables}
    expected = {
        "admin",
        "sessions",
        "messages",
        "workflows",
        "workflow_runs",
        "cron_jobs",
        "credentials",
        "allowed_users",
        "audit_log",
        "schema_version",
    }
    assert expected.issubset(table_names)


@pytest.mark.asyncio
async def test_migrations_idempotent(db):
    await run_migrations(db)
    row = await db.fetchone("SELECT COUNT(*) as c FROM schema_version")
    assert row["c"] == 5


@pytest.mark.asyncio
async def test_crud_operations(db):
    await db.execute(
        "INSERT INTO admin (username, password) VALUES (?, ?)",
        ("admin", "hashed_pw"),
    )
    row = await db.fetchone("SELECT username FROM admin WHERE username = ?", ("admin",))
    assert row["username"] == "admin"

    rows = await db.fetchall("SELECT * FROM admin")
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_sessions_and_messages(db):
    await db.execute("INSERT INTO sessions (session_key) VALUES (?)", ("telegram:12345",))
    session = await db.fetchone(
        "SELECT id FROM sessions WHERE session_key = ?", ("telegram:12345",)
    )
    assert session is not None

    await db.execute(
        "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
        (session["id"], "user", "Hello!"),
    )
    msgs = await db.fetchall("SELECT * FROM messages WHERE session_id = ?", (session["id"],))
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Hello!"


@pytest.mark.asyncio
async def test_cron_service_sqlite_backend(db):
    """Test CronService with SQLite backend."""
    from comobot.cron.service import CronService
    from comobot.cron.types import CronSchedule

    service = CronService(db=db)

    # Add a job
    job = await service.add_job(
        name="test-job",
        schedule=CronSchedule(kind="every", every_ms=60000),
        message="hello from sqlite",
        deliver=True,
        channel="telegram",
        to="12345",
    )
    assert job.id is not None
    assert job.name == "test-job"

    # List jobs
    jobs = await service.list_jobs()
    assert len(jobs) == 1
    assert jobs[0].name == "test-job"
    assert jobs[0].payload.message == "hello from sqlite"

    # Verify in database directly
    rows = await db.fetchall("SELECT * FROM cron_jobs")
    assert len(rows) == 1

    # Disable job
    updated = await service.enable_job(job.id, enabled=False)
    assert updated is not None
    assert updated.enabled is False

    # List should exclude disabled by default
    active = await service.list_jobs()
    assert len(active) == 0
    all_jobs = await service.list_jobs(include_disabled=True)
    assert len(all_jobs) == 1

    # Remove job
    removed = await service.remove_job(job.id)
    assert removed is True
    remaining = await service.list_jobs(include_disabled=True)
    assert len(remaining) == 0
