"""Workspace auto-migration for Agent v2.

Creates new directories required by v2 features (episodic memory, feedback,
custom agent profiles).  Only adds — never deletes or modifies existing files.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger


def migrate_workspace_v2(workspace: Path) -> None:
    """Ensure v2 workspace directories exist.  Safe to call on every startup."""
    for subdir in ("episodic", "feedback", "agents"):
        path = workspace / subdir
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            logger.info("Created workspace directory: {}", path)
