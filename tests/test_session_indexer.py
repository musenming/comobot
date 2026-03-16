"""Tests for session_indexer: sanitizer, indexer, and debounce behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from comobot.agent.session_indexer import SessionIndexer, SessionSanitizer
from comobot.config.schema import SessionIndexConfig


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Create a minimal workspace directory structure."""
    (tmp_path / "sessions").mkdir()
    (tmp_path / "memory").mkdir()
    return tmp_path


def _write_session(path: Path, messages: list[dict], key: str = "telegram:user123") -> None:
    """Write a JSONL session file with metadata + messages."""
    metadata = {
        "_type": "metadata",
        "key": key,
        "created_at": "2026-03-15T10:30:00",
        "updated_at": "2026-03-16T10:00:00",
        "metadata": {},
        "last_consolidated": 0,
    }
    with path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(metadata) + "\n")
        for msg in messages:
            f.write(json.dumps(msg) + "\n")


# ── SessionSanitizer tests ──────────────────────────────────────


class TestSessionSanitizer:
    def test_basic_user_assistant(self, tmp_path: Path) -> None:
        """Rule: preserve user/assistant text content."""
        path = tmp_path / "test.jsonl"
        _write_session(
            path,
            [
                {"role": "user", "content": "Hello", "timestamp": "2026-03-15T10:30:00"},
                {"role": "assistant", "content": "Hi there!", "timestamp": "2026-03-15T10:30:05"},
            ],
        )
        result = SessionSanitizer().sanitize(path)
        assert "**User**: Hello" in result
        assert "**Assistant**: Hi there!" in result

    def test_strips_tool_result_messages(self, tmp_path: Path) -> None:
        """Rule: tool role messages should be skipped."""
        path = tmp_path / "test.jsonl"
        _write_session(
            path,
            [
                {"role": "user", "content": "Read file"},
                {
                    "role": "assistant",
                    "content": "Let me read it",
                    "tool_calls": [
                        {"function": {"name": "read_file", "arguments": '{"path": "/tmp/x"}'}}
                    ],
                },
                {"role": "tool", "content": "file contents here...", "tool_call_id": "tc1"},
            ],
        )
        result = SessionSanitizer().sanitize(path)
        assert "file contents here" not in result
        assert "[called: read_file]" in result

    def test_strips_base64_images(self, tmp_path: Path) -> None:
        """Rule: base64 images replaced with [image]."""
        b64 = "data:image/png;base64," + "A" * 200
        path = tmp_path / "test.jsonl"
        _write_session(path, [{"role": "user", "content": f"Look at this {b64} image"}])
        result = SessionSanitizer().sanitize(path)
        assert "[image]" in result
        assert "AAAA" not in result

    def test_truncates_long_content(self, tmp_path: Path) -> None:
        """Rule: content > 500 chars is truncated."""
        long_text = "x" * 1000
        path = tmp_path / "test.jsonl"
        _write_session(path, [{"role": "user", "content": long_text}])
        result = SessionSanitizer().sanitize(path)
        assert "[truncated]" in result
        assert len(result) < 1000

    def test_frontmatter_generation(self, tmp_path: Path) -> None:
        """Rule: frontmatter includes session_key, created_at, message_count."""
        path = tmp_path / "test.jsonl"
        _write_session(
            path,
            [
                {"role": "user", "content": "msg1"},
                {"role": "assistant", "content": "msg2"},
            ],
            key="telegram:user123",
        )
        result = SessionSanitizer().sanitize(path)
        assert "session_key: telegram:user123" in result
        assert "created_at: 2026-03-15T10:30:00" in result
        assert "message_count: 2" in result

    def test_multimodal_content(self, tmp_path: Path) -> None:
        """Rule: multimodal list content handled correctly."""
        path = tmp_path / "test.jsonl"
        _write_session(
            path,
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is this?"},
                        {"type": "image_url", "image_url": {"url": "data:..."}},
                    ],
                }
            ],
        )
        result = SessionSanitizer().sanitize(path)
        assert "What is this?" in result
        assert "[image]" in result


# ── SessionIndexer tests ────────────────────────────────────────


class TestSessionIndexer:
    def _make_config(self, **overrides) -> SessionIndexConfig:
        defaults = {
            "enabled": True,
            "delta_threshold_bytes": 100,  # Low threshold for testing
            "delta_threshold_lines": 5,
            "debounce_seconds": 0,  # No debounce for tests
            "max_transcript_age_days": 90,
            "exclude_channels": [],
        }
        defaults.update(overrides)
        return SessionIndexConfig(**defaults)

    @pytest.mark.asyncio
    async def test_full_index_creates_transcript(self, tmp_workspace: Path) -> None:
        """First-time indexing creates a transcript file."""
        session_path = tmp_workspace / "sessions" / "telegram_user123.jsonl"
        _write_session(
            session_path,
            [{"role": "user", "content": f"message {i}"} for i in range(10)],
        )

        config = self._make_config()
        indexer = SessionIndexer(config, None, tmp_workspace / "sessions", tmp_workspace)
        await indexer.check_and_index()

        transcript = tmp_workspace / ".session_index" / "transcripts" / "telegram_user123.md"
        assert transcript.exists()
        content = transcript.read_text()
        assert "message 0" in content
        assert "message 9" in content

    @pytest.mark.asyncio
    async def test_incremental_index(self, tmp_workspace: Path) -> None:
        """After threshold, new messages are appended to existing transcript."""
        session_path = tmp_workspace / "sessions" / "test_session.jsonl"
        _write_session(
            session_path,
            [{"role": "user", "content": f"original {i}"} for i in range(10)],
        )

        config = self._make_config(delta_threshold_lines=3)
        indexer = SessionIndexer(config, None, tmp_workspace / "sessions", tmp_workspace)
        await indexer.check_and_index()

        transcript = tmp_workspace / ".session_index" / "transcripts" / "test_session.md"
        assert transcript.exists()
        original_size = transcript.stat().st_size

        # Append new messages to session
        with session_path.open("a", encoding="utf-8") as f:
            for i in range(5):
                f.write(json.dumps({"role": "user", "content": f"new message {i}"}) + "\n")

        # Reset debounce
        indexer._last_run = 0.0
        await indexer.check_and_index()

        new_content = transcript.read_text()
        assert "new message 0" in new_content
        assert transcript.stat().st_size > original_size

    @pytest.mark.asyncio
    async def test_debounce(self, tmp_workspace: Path) -> None:
        """check_and_index should be debounced."""
        session_path = tmp_workspace / "sessions" / "test.jsonl"
        _write_session(session_path, [{"role": "user", "content": "hello"}])

        config = self._make_config(debounce_seconds=60)
        indexer = SessionIndexer(config, None, tmp_workspace / "sessions", tmp_workspace)

        # First call should index
        await indexer.check_and_index()
        transcript = tmp_workspace / ".session_index" / "transcripts" / "test.md"
        assert transcript.exists()

        # Modify session
        with session_path.open("a", encoding="utf-8") as f:
            for i in range(10):
                f.write(json.dumps({"role": "user", "content": f"new {i}"}) + "\n")

        # Second call should be debounced (within 60s)
        original_content = transcript.read_text()
        await indexer.check_and_index()
        assert transcript.read_text() == original_content

    @pytest.mark.asyncio
    async def test_exclude_channels(self, tmp_workspace: Path) -> None:
        """Excluded channels should not be indexed."""
        for name in ["telegram_user1.jsonl", "cron_abc.jsonl"]:
            _write_session(
                tmp_workspace / "sessions" / name,
                [{"role": "user", "content": "test"}],
            )

        config = self._make_config(exclude_channels=["cron"])
        indexer = SessionIndexer(config, None, tmp_workspace / "sessions", tmp_workspace)
        await indexer.check_and_index()

        transcripts = list((tmp_workspace / ".session_index" / "transcripts").glob("*.md"))
        names = [t.stem for t in transcripts]
        assert "telegram_user1" in names
        assert "cron_abc" not in names

    @pytest.mark.asyncio
    async def test_disabled_does_nothing(self, tmp_workspace: Path) -> None:
        """enabled=False should skip all indexing."""
        session_path = tmp_workspace / "sessions" / "test.jsonl"
        _write_session(session_path, [{"role": "user", "content": "hello"}])

        config = self._make_config(enabled=False)
        indexer = SessionIndexer(config, None, tmp_workspace / "sessions", tmp_workspace)
        await indexer.check_and_index()

        transcripts_dir = tmp_workspace / ".session_index" / "transcripts"
        if transcripts_dir.exists():
            assert list(transcripts_dir.glob("*.md")) == []

    @pytest.mark.asyncio
    async def test_state_persistence(self, tmp_workspace: Path) -> None:
        """Index state should be persisted to state.json and reloaded."""
        session_path = tmp_workspace / "sessions" / "test.jsonl"
        _write_session(
            session_path,
            [{"role": "user", "content": f"msg {i}"} for i in range(10)],
        )

        config = self._make_config()
        indexer = SessionIndexer(config, None, tmp_workspace / "sessions", tmp_workspace)
        await indexer.check_and_index()

        state_file = tmp_workspace / ".session_index" / "state.json"
        assert state_file.exists()

        state_data = json.loads(state_file.read_text())
        assert "test.jsonl" in state_data
        assert state_data["test.jsonl"]["last_offset"] > 0

        # Create a new indexer — state should be loaded from disk
        indexer2 = SessionIndexer(config, None, tmp_workspace / "sessions", tmp_workspace)
        assert "test.jsonl" in indexer2._index_state
        assert indexer2._index_state["test.jsonl"].last_offset > 0


# ── Integration test ────────────────────────────────────────────


class TestSessionIndexIntegration:
    @pytest.mark.asyncio
    async def test_end_to_end_indexing_and_search(self, tmp_workspace: Path) -> None:
        """End-to-end: JSONL → index → memory_search finds session content."""
        from comobot.agent.memory_search import MemorySearchEngine

        # Create a session with distinctive content
        session_path = tmp_workspace / "sessions" / "telegram_user42.jsonl"
        _write_session(
            session_path,
            [
                {"role": "user", "content": "comobot has a memory leak problem"},
                {
                    "role": "assistant",
                    "content": "SessionManager._cache has no maxsize causing memory growth",
                },
                {"role": "user", "content": "How to fix it?"},
                {"role": "assistant", "content": "Add an LRU limit to the cache"},
            ],
        )

        # Create engine and indexer
        engine = MemorySearchEngine(workspace=tmp_workspace)
        config = SessionIndexConfig(
            enabled=True,
            delta_threshold_bytes=10,
            delta_threshold_lines=2,
            debounce_seconds=0,
        )
        indexer = SessionIndexer(
            config=config,
            memory_engine=engine,
            sessions_dir=tmp_workspace / "sessions",
            workspace=tmp_workspace,
        )

        # Run indexing
        await indexer.check_and_index()

        # Search for session content
        results = engine.search("memory leak", max_results=5)
        assert len(results) > 0
        # Verify the result comes from session transcript
        found = any(".session_index/transcripts/" in r.file_path for r in results)
        assert found, (
            f"Expected session transcript in results, got: {[r.file_path for r in results]}"
        )
