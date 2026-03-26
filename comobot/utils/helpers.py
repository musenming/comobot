"""Utility functions for comobot."""

import os
import re
import sys
from datetime import datetime
from pathlib import Path


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists, return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def pyi_clean_env() -> dict[str, str]:
    """Return a copy of ``os.environ`` with PyInstaller internal vars removed.

    When a PyInstaller *onefile* binary spawns itself as a subprocess, the
    child inherits ``_PYI_*`` / ``_MEI*`` environment variables that interfere
    with the bootloader's temp-directory extraction.  On macOS this causes
    runtime-hook failures such as::

        ModuleNotFoundError: No module named '_socket'

    Stripping these variables lets the child perform a clean extraction.
    For non-frozen (``pip install``) environments this simply returns an
    unmodified copy of ``os.environ``.
    """
    env = dict(os.environ)
    if not getattr(sys, "frozen", False):
        return env

    # Remove all PyInstaller internal variables
    for key in list(env):
        if key.startswith(("_PYI_", "_MEI")):
            del env[key]

    # Restore original LD_LIBRARY_PATH / DYLD_LIBRARY_PATH if PyInstaller
    # saved the original value (Linux / macOS).
    for var in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
        orig = env.pop(f"{var}_ORIG", None)
        if orig is not None:
            env[var] = orig
        elif var in env:
            del env[var]

    return env


def get_data_path() -> Path:
    """~/.comobot data directory."""
    comobot_dir = Path.home() / ".comobot"
    if not comobot_dir.exists():
        legacy_dir = Path.home() / ".nanobot"
        if legacy_dir.exists():
            import sys

            print(
                "\n检测到您安装了其他小助手，可将数据进行迁移:\n"
                "  mv ~/.nanobot ~/.comobot\n"
                "迁移后重新启动即可继续使用。\n",
                file=sys.stderr,
            )
    return ensure_dir(comobot_dir)


def get_workspace_path(workspace: str | None = None) -> Path:
    """Resolve and ensure workspace path. Defaults to ~/.comobot/workspace."""
    path = Path(workspace).expanduser() if workspace else Path.home() / ".comobot" / "workspace"
    return ensure_dir(path)


def timestamp() -> str:
    """Current ISO timestamp."""
    return datetime.now().isoformat()


_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*]')


def safe_filename(name: str) -> str:
    """Replace unsafe path characters with underscores."""
    return _UNSAFE_CHARS.sub("_", name).strip()


def sync_workspace_templates(workspace: Path, silent: bool = False) -> list[str]:
    """Sync bundled templates to workspace. Only creates missing files."""
    from importlib.resources import files as pkg_files

    try:
        tpl = pkg_files("comobot") / "templates"
    except Exception:
        return []
    if not tpl.is_dir():
        return []

    added: list[str] = []

    def _write(src, dest: Path):
        if dest.exists():
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text(encoding="utf-8") if src else "", encoding="utf-8")
        added.append(str(dest.relative_to(workspace)))

    for item in tpl.iterdir():
        if item.name.endswith(".md"):
            _write(item, workspace / item.name)
    _write(tpl / "memory" / "MEMORY.md", workspace / "memory" / "MEMORY.md")
    _write(None, workspace / "memory" / "HISTORY.md")
    (workspace / "skills").mkdir(exist_ok=True)

    if added and not silent:
        from rich.console import Console

        for name in added:
            Console().print(f"  [dim]Created {name}[/dim]")
    return added
