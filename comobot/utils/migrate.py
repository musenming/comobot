"""Memory and file system migration utilities.

Checks for legacy storage structures and migrates them to the current format.
Run automatically on startup (gateway/agent) to ensure clean state.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from loguru import logger


def check_and_migrate(data_dir: Path, workspace: Path) -> None:
    """Run all migration checks.

    Call this during startup (before agent/gateway begin processing) to ensure
    the file system structure matches the current version.
    """
    logger.debug("Running storage migration checks...")
    _migrate_legacy_memory(data_dir, workspace)
    _migrate_legacy_sessions(data_dir, workspace)
    _migrate_legacy_cron(data_dir, workspace)
    logger.debug("Migration checks completed")


def _migrate_legacy_memory(data_dir: Path, workspace: Path) -> None:
    """Migrate memory from old flat-file structure to the current two-layer layout.

    Old structure (pre-migration):
        ~/.comobot/MEMORY.md         (single flat memory file)
        ~/.comobot/HISTORY.md        (single flat history file)
        ~/.comobot/workspace/MEMORY.md  (in workspace root, not in memory/)

    New structure:
        ~/.comobot/workspace/memory/MEMORY.md   (long-term memory)
        ~/.comobot/workspace/memory/YYYY-MM-DD.md  (daily logs)
    """
    memory_dir = workspace / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    new_memory_file = memory_dir / "MEMORY.md"

    # 1. Migrate ~/.comobot/MEMORY.md -> workspace/memory/MEMORY.md
    legacy_root_memory = data_dir / "MEMORY.md"
    if legacy_root_memory.exists() and not new_memory_file.exists():
        try:
            content = legacy_root_memory.read_text(encoding="utf-8")
            if content.strip():
                new_memory_file.write_text(content, encoding="utf-8")
                logger.info("Migrated MEMORY.md from {} to {}", legacy_root_memory, new_memory_file)
            legacy_root_memory.unlink()
            logger.info("Removed legacy {}", legacy_root_memory)
        except Exception:
            logger.exception("Failed to migrate legacy root MEMORY.md")

    # 2. Migrate workspace/MEMORY.md -> workspace/memory/MEMORY.md
    workspace_root_memory = workspace / "MEMORY.md"
    if workspace_root_memory.exists() and workspace_root_memory != new_memory_file:
        try:
            if not new_memory_file.exists():
                content = workspace_root_memory.read_text(encoding="utf-8")
                if content.strip():
                    new_memory_file.write_text(content, encoding="utf-8")
                    logger.info("Migrated MEMORY.md from workspace root to memory/")
            # Keep workspace/MEMORY.md as a symlink or remove it
            workspace_root_memory.unlink()
            logger.info("Removed legacy workspace root MEMORY.md")
        except Exception:
            logger.exception("Failed to migrate workspace root MEMORY.md")

    # 3. Migrate legacy HISTORY.md to a daily log entry
    for history_path in [data_dir / "HISTORY.md", workspace / "HISTORY.md"]:
        if history_path.exists():
            try:
                content = history_path.read_text(encoding="utf-8").strip()
                if content:
                    # Write to a migration-specific daily log
                    migration_log = memory_dir / "migrated-history.md"
                    if not migration_log.exists():
                        migration_log.write_text(
                            f"# Migrated History\n\n{content}\n",
                            encoding="utf-8",
                        )
                        logger.info(
                            "Migrated HISTORY.md content to {}",
                            migration_log,
                        )
                history_path.unlink()
                logger.info("Removed legacy {}", history_path)
            except Exception:
                logger.exception("Failed to migrate {}", history_path)

    # 4. Migrate legacy memory/ files that might be in the old format
    # (e.g. memory stored in ~/.comobot/memory/ instead of workspace/memory/)
    legacy_memory_dir = data_dir / "memory"
    if (
        legacy_memory_dir.exists()
        and legacy_memory_dir != memory_dir
        and legacy_memory_dir.is_dir()
    ):
        try:
            for f in legacy_memory_dir.glob("*.md"):
                dest = memory_dir / f.name
                if not dest.exists():
                    shutil.copy2(str(f), str(dest))
                    logger.info("Migrated memory file {} -> {}", f.name, dest)
            # Remove legacy dir if now empty (except index files)
            remaining = [p for p in legacy_memory_dir.iterdir() if not p.name.startswith(".")]
            if not remaining:
                shutil.rmtree(str(legacy_memory_dir), ignore_errors=True)
                logger.info("Removed empty legacy memory dir {}", legacy_memory_dir)
        except Exception:
            logger.exception("Failed to migrate legacy memory directory")


def _migrate_legacy_sessions(data_dir: Path, workspace: Path) -> None:
    """Migrate session files from ~/.comobot/sessions/ to workspace/sessions/."""
    legacy_dir = data_dir / "sessions"
    new_dir = workspace / "sessions"

    if not legacy_dir.exists() or not legacy_dir.is_dir():
        return
    if legacy_dir == new_dir:
        return

    new_dir.mkdir(parents=True, exist_ok=True)

    migrated = 0
    for f in legacy_dir.glob("*.jsonl"):
        dest = new_dir / f.name
        if not dest.exists():
            try:
                shutil.move(str(f), str(dest))
                migrated += 1
            except Exception:
                logger.warning("Failed to migrate session file {}", f.name)

    if migrated > 0:
        logger.info("Migrated {} session files to workspace/sessions/", migrated)

    # Clean up empty legacy dir
    remaining = list(legacy_dir.iterdir())
    if not remaining:
        legacy_dir.rmdir()
        logger.info("Removed empty legacy sessions dir")


def _migrate_legacy_cron(data_dir: Path, workspace: Path) -> None:
    """Check for legacy cron/jobs.json and log a note if it exists.

    The cron system now uses SQLite. Legacy jobs.json files are still supported
    by CronService as a fallback, so we just log a note here.
    """
    legacy_cron = data_dir / "cron" / "jobs.json"
    if legacy_cron.exists():
        try:
            content = json.loads(legacy_cron.read_text(encoding="utf-8"))
            job_count = len(content.get("jobs", []))
            if job_count > 0:
                logger.info(
                    "Legacy cron/jobs.json found with {} jobs. "
                    "These will be loaded by CronService automatically.",
                    job_count,
                )
        except Exception:
            pass
