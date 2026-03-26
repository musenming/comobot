"""Gateway management endpoints."""

import os
import signal
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Depends
from loguru import logger

from comobot.api.deps import get_current_user

router = APIRouter(prefix="/api/gateway")


def _get_log_dir() -> Path:
    """Return the path to the logs directory (~/.comobot/logs/)."""
    log_dir = Path.home() / ".comobot" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


@router.post("/restart")
async def restart_gateway(_user: str = Depends(get_current_user)):
    """Restart the gateway process.

    Spawns a new gateway process and then terminates the current one.
    The new process inherits the same port and options.
    """
    # Determine the comobot executable
    if getattr(sys, "frozen", False):
        comobot_bin = sys.executable
    else:
        comobot_bin = sys.executable.replace("/python", "/comobot")
        if not Path(comobot_bin).exists():
            comobot_bin = "comobot"

    # Read current port from PID-companion or use default
    port = int(os.environ.get("COMOBOT_PORT", "18790"))

    cmd = [comobot_bin, "gateway", "--port", str(port)]
    log_file = _get_log_dir() / "gateway.log"

    logger.info("Gateway restart requested — spawning new process")

    # Start new gateway process (append to existing log, sanitized)
    from comobot.utils.helpers import pyi_clean_env
    from comobot.utils.log_sanitizer import SanitizedFileWriter

    lf = SanitizedFileWriter(str(log_file))
    subprocess.Popen(
        cmd,
        stdout=lf,
        stderr=lf,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=pyi_clean_env(),
    )

    # Schedule self-termination after response is sent
    import asyncio

    async def _self_terminate():
        await asyncio.sleep(1)
        os.kill(os.getpid(), signal.SIGTERM)

    asyncio.create_task(_self_terminate())

    return {"restarting": True, "message": "Gateway is restarting"}
