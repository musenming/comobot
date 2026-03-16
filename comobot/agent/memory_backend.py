"""Memory backend abstraction: pluggable search backends for the memory system."""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from comobot.agent.memory_search import MemorySearchEngine


@dataclass
class SearchResult:
    """A search result from any memory backend."""

    content: str
    file_path: str
    start_line: int
    end_line: int
    score: float
    source: str  # "memory", "session", "knowhow"


class MemoryBackend(ABC):
    """Abstract search backend, supporting builtin and QMD implementations."""

    @abstractmethod
    async def initialize(self) -> None: ...

    @abstractmethod
    async def search(self, query: str, max_results: int = 5, **kwargs) -> list[SearchResult]: ...

    @abstractmethod
    async def get(self, path: str) -> str: ...

    @abstractmethod
    async def reindex(self, paths: list[str] | None = None) -> None: ...

    @abstractmethod
    async def shutdown(self) -> None: ...


class BuiltinBackend(MemoryBackend):
    """Wraps the existing MemorySearchEngine to conform to the MemoryBackend interface."""

    def __init__(self, engine: MemorySearchEngine, workspace: Path):
        self._engine = engine
        self._workspace = workspace

    @property
    def engine(self) -> MemorySearchEngine:
        """Expose underlying engine for callers that need direct access."""
        return self._engine

    async def initialize(self) -> None:
        self._engine.reindex()

    async def search(self, query: str, max_results: int = 5, **kwargs) -> list[SearchResult]:
        file_filter = kwargs.get("file_filter")
        chunks = self._engine.search(query, max_results=max_results, file_filter=file_filter)
        return [
            SearchResult(
                content=c.content,
                file_path=c.file_path,
                start_line=c.start_line,
                end_line=c.end_line,
                score=c.score,
                source=_classify_source(c.file_path),
            )
            for c in chunks
        ]

    async def get(self, path: str) -> str:
        abs_path = self._workspace / path
        if abs_path.exists():
            return abs_path.read_text(encoding="utf-8")
        return ""

    async def reindex(self, paths: list[str] | None = None) -> None:
        self._engine.reindex()

    async def shutdown(self) -> None:
        self._engine.close()


class FallbackBackend(MemoryBackend):
    """Tries QMD backend first, falls back to builtin on failure.

    Safety net design (inspired by OpenClaw):
    - If primary (QMD) crashes, returns errors, or times out → auto-fallback to builtin
    - Consecutive failures are tracked; after threshold → primary is suspended
    - A background recovery probe periodically checks if primary is healthy again
    - Once recovered, search automatically routes through primary again
    - The builtin backend is ALWAYS available as a safety net
    """

    # After this many consecutive failures, suspend primary and start recovery probes
    FAILURE_THRESHOLD = 3
    # Seconds between recovery probes when primary is suspended
    RECOVERY_INTERVAL = 60

    def __init__(self, primary: MemoryBackend, fallback: BuiltinBackend):
        self._primary = primary
        self._fallback = fallback
        self._use_primary = False
        self._consecutive_failures = 0
        self._last_failure_time: float = 0
        self._recovery_task: asyncio.Task | None = None
        # Attributes set by settings API for async enable
        self._starting = False
        self._start_error: str | None = None

    @property
    def engine(self) -> MemorySearchEngine:
        """Expose underlying engine for callers that need direct access."""
        return self._fallback.engine

    async def initialize(self, enable_primary: bool = True) -> None:
        await self._fallback.initialize()
        if not enable_primary:
            logger.info("Memory backend ready (primary disabled, hot-swap available)")
            return
        try:
            await self._primary.initialize()
            self._use_primary = True
            self._consecutive_failures = 0
            logger.info("Primary memory backend active")
        except Exception as e:
            logger.info("Primary backend unavailable ({}), using builtin fallback", e)

    def _record_failure(self, operation: str, error: Exception) -> None:
        """Record a primary backend failure and suspend if threshold reached."""
        self._consecutive_failures += 1
        self._last_failure_time = time.monotonic()
        logger.warning(
            "Primary {} failed ({}/{}): {}",
            operation,
            self._consecutive_failures,
            self.FAILURE_THRESHOLD,
            error,
        )
        if self._consecutive_failures >= self.FAILURE_THRESHOLD:
            self._use_primary = False
            logger.error(
                "Primary backend suspended after {} consecutive failures, "
                "falling back to builtin. Recovery probe will attempt reconnection.",
                self._consecutive_failures,
            )
            self._start_recovery_probe()

    def _record_success(self) -> None:
        """Reset failure counter on successful primary operation."""
        if self._consecutive_failures > 0:
            logger.info("Primary backend recovered after {} failures", self._consecutive_failures)
        self._consecutive_failures = 0

    def _start_recovery_probe(self) -> None:
        """Start a background task that periodically probes if primary is healthy."""
        if self._recovery_task and not self._recovery_task.done():
            return  # Already probing
        self._recovery_task = asyncio.create_task(self._recovery_loop())

    async def _recovery_loop(self) -> None:
        """Periodically attempt to re-enable the primary backend."""
        logger.info("Recovery probe started (interval={}s)", self.RECOVERY_INTERVAL)
        while not self._use_primary:
            await asyncio.sleep(self.RECOVERY_INTERVAL)
            try:
                await self._primary.initialize()
                self._use_primary = True
                self._consecutive_failures = 0
                logger.info("Primary backend recovered and re-enabled automatically")
                return
            except Exception as e:
                logger.debug("Recovery probe: primary still unavailable ({})", e)
        logger.info("Recovery probe stopped (primary is active)")

    async def search(self, query: str, max_results: int = 5, **kwargs) -> list[SearchResult]:
        if self._use_primary:
            try:
                results = await self._primary.search(query, max_results, **kwargs)
                self._record_success()
                return results
            except Exception as e:
                self._record_failure("search", e)
        return await self._fallback.search(query, max_results, **kwargs)

    async def get(self, path: str) -> str:
        if self._use_primary:
            try:
                content = await self._primary.get(path)
                self._record_success()
                return content
            except Exception as e:
                self._record_failure("get", e)
        return await self._fallback.get(path)

    async def reindex(self, paths: list[str] | None = None) -> None:
        await self._fallback.reindex(paths)
        if self._use_primary:
            try:
                await self._primary.reindex(paths)
            except Exception as e:
                logger.warning("Primary reindex failed: {}", e)

    async def shutdown(self) -> None:
        # Stop recovery probe
        if self._recovery_task and not self._recovery_task.done():
            self._recovery_task.cancel()
            try:
                await self._recovery_task
            except asyncio.CancelledError:
                pass
        if self._use_primary:
            try:
                await self._primary.shutdown()
            except Exception:
                pass
        await self._fallback.shutdown()

    async def enable_primary(self) -> None:
        """Enable the primary backend at runtime (hot-swap)."""
        if self._use_primary:
            return
        try:
            await self._primary.initialize()
            self._use_primary = True
            self._consecutive_failures = 0
            logger.info("Primary backend enabled via hot-swap")
        except Exception as e:
            logger.error("Failed to enable primary backend: {}", e)
            raise

    async def disable_primary(self) -> None:
        """Disable the primary backend at runtime (hot-swap)."""
        if not self._use_primary:
            return
        # Stop recovery probe if running
        if self._recovery_task and not self._recovery_task.done():
            self._recovery_task.cancel()
            try:
                await self._recovery_task
            except asyncio.CancelledError:
                pass
        await self._primary.shutdown()
        self._use_primary = False
        self._consecutive_failures = 0
        logger.info("Primary backend disabled, using builtin")

    @property
    def primary_active(self) -> bool:
        return self._use_primary


def _classify_source(file_path: str) -> str:
    """Classify a file path into a source category."""
    if ".session_index/" in file_path:
        return "session"
    if file_path.startswith("knowhow/"):
        return "knowhow"
    return "memory"
