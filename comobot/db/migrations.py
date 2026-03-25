"""Database schema migrations for comobot."""

from __future__ import annotations

from loguru import logger

from comobot.db.connection import Database

MIGRATIONS: list[tuple[int, str, str]] = [
    (
        1,
        "initial_schema",
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS admin (
            id          INTEGER PRIMARY KEY,
            username    TEXT UNIQUE NOT NULL,
            password    TEXT NOT NULL,
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id              INTEGER PRIMARY KEY,
            session_key     TEXT UNIQUE NOT NULL,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now')),
            last_consolidated INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY,
            session_id  INTEGER REFERENCES sessions(id),
            role        TEXT NOT NULL,
            content     TEXT,
            tool_calls  TEXT,
            tool_call_id TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

        CREATE TABLE IF NOT EXISTS workflows (
            id          INTEGER PRIMARY KEY,
            name        TEXT UNIQUE NOT NULL,
            description TEXT,
            template    TEXT,
            definition  TEXT NOT NULL,
            enabled     INTEGER DEFAULT 1,
            trigger_rules TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS workflow_runs (
            id          INTEGER PRIMARY KEY,
            workflow_id INTEGER REFERENCES workflows(id),
            trigger_data TEXT,
            status      TEXT DEFAULT 'running',
            variables   TEXT,
            error       TEXT,
            started_at  TEXT DEFAULT (datetime('now')),
            finished_at TEXT
        );

        CREATE TABLE IF NOT EXISTS cron_jobs (
            id          INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            schedule    TEXT NOT NULL,
            payload     TEXT NOT NULL,
            enabled     INTEGER DEFAULT 1,
            next_run_at TEXT,
            last_run_at TEXT,
            last_status TEXT,
            last_error  TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS credentials (
            id          INTEGER PRIMARY KEY,
            provider    TEXT NOT NULL,
            key_name    TEXT NOT NULL,
            encrypted   BLOB NOT NULL,
            nonce       BLOB NOT NULL,
            tag         BLOB NOT NULL,
            created_at  TEXT DEFAULT (datetime('now')),
            UNIQUE(provider, key_name)
        );

        CREATE TABLE IF NOT EXISTS allowed_users (
            id          INTEGER PRIMARY KEY,
            channel     TEXT NOT NULL,
            user_id     TEXT NOT NULL,
            alias       TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            UNIQUE(channel, user_id)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY,
            timestamp   TEXT DEFAULT (datetime('now')),
            level       TEXT NOT NULL,
            module      TEXT NOT NULL,
            event       TEXT NOT NULL,
            detail      TEXT,
            session_key TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_audit_module ON audit_log(module);
    """,
    ),
    (
        2,
        "add_knowhow_table",
        """
        CREATE TABLE IF NOT EXISTS knowhow (
            id              TEXT PRIMARY KEY,
            title           TEXT NOT NULL,
            tags            TEXT NOT NULL DEFAULT '[]',
            goal            TEXT,
            file_path       TEXT NOT NULL UNIQUE,
            source_session  TEXT,
            source_messages TEXT,
            status          TEXT DEFAULT 'active',
            usage_count     INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_knowhow_status ON knowhow(status);
        CREATE INDEX IF NOT EXISTS idx_knowhow_tags ON knowhow(tags);
        """,
    ),
    (
        3,
        "add_sessions_platform",
        """
        ALTER TABLE sessions ADD COLUMN platform TEXT DEFAULT '';

        UPDATE sessions
        SET platform = CASE
            WHEN instr(session_key, ':') > 0
            THEN substr(session_key, 1, instr(session_key, ':') - 1)
            ELSE session_key
        END
        WHERE platform = '' OR platform IS NULL;

        CREATE INDEX IF NOT EXISTS idx_sessions_platform ON sessions(platform);
        """,
    ),
    (
        4,
        "add_remote_tables",
        """
        CREATE TABLE IF NOT EXISTS remote_devices (
            id                TEXT PRIMARY KEY,
            device_name       TEXT NOT NULL,
            device_os         TEXT NOT NULL,
            device_public_key TEXT NOT NULL,
            server_public_key TEXT NOT NULL,
            server_secret_key TEXT NOT NULL,
            push_token        TEXT,
            paired_at         TEXT DEFAULT (datetime('now')),
            last_seen_at      TEXT DEFAULT (datetime('now')),
            is_active         INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS voice_intents (
            id          TEXT PRIMARY KEY,
            device_id   TEXT REFERENCES remote_devices(id),
            transcript  TEXT NOT NULL,
            intent      TEXT,
            confidence  REAL DEFAULT 0,
            status      TEXT DEFAULT 'pending',
            agent_id    TEXT,
            session_key TEXT,
            result      TEXT,
            error       TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_voice_intents_device ON voice_intents(device_id);
        CREATE INDEX IF NOT EXISTS idx_voice_intents_status ON voice_intents(status);

        CREATE TABLE IF NOT EXISTS pairing_tokens (
            token             TEXT PRIMARY KEY,
            server_public_key TEXT NOT NULL,
            server_secret_key TEXT NOT NULL,
            created_at        TEXT DEFAULT (datetime('now')),
            expires_at        TEXT NOT NULL,
            used              INTEGER DEFAULT 0
        );
        """,
    ),
]


async def run_migrations(db: Database) -> None:
    """Run pending database migrations."""
    await db.conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        )
    """)
    await db.conn.commit()

    row = await db.fetchone("SELECT MAX(version) as v FROM schema_version")
    current = row["v"] if row and row["v"] else 0

    for version, name, sql in MIGRATIONS:
        if version <= current:
            continue
        logger.info("Running migration {}: {}", version, name)
        for statement in sql.split(";"):
            stmt = statement.strip()
            if stmt:
                await db.conn.execute(stmt)
        await db.conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
        await db.conn.commit()
        logger.info("Migration {} applied successfully", version)
