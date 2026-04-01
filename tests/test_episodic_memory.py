"""Tests for episodic memory system: store, extractor, injector."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from comobot.agent.episodic.models import EpisodicMemory


class MockDB:
    """Simple mock for Database with async methods."""

    def __init__(self):
        self._data: dict[str, dict] = {}
        self._last_sql = ""
        self._last_params = ()

    async def execute(self, sql: str, params=None):
        self._last_sql = sql
        self._last_params = params or ()

    async def fetchone(self, sql: str, params=None):
        self._last_sql = sql
        self._last_params = params or ()
        if params and len(params) > 0:
            key = str(params[0])
            if key in self._data:
                return self._data[key]
        return None

    async def fetchall(self, sql: str, params=None):
        self._last_sql = sql
        return list(self._data.values())


class TestEpisodicMemory:
    def test_defaults(self):
        mem = EpisodicMemory(id="ep_20260330_001", type="fact", content="Test fact")
        assert mem.confidence == 1.0
        assert mem.status == "active"
        assert mem.access_count == 0
        assert mem.tags == []

    def test_all_types(self):
        for t in ("task", "fact", "preference", "feedback"):
            mem = EpisodicMemory(id="ep_test", type=t, content="Test")
            assert mem.type == t


class TestEpisodicMemoryStore:
    @pytest.fixture
    def workspace(self, tmp_path: Path) -> Path:
        return tmp_path

    @pytest.fixture
    def db(self):
        return MockDB()

    @pytest.fixture
    def store(self, workspace, db):
        from comobot.agent.episodic.store import EpisodicMemoryStore

        return EpisodicMemoryStore(workspace, db)

    @pytest.mark.asyncio
    async def test_create_generates_file(self, store, workspace):
        mem = EpisodicMemory(
            id="",
            type="fact",
            content="User prefers Python 3.11",
            tags=["python", "version"],
            source_session="web:123",
        )
        result = await store.create(mem)
        assert result.id.startswith("ep_")
        assert result.file_path.startswith("episodic/")

        episodic_dir = workspace / "episodic"
        md_files = list(episodic_dir.glob("*.md"))
        assert len(md_files) == 1

        content = md_files[0].read_text()
        assert "User prefers Python 3.11" in content
        assert "type: fact" in content
        assert '"python"' in content

    @pytest.mark.asyncio
    async def test_create_id_format(self, store):
        import re

        mem = EpisodicMemory(id="", type="task", content="Test")
        result = await store.create(mem)
        assert re.match(r"ep_\d{8}_\d{3}", result.id)

    @pytest.mark.asyncio
    async def test_get_returns_content(self, store, workspace, db):
        mem = EpisodicMemory(
            id="", type="fact", content="Important fact", tags=["test"]
        )
        created = await store.create(mem)

        db._data[created.id] = {
            "id": created.id,
            "type": "fact",
            "content": "Important fact",
            "confidence": 1.0,
            "source_session": "",
            "source_channel": "",
            "tags": '["test"]',
            "file_path": created.file_path,
            "created_at": "2026-03-30",
            "last_accessed_at": None,
            "access_count": 0,
            "status": "active",
        }

        fetched = await store.get(created.id)
        assert fetched is not None
        assert fetched["content"] == "Important fact"
        assert fetched["tags"] == ["test"]
        assert "file_content" in fetched

    @pytest.mark.asyncio
    async def test_delete_is_soft(self, store, db):
        mem = EpisodicMemory(id="", type="fact", content="To delete")
        created = await store.create(mem)

        result = await store.delete(created.id)
        assert result is True
        assert "archived" in db._last_params

    @pytest.mark.asyncio
    async def test_record_access(self, store, db):
        await store.record_access("ep_20260330_001")
        assert "access_count" in db._last_sql

    @pytest.mark.asyncio
    async def test_render_markdown_format(self, store):
        mem = EpisodicMemory(
            id="ep_test_001",
            type="preference",
            content="User likes dark mode",
            confidence=0.9,
            tags=["ui", "preference"],
            source_session="web:1",
        )
        md = store._render_markdown(mem)
        assert md.startswith("---")
        assert "id: ep_test_001" in md
        assert "type: preference" in md
        assert "confidence: 0.9" in md
        assert "User likes dark mode" in md


class TestMemoryExtractor:
    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        provider.chat = AsyncMock()
        return provider

    @pytest.fixture
    def mock_store(self):
        store = MagicMock()
        store.create = AsyncMock(side_effect=lambda m: m)
        return store

    @pytest.mark.asyncio
    async def test_extract_parses_memories(self, mock_provider, mock_store):
        from comobot.agent.episodic.extractor import MemoryExtractor

        mock_provider.chat.return_value = MagicMock(
            content=json.dumps({
                "memories": [
                    {
                        "type": "fact",
                        "content": "User uses PostgreSQL 14",
                        "confidence": 0.9,
                        "tags": ["database"],
                    },
                    {
                        "type": "preference",
                        "content": "User prefers functional style",
                        "confidence": 0.8,
                        "tags": ["coding"],
                    },
                ]
            })
        )

        extractor = MemoryExtractor(mock_store, mock_provider, confidence_threshold=0.6)
        results = await extractor.extract(
            [
                {"role": "user", "content": "I use PostgreSQL 14"},
                {"role": "assistant", "content": "Noted."},
            ],
            source_session="test:1",
        )
        assert len(results) == 2
        assert results[0].type == "fact"
        assert mock_store.create.await_count == 2

    @pytest.mark.asyncio
    async def test_extract_filters_low_confidence(self, mock_provider, mock_store):
        from comobot.agent.episodic.extractor import MemoryExtractor

        mock_provider.chat.return_value = MagicMock(
            content=json.dumps({
                "memories": [
                    {"type": "fact", "content": "Maybe...", "confidence": 0.3, "tags": []},
                    {"type": "fact", "content": "Definitely", "confidence": 0.9, "tags": []},
                ]
            })
        )

        extractor = MemoryExtractor(mock_store, mock_provider, confidence_threshold=0.6)
        results = await extractor.extract(
            [{"role": "user", "content": "test"}],
        )
        assert len(results) == 1
        assert results[0].content == "Definitely"

    @pytest.mark.asyncio
    async def test_extract_handles_empty_conversation(self, mock_provider, mock_store):
        from comobot.agent.episodic.extractor import MemoryExtractor

        extractor = MemoryExtractor(mock_store, mock_provider)
        results = await extractor.extract([])
        assert results == []
        mock_provider.chat.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_extract_handles_llm_error(self, mock_provider, mock_store):
        from comobot.agent.episodic.extractor import MemoryExtractor

        mock_provider.chat.side_effect = RuntimeError("API error")
        extractor = MemoryExtractor(mock_store, mock_provider)
        results = await extractor.extract(
            [{"role": "user", "content": "test"}],
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_extract_skips_process_messages(self, mock_provider, mock_store):
        from comobot.agent.episodic.extractor import MemoryExtractor

        mock_provider.chat.return_value = MagicMock(
            content=json.dumps({"memories": []})
        )
        extractor = MemoryExtractor(mock_store, mock_provider)
        await extractor.extract([
            {"role": "user", "content": "Hello"},
            {"role": "process", "content": '{"type": "plan"}'},
            {"role": "assistant", "content": "Hi"},
        ])
        # Verify process messages were filtered in conversation
        call_args = mock_provider.chat.call_args
        user_content = call_args.kwargs["messages"][1]["content"]
        assert "process:" not in user_content

    def test_format_conversation(self):
        from comobot.agent.episodic.extractor import MemoryExtractor

        result = MemoryExtractor._format_conversation([
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "process", "content": "skip me"},
        ])
        assert "user: Hello" in result
        assert "assistant: Hi there" in result
        assert "process" not in result

    def test_parse_response_json(self):
        from comobot.agent.episodic.extractor import MemoryExtractor

        result = MemoryExtractor._parse_response(
            json.dumps({"memories": [{"type": "fact", "content": "test"}]})
        )
        assert len(result) == 1

    def test_parse_response_markdown_json(self):
        from comobot.agent.episodic.extractor import MemoryExtractor

        result = MemoryExtractor._parse_response(
            '```json\n{"memories": [{"type": "fact", "content": "test"}]}\n```'
        )
        assert len(result) == 1

    def test_parse_response_none(self):
        from comobot.agent.episodic.extractor import MemoryExtractor

        assert MemoryExtractor._parse_response(None) == []
        assert MemoryExtractor._parse_response("") == []


class TestMemoryInjector:
    @pytest.fixture
    def workspace(self, tmp_path: Path) -> Path:
        (tmp_path / "feedback").mkdir()
        (tmp_path / "episodic").mkdir()
        return tmp_path

    def test_inject_with_feedback(self, workspace):
        from comobot.agent.episodic.injector import MemoryInjector

        # Write a feedback file
        fb_file = workspace / "feedback" / "fb_001.md"
        fb_file.write_text(
            "---\nid: fb_001\ntype: feedback\n---\n\n"
            "User prefers concise responses, no trailing summaries"
        )

        injector = MemoryInjector(workspace)
        parts = injector.inject("How do I deploy?")
        assert len(parts) >= 1
        assert "User Preferences" in parts[0]
        assert "concise responses" in parts[0]

    def test_inject_empty_feedback_dir(self, workspace):
        from comobot.agent.episodic.injector import MemoryInjector

        injector = MemoryInjector(workspace)
        parts = injector.inject("Hello")
        # No feedback files, no episodic engine
        assert parts == []

    def test_inject_strips_frontmatter(self, workspace):
        from comobot.agent.episodic.injector import MemoryInjector

        fb_file = workspace / "feedback" / "fb_002.md"
        fb_file.write_text(
            "---\nid: fb_002\ntype: feedback\nconfidence: 0.9\n---\n\nActual content here"
        )

        injector = MemoryInjector(workspace)
        parts = injector.inject("test")
        assert "Actual content here" in parts[0]
        # Frontmatter should not appear in injected text
        assert "confidence: 0.9" not in parts[0]

    def test_inject_with_memory_engine(self, workspace):
        from comobot.agent.episodic.injector import MemoryInjector

        # Mock memory engine
        mock_engine = MagicMock()
        mock_chunk = MagicMock()
        mock_chunk.score = 0.7
        mock_chunk.content = "Previously deployed using Docker Compose"
        mock_engine.search.return_value = [mock_chunk]

        injector = MemoryInjector(workspace, memory_engine=mock_engine, max_inject=5)
        parts = injector.inject("How to deploy?")

        # Should have episodic section
        episodic_parts = [p for p in parts if "Past Experience" in p]
        assert len(episodic_parts) == 1
        assert "Docker Compose" in episodic_parts[0]

    def test_inject_filters_low_score(self, workspace):
        from comobot.agent.episodic.injector import MemoryInjector

        mock_engine = MagicMock()
        mock_chunk = MagicMock()
        mock_chunk.score = 0.1  # Below threshold
        mock_engine.search.return_value = [mock_chunk]

        injector = MemoryInjector(workspace, memory_engine=mock_engine)
        parts = injector.inject("Unrelated query")
        episodic_parts = [p for p in parts if "Past Experience" in p]
        assert len(episodic_parts) == 0


class TestSetDbSessionManagerInitializesExtractor:
    """Regression test: set_db_session_manager must initialize MemoryExtractor.

    Bug: SQLiteSessionManager stores DB as ``self.db`` (public), but
    ``set_db_session_manager`` accessed ``db_sm._db`` (private).
    ``hasattr`` returned False, so extractor was never created.
    """

    def test_extractor_initialized_with_public_db_attr(self):
        """MemoryExtractor must be set when db_sm exposes ``db``."""
        from unittest.mock import MagicMock, patch

        # Minimal mock of AgentLoop – only need the method under test
        from comobot.agent.loop import AgentLoop

        # Build a mock db_sm whose attribute is ``db`` (not ``_db``)
        mock_db = MagicMock()
        mock_db_sm = MagicMock(spec=[])  # empty spec so no auto-attrs
        mock_db_sm.db = mock_db  # public attr, like SQLiteSessionManager
        assert not hasattr(mock_db_sm, "_db")

        # Create a minimal AgentLoop with episodic enabled
        with patch.object(AgentLoop, "__init__", lambda self: None):
            loop = AgentLoop.__new__(AgentLoop)

        # Set minimum attributes that set_db_session_manager needs
        from comobot.config.schema import EpisodicMemoryConfig

        loop._episodic_config = EpisodicMemoryConfig(enabled=True)
        loop._memory_extractor = None
        loop._episodic_store = None
        loop._db_session_manager = None
        loop.workspace = Path("/tmp/test_workspace_episodic")
        loop.workspace.mkdir(exist_ok=True)
        loop.provider = MagicMock()
        loop.model = "test-model"
        loop._memory_engine = None

        loop.set_db_session_manager(mock_db_sm)

        assert loop._memory_extractor is not None, (
            "MemoryExtractor should be initialized when db_sm has public 'db' attr"
        )
        assert loop._episodic_store is not None
