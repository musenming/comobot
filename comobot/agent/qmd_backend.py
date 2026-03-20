"""QMD sidecar backend: integrates @tobilu/qmd as a search engine."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from comobot.agent.memory_backend import MemoryBackend, SearchResult
from comobot.utils.helpers import ensure_dir

if TYPE_CHECKING:
    from comobot.config.schema import QMDConfig

QMD_NPM_PACKAGE = "@tobilu/qmd"


def detect_gpu() -> dict:
    """Detect GPU availability. Returns {available: bool, name: str | None}."""
    # Check NVIDIA GPU
    try:
        import subprocess

        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return {"available": True, "name": result.stdout.strip().split("\n")[0]}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Check ROCm (AMD)
    try:
        import subprocess

        result = subprocess.run(
            ["rocm-smi", "--showproductname"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return {"available": True, "name": "AMD ROCm GPU"}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return {"available": False, "name": None}


def detect_qmd_mode() -> str:
    """Auto-detect optimal QMD mode based on system memory."""
    try:
        import psutil

        total_ram_gb = psutil.virtual_memory().total / (1024**3)
        return "daemon" if total_ram_gb >= 16 else "on-demand"
    except ImportError:
        # psutil not available, default to on-demand (safer)
        return "on-demand"


class QMDManager:
    """Manages QMD subprocess lifecycle."""

    def __init__(self, config: QMDConfig, workspace: Path):
        self._config = config
        self._workspace = workspace
        self._process: asyncio.subprocess.Process | None = None
        self._qmd_dir = ensure_dir(workspace / ".qmd")
        self._update_task: asyncio.Task | None = None
        self._mode = config.mode if config.mode != "auto" else detect_qmd_mode()
        self._http_port: int | None = None

    async def start(self) -> None:
        """Start QMD: auto-install if needed, setup collections, index, launch daemon."""
        await self._ensure_qmd_installed()

        # Verify binary works
        version = await self._run_qmd("--version")
        logger.info("QMD version: {}", version.strip())

        # Register collections
        await self._setup_collections()

        # Initial update + embed (first run downloads the embedding model, may take minutes)
        await self._run_qmd("update")
        logger.info(
            "QMD: generating embeddings (first run downloads model, may take a few minutes)..."
        )
        await self._run_qmd("embed", timeout=800)

        # Start daemon if mode requires it
        if self._mode == "daemon":
            await self._start_daemon()
            self._update_task = asyncio.create_task(self._periodic_update())

    def _find_qmd_binary(self) -> str | None:
        """Find the qmd binary: check config command, local install, then PATH."""
        # 1. Check configured command
        cmd = self._config.command
        if cmd != "qmd" and shutil.which(cmd):
            return cmd

        # 2. Check local install in .qmd/node_modules
        local_bin = self._qmd_dir / "node_modules" / ".bin" / "qmd"
        if local_bin.exists():
            return str(local_bin)

        # 3. Check global PATH
        global_qmd = shutil.which("qmd")
        if global_qmd:
            return global_qmd

        return None

    async def _ensure_bun_installed(self) -> str:
        """Ensure bun runtime is available; auto-install if needed. Returns bun path."""
        bun_path = shutil.which("bun")
        if bun_path:
            logger.info("Bun runtime found: {}", bun_path)
            return bun_path

        # Check common install locations
        home = Path.home()
        candidates = [
            home / ".bun" / "bin" / "bun",
            Path("/usr/local/bin/bun"),
            Path("/opt/homebrew/bin/bun"),
        ]
        for c in candidates:
            if c.exists():
                logger.info("Bun runtime found: {}", c)
                return str(c)

        # Auto-install bun
        logger.info("Bun runtime not found, installing (first-time setup)...")
        curl_path = shutil.which("curl")
        if not curl_path:
            raise FileNotFoundError(
                "Bun runtime not found and curl is not available for auto-install. "
                "Please install bun manually: curl -fsSL https://bun.sh/install | bash"
            )

        proc = await asyncio.create_subprocess_shell(
            "curl -fsSL https://bun.sh/install | bash",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "BUN_INSTALL": str(home / ".bun")},
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

        if proc.returncode != 0:
            err_msg = stderr.decode().strip()
            logger.error("Bun install failed: {}", err_msg)
            raise RuntimeError(f"Failed to install bun: {err_msg}")

        installed_bun = home / ".bun" / "bin" / "bun"
        if not installed_bun.exists():
            raise FileNotFoundError(
                "Bun installed but binary not found. "
                "Please install manually: curl -fsSL https://bun.sh/install | bash"
            )

        logger.info("Bun installed successfully: {}", installed_bun)
        return str(installed_bun)

    async def _ensure_qmd_installed(self) -> None:
        """Check if qmd binary exists; if not, auto-install bun + qmd.

        Install chain (only curl required on system):
          curl → bun (runtime) → bun add @tobilu/qmd (package)
        """
        # Step 1: Ensure bun runtime is available (qmd requires it)
        bun_path = await self._ensure_bun_installed()

        # Add bun to PATH for qmd subprocess calls
        bun_dir = str(Path(bun_path).parent)
        current_path = os.environ.get("PATH", "")
        if bun_dir not in current_path:
            os.environ["PATH"] = f"{bun_dir}:{current_path}"

        # Step 2: Check if qmd binary exists
        existing = self._find_qmd_binary()
        if existing:
            self._config.command = existing
            logger.info("QMD binary found: {}", existing)
            return

        # Step 3: Install qmd via bun (faster than npm, and already installed)
        logger.info("QMD not found, installing {} via bun (first-time setup)...", QMD_NPM_PACKAGE)

        install_dir = self._qmd_dir
        # Ensure package.json exists for bun add
        pkg_json = install_dir / "package.json"
        if not pkg_json.exists():
            pkg_json.write_text('{"private": true}', encoding="utf-8")

        proc = await asyncio.create_subprocess_exec(
            bun_path,
            "add",
            QMD_NPM_PACKAGE,
            cwd=str(install_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

        if proc.returncode != 0:
            err_msg = stderr.decode().strip()
            logger.error("QMD install failed: {}", err_msg)
            raise RuntimeError(f"Failed to install QMD: {err_msg}")

        # Verify the installed binary
        local_bin = install_dir / "node_modules" / ".bin" / "qmd"
        if not local_bin.exists():
            raise FileNotFoundError(
                f"QMD installed but binary not found at {local_bin}. "
                "Try manual install: bun add -g @tobilu/qmd"
            )

        self._config.command = str(local_bin)
        logger.info("QMD installed successfully: {}", local_bin)

    async def _setup_collections(self) -> None:
        """Register search directories as QMD collections."""
        collections: dict[str, str] = {
            "memory": str(self._workspace / "memory"),
        }
        # Session transcripts
        transcript_dir = self._workspace / ".session_index" / "transcripts"
        if transcript_dir.exists():
            collections["sessions"] = str(transcript_dir)

        # Know-how
        knowhow_dir = self._workspace / "knowhow"
        if knowhow_dir.exists():
            collections["knowhow"] = str(knowhow_dir)

        # User-configured extra paths
        for name, path in self._config.paths.items():
            collections[name] = path

        for name, path in collections.items():
            try:
                await self._run_qmd("collection", "add", path, "--name", name)
                logger.info("QMD collection '{}' added: {}", name, path)
            except RuntimeError as e:
                if "already exists" in str(e):
                    logger.debug("QMD collection '{}' already exists, skipping", name)
                else:
                    logger.warning("Failed to add collection {}: {}", name, e)

    async def _start_daemon(self) -> None:
        """Start QMD MCP server in daemon mode."""
        env = self._qmd_env()
        self._process = await asyncio.create_subprocess_exec(
            self._config.command,
            "mcp",
            "--http",
            "--daemon",
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # Wait briefly for startup
        await asyncio.sleep(2)
        if self._process.returncode is not None:
            stderr = ""
            if self._process.stderr:
                stderr = (await self._process.stderr.read()).decode()
            raise RuntimeError(f"QMD daemon failed to start: {stderr}")
        logger.info("QMD daemon started (pid={})", self._process.pid)

    async def _periodic_update(self) -> None:
        """Periodically re-scan and re-embed."""
        interval = self._config.update_interval
        while True:
            await asyncio.sleep(interval)
            try:
                await self._run_qmd("update")
                await self._run_qmd("embed", timeout=800)
            except Exception as e:
                logger.warning("QMD periodic update failed: {}", e)

    async def stop(self) -> None:
        """Graceful shutdown."""
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
            self._update_task = None

        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=10)
            except asyncio.TimeoutError:
                self._process.kill()
            self._process = None
            logger.info("QMD daemon stopped")

    async def query(self, query_text: str, limit: int = 5) -> list[dict]:
        """Execute a QMD query. In on-demand mode, starts a temporary process."""
        if self._mode == "on-demand":
            return await self._on_demand_query(query_text, limit)
        return await self._daemon_query(query_text, limit)

    async def _daemon_query(self, query_text: str, limit: int) -> list[dict]:
        """Query via the running daemon's MCP interface."""
        result = await self._run_qmd("query", query_text, "--limit", str(limit), "--json")
        try:
            data = json.loads(result)
            return data if isinstance(data, list) else data.get("results", [])
        except json.JSONDecodeError:
            return []

    async def _on_demand_query(self, query_text: str, limit: int) -> list[dict]:
        """Start QMD, query, then release. Higher latency but zero idle memory."""
        result = await self._run_qmd("query", query_text, "--limit", str(limit), "--json")
        try:
            data = json.loads(result)
            return data if isinstance(data, list) else data.get("results", [])
        except json.JSONDecodeError:
            return []

    async def update_and_embed(self) -> None:
        """Manually trigger update + embed."""
        await self._run_qmd("update")
        await self._run_qmd("embed")

    async def _run_qmd(self, *args: str, timeout: int = 120) -> str:
        """Execute a qmd CLI command."""
        env = self._qmd_env()
        proc = await asyncio.create_subprocess_exec(
            self._config.command,
            *args,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"qmd {' '.join(args)} timed out after {timeout}s")
        if proc.returncode != 0:
            err = stderr.decode().strip() or stdout.decode().strip()
            raise RuntimeError(f"qmd {' '.join(args)} failed: {err}")
        return stdout.decode()

    def _qmd_env(self) -> dict[str, str]:
        """Environment variables for QMD process isolation."""
        return {
            **os.environ,
            "XDG_CONFIG_HOME": str(self._qmd_dir / "config"),
            "XDG_CACHE_HOME": str(self._qmd_dir / "cache"),
            "QMD_DB_PATH": str(self._qmd_dir / "index.sqlite"),
        }

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None


class QMDBackend(MemoryBackend):
    """QMD search backend with BM25 + Vector + Reranking."""

    def __init__(self, config: QMDConfig, workspace: Path):
        self._manager = QMDManager(config, workspace)
        self._config = config
        self._workspace = workspace
        self._available = False

    async def initialize(self) -> None:
        try:
            logger.info("Initializing QMD backend...")
            await self._manager.start()
            self._available = True
            logger.info("QMD backend initialized successfully (mode={})", self._manager._mode)
        except FileNotFoundError as e:
            logger.error("QMD setup failed: {}", e)
            self._available = False
            raise
        except Exception as e:
            logger.error("QMD initialization failed: {}", e)
            self._available = False
            raise

    async def search(self, query: str, max_results: int = 5, **kwargs) -> list[SearchResult]:
        if not self._available:
            raise RuntimeError("QMD backend not available")
        raw_results = await self._manager.query(query, max_results)
        return [self._parse_result(r) for r in raw_results]

    async def get(self, path: str) -> str:
        abs_path = self._workspace / path
        if abs_path.exists():
            return abs_path.read_text(encoding="utf-8")
        return ""

    async def reindex(self, paths: list[str] | None = None) -> None:
        if self._available:
            await self._manager.update_and_embed()

    async def shutdown(self) -> None:
        await self._manager.stop()
        self._available = False

    @property
    def is_running(self) -> bool:
        return self._available and self._manager.is_running

    @staticmethod
    def _parse_result(raw: dict) -> SearchResult:
        return SearchResult(
            content=raw.get("content", ""),
            file_path=raw.get("path", ""),
            start_line=raw.get("line", 0),
            end_line=raw.get("endLine", 0),
            score=raw.get("score", 0.0),
            source=raw.get("collection", "memory"),
        )
