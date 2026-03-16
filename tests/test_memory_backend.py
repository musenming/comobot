"""Tests for memory backend abstraction and QMD integration wiring."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from comobot.agent.memory_backend import (
    BuiltinBackend,
    FallbackBackend,
    MemoryBackend,
    SearchResult,
    _classify_source,
)
from comobot.agent.memory_search import MemorySearchEngine
from comobot.config.schema import MemoryConfig, QMDConfig


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    (tmp_path / "memory").mkdir()
    return tmp_path


@pytest.fixture
def engine(tmp_workspace: Path) -> MemorySearchEngine:
    return MemorySearchEngine(workspace=tmp_workspace)


# ── SearchResult / classify ──────────────────────────────────────


class TestClassifySource:
    def test_memory_file(self):
        assert _classify_source("memory/2026-03-16.md") == "memory"

    def test_session_transcript(self):
        assert _classify_source(".session_index/transcripts/foo.md") == "session"

    def test_knowhow_file(self):
        assert _classify_source("knowhow/fix_bug.md") == "knowhow"

    def test_memory_md(self):
        assert _classify_source("MEMORY.md") == "memory"


# ── BuiltinBackend ───────────────────────────────────────────────


class TestBuiltinBackend:
    @pytest.mark.asyncio
    async def test_search_delegates_to_engine(self, tmp_workspace, engine):
        # Write a memory file so search has something to find
        (tmp_workspace / "memory" / "test.md").write_text("hello world test content")
        engine.reindex()

        backend = BuiltinBackend(engine, tmp_workspace)
        results = await backend.search("hello world")
        assert len(results) > 0
        assert isinstance(results[0], SearchResult)
        assert results[0].source == "memory"

    @pytest.mark.asyncio
    async def test_get_reads_file(self, tmp_workspace, engine):
        (tmp_workspace / "memory" / "note.md").write_text("my note")
        backend = BuiltinBackend(engine, tmp_workspace)
        content = await backend.get("memory/note.md")
        assert content == "my note"

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_empty(self, tmp_workspace, engine):
        backend = BuiltinBackend(engine, tmp_workspace)
        content = await backend.get("memory/missing.md")
        assert content == ""

    @pytest.mark.asyncio
    async def test_reindex_calls_engine(self, tmp_workspace, engine):
        backend = BuiltinBackend(engine, tmp_workspace)
        await backend.reindex()  # Should not raise

    @pytest.mark.asyncio
    async def test_engine_property(self, tmp_workspace, engine):
        backend = BuiltinBackend(engine, tmp_workspace)
        assert backend.engine is engine


# ── FallbackBackend ──────────────────────────────────────────────


class TestFallbackBackend:
    def _make_mock_primary(self):
        primary = AsyncMock(spec=MemoryBackend)
        primary.search = AsyncMock(
            return_value=[SearchResult("qmd content", "f.md", 1, 5, 0.9, "memory")]
        )
        primary.initialize = AsyncMock()
        primary.shutdown = AsyncMock()
        primary.reindex = AsyncMock()
        return primary

    @pytest.mark.asyncio
    async def test_uses_primary_when_available(self, tmp_workspace, engine):
        primary = self._make_mock_primary()
        builtin = BuiltinBackend(engine, tmp_workspace)
        fb = FallbackBackend(primary, builtin)
        await fb.initialize()

        assert fb.primary_active is True
        results = await fb.search("test")
        assert len(results) == 1
        assert results[0].content == "qmd content"
        primary.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_on_primary_failure(self, tmp_workspace, engine):
        primary = self._make_mock_primary()
        primary.search = AsyncMock(side_effect=RuntimeError("QMD crashed"))
        builtin = BuiltinBackend(engine, tmp_workspace)
        fb = FallbackBackend(primary, builtin)
        await fb.initialize()

        # Safety net: needs FAILURE_THRESHOLD (3) consecutive failures to suspend
        for i in range(fb.FAILURE_THRESHOLD):
            results = await fb.search("test")
            assert isinstance(results, list)
            if i < fb.FAILURE_THRESHOLD - 1:
                # Still trying primary until threshold reached
                assert fb.primary_active is True
        # After threshold, primary is suspended
        assert fb.primary_active is False

    @pytest.mark.asyncio
    async def test_single_failure_does_not_suspend(self, tmp_workspace, engine):
        """A single failure should NOT suspend primary — it recovers on next success."""
        primary = self._make_mock_primary()
        builtin = BuiltinBackend(engine, tmp_workspace)
        fb = FallbackBackend(primary, builtin)
        await fb.initialize()

        # One failure
        primary.search = AsyncMock(side_effect=RuntimeError("transient"))
        await fb.search("test")
        assert fb.primary_active is True  # Still active
        assert fb._consecutive_failures == 1

        # Next call succeeds — counter resets
        primary.search = AsyncMock(return_value=[SearchResult("ok", "f.md", 1, 1, 0.9, "memory")])
        results = await fb.search("test")
        assert fb.primary_active is True
        assert fb._consecutive_failures == 0
        assert results[0].content == "ok"

    @pytest.mark.asyncio
    async def test_falls_back_on_primary_init_failure(self, tmp_workspace, engine):
        primary = self._make_mock_primary()
        primary.initialize = AsyncMock(side_effect=FileNotFoundError("qmd not found"))
        builtin = BuiltinBackend(engine, tmp_workspace)
        fb = FallbackBackend(primary, builtin)
        await fb.initialize()

        assert fb.primary_active is False

    @pytest.mark.asyncio
    async def test_enable_disable_primary(self, tmp_workspace, engine):
        primary = self._make_mock_primary()
        primary.initialize = AsyncMock(side_effect=FileNotFoundError("qmd not found"))
        builtin = BuiltinBackend(engine, tmp_workspace)
        fb = FallbackBackend(primary, builtin)
        await fb.initialize()
        assert fb.primary_active is False

        # Now fix the primary and enable it
        primary.initialize = AsyncMock()
        await fb.enable_primary()
        assert fb.primary_active is True

        # Disable it
        await fb.disable_primary()
        assert fb.primary_active is False
        primary.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_enable_primary_failure_raises(self, tmp_workspace, engine):
        primary = self._make_mock_primary()
        primary.initialize = AsyncMock(side_effect=RuntimeError("qmd broken"))
        builtin = BuiltinBackend(engine, tmp_workspace)
        fb = FallbackBackend(primary, builtin)

        with pytest.raises(RuntimeError, match="qmd broken"):
            await fb.enable_primary()
        assert fb.primary_active is False

    @pytest.mark.asyncio
    async def test_engine_property_returns_builtin_engine(self, tmp_workspace, engine):
        primary = self._make_mock_primary()
        builtin = BuiltinBackend(engine, tmp_workspace)
        fb = FallbackBackend(primary, builtin)
        assert fb.engine is engine

    @pytest.mark.asyncio
    async def test_recovery_probe_re_enables_primary(self, tmp_workspace, engine):
        """After suspension, recovery probe should re-enable primary when healthy."""
        primary = self._make_mock_primary()
        primary.search = AsyncMock(side_effect=RuntimeError("QMD crashed"))
        builtin = BuiltinBackend(engine, tmp_workspace)
        fb = FallbackBackend(primary, builtin)
        fb.RECOVERY_INTERVAL = 0.1  # Speed up for test
        await fb.initialize()

        # Trigger suspension
        for _ in range(fb.FAILURE_THRESHOLD):
            await fb.search("test")
        assert fb.primary_active is False

        # "Fix" primary — next initialize will succeed
        primary.initialize = AsyncMock()

        # Wait for recovery probe to fire
        await asyncio.sleep(0.3)
        assert fb.primary_active is True
        assert fb._consecutive_failures == 0

        # Cleanup
        await fb.shutdown()

    @pytest.mark.asyncio
    async def test_get_fallback_on_failure(self, tmp_workspace, engine):
        """get() should also fallback and track failures."""
        primary = self._make_mock_primary()
        primary.get = AsyncMock(side_effect=RuntimeError("QMD down"))
        (tmp_workspace / "memory" / "note.md").write_text("builtin content")
        builtin = BuiltinBackend(engine, tmp_workspace)
        fb = FallbackBackend(primary, builtin)
        await fb.initialize()

        content = await fb.get("memory/note.md")
        assert content == "builtin content"
        assert fb._consecutive_failures == 1


# ── MemorySearchTool with backend ────────────────────────────────


class TestMemorySearchToolWithBackend:
    @pytest.mark.asyncio
    async def test_tool_uses_backend(self, tmp_workspace, engine):
        from comobot.agent.tools.memory_tools import MemorySearchTool

        backend = AsyncMock(spec=MemoryBackend)
        backend.search = AsyncMock(
            return_value=[SearchResult("found it", "memory/test.md", 1, 3, 0.85, "memory")]
        )
        tool = MemorySearchTool(backend=backend)
        result = await tool.execute(query="test query")
        assert "found it" in result
        assert "0.850" in result
        backend.search.assert_called_once_with("test query", max_results=5)

    @pytest.mark.asyncio
    async def test_tool_uses_engine_fallback(self, tmp_workspace, engine):
        from comobot.agent.tools.memory_tools import MemorySearchTool

        tool = MemorySearchTool(engine)
        result = await tool.execute(query="nonexistent")
        assert "No matching" in result

    @pytest.mark.asyncio
    async def test_tool_no_backend_no_engine(self):
        from comobot.agent.tools.memory_tools import MemorySearchTool

        tool = MemorySearchTool()
        result = await tool.execute(query="test")
        assert "no search backend" in result


# ── Config schema ────────────────────────────────────────────────


class TestConfigSchema:
    def test_qmd_config_defaults(self):
        qmd = QMDConfig()
        assert qmd.enabled is False
        assert qmd.command == "qmd"
        assert qmd.mode == "auto"
        assert qmd.paths == {}
        assert qmd.update_interval == 300

    def test_memory_config_with_qmd(self):
        mc = MemoryConfig(backend="qmd", qmd=QMDConfig(enabled=True, mode="daemon"))
        assert mc.backend == "qmd"
        assert mc.qmd.enabled is True
        assert mc.qmd.mode == "daemon"

    def test_memory_config_defaults(self):
        mc = MemoryConfig()
        assert mc.backend == "auto"
        assert mc.qmd.enabled is False
        assert mc.session_index.enabled is False


# ── QMD Backend (unit-level, no real qmd binary) ─────────────────


class TestQMDBackend:
    def test_detect_qmd_mode_with_high_ram(self):
        from comobot.agent.qmd_backend import detect_qmd_mode

        mock_psutil = MagicMock()
        mock_psutil.virtual_memory.return_value = MagicMock(total=32 * 1024**3)
        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            assert detect_qmd_mode() == "daemon"

    def test_detect_qmd_mode_with_low_ram(self):
        from comobot.agent.qmd_backend import detect_qmd_mode

        mock_psutil = MagicMock()
        mock_psutil.virtual_memory.return_value = MagicMock(total=8 * 1024**3)
        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            assert detect_qmd_mode() == "on-demand"

    def test_detect_qmd_mode_without_psutil(self):
        """Without psutil, should default to on-demand."""
        # Force ImportError by removing psutil from modules
        import sys

        from comobot.agent.qmd_backend import detect_qmd_mode

        original = sys.modules.get("psutil")
        sys.modules["psutil"] = None  # type: ignore
        try:
            # detect_qmd_mode catches ImportError internally
            result = detect_qmd_mode()
            assert result == "on-demand"
        finally:
            if original is not None:
                sys.modules["psutil"] = original
            else:
                sys.modules.pop("psutil", None)

    @pytest.mark.asyncio
    async def test_qmd_backend_init_fails_without_binary(self, tmp_workspace):
        from comobot.agent.qmd_backend import QMDBackend

        config = QMDConfig(enabled=True, command="nonexistent_qmd_binary_xyz")
        backend = QMDBackend(config, tmp_workspace)

        # Mock both shutil.which and Path.exists to prevent finding real bun/curl
        with patch("comobot.agent.qmd_backend.shutil.which", return_value=None):
            with patch("pathlib.Path.exists", return_value=False):
                with pytest.raises(FileNotFoundError, match="not (found|available)"):
                    await backend.initialize()
        assert backend.is_running is False

    @pytest.mark.asyncio
    async def test_qmd_auto_install_uses_local_binary(self, tmp_workspace):
        """If qmd is already installed locally in .qmd/node_modules, use it."""
        from comobot.agent.qmd_backend import QMDManager

        config = QMDConfig(enabled=True)
        manager = QMDManager(config, tmp_workspace)

        # Create fake local binary
        local_bin = tmp_workspace / ".qmd" / "node_modules" / ".bin" / "qmd"
        local_bin.parent.mkdir(parents=True, exist_ok=True)
        local_bin.write_text("#!/bin/sh\necho fake")
        local_bin.chmod(0o755)

        found = manager._find_qmd_binary()
        assert found is not None
        assert "node_modules" in found


# ── Settings API endpoint wiring ─────────────────────────────────


class TestSettingsAPIWiring:
    """Test that the settings endpoint correctly accesses the memory backend."""

    @pytest.mark.asyncio
    async def test_get_qmd_settings_with_no_agent(self):
        """When no agent is in app.state, should return stopped."""
        from unittest.mock import MagicMock

        from comobot.api.routes.settings import _get_memory_backend

        request = MagicMock()
        request.app.state = MagicMock(spec=[])  # No attributes
        result = _get_memory_backend(request)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_qmd_settings_with_agent(self):
        """When agent has _memory_backend, it should be returned."""
        from unittest.mock import MagicMock

        from comobot.api.routes.settings import _get_memory_backend

        mock_backend = MagicMock(spec=MemoryBackend)
        mock_agent = MagicMock()
        mock_agent._memory_backend = mock_backend

        request = MagicMock()
        request.app.state.agent = mock_agent
        result = _get_memory_backend(request)
        assert result is mock_backend
