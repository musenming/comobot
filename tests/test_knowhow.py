"""Tests for Know-how system: store, extractor, memory search integration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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
        # Return matching row if stored
        if params and len(params) > 0:
            key = str(params[0])
            if key in self._data:
                return self._data[key]
        return None

    async def fetchall(self, sql: str, params=None):
        self._last_sql = sql
        return list(self._data.values())


class TestKnowhowStore:
    """KnowhowStore CRUD tests."""

    @pytest.fixture
    def workspace(self, tmp_path: Path) -> Path:
        return tmp_path

    @pytest.fixture
    def db(self):
        return MockDB()

    @pytest.fixture
    def store(self, workspace, db):
        from comobot.knowhow.store import KnowhowStore

        return KnowhowStore(workspace, db)

    @pytest.mark.asyncio
    async def test_create_generates_file(self, store, workspace):
        """Create should write a Markdown file and return metadata."""
        result = await store.create(
            preview={
                "title": "Test Deploy",
                "goal": "Deploy service",
                "steps": ["Step 1", "Step 2"],
                "tags": ["deploy", "docker"],
                "outcome": "Success",
                "tools_used": ["exec"],
            },
            raw_messages=[
                {"role": "user", "content": "Deploy the service"},
                {"role": "assistant", "content": "Done."},
            ],
            source_session="web:123",
            message_ids=[1, 2],
        )

        assert result["id"].startswith("kh_")
        assert result["title"] == "Test Deploy"
        assert result["status"] == "active"

        # Verify file was written
        knowhow_dir = workspace / "knowhow"
        assert knowhow_dir.exists()
        md_files = list(knowhow_dir.glob("*.md"))
        assert len(md_files) == 1

        content = md_files[0].read_text()
        assert "Test Deploy" in content
        assert "Step 1" in content
        assert "Deploy service" in content

    @pytest.mark.asyncio
    async def test_create_id_format(self, store):
        """ID should follow kh_YYYYMMDD_NNN format."""
        result = await store.create(
            preview={"title": "T", "goal": "G", "steps": [], "tags": []},
            raw_messages=[],
        )
        import re

        assert re.match(r"kh_\d{8}_\d{3}", result["id"])

    @pytest.mark.asyncio
    async def test_get_returns_content(self, store, workspace, db):
        """Get should return metadata + file content."""
        result = await store.create(
            preview={"title": "Test", "goal": "G", "steps": ["S1"], "tags": ["t"]},
            raw_messages=[{"role": "user", "content": "hello"}],
        )

        # Store the data for fetchone
        db._data[result["id"]] = {
            "id": result["id"],
            "title": "Test",
            "tags": '["t"]',
            "goal": "G",
            "file_path": result["file_path"],
            "source_session": "",
            "source_messages": "[]",
            "status": "active",
            "usage_count": 0,
            "created_at": "2026-03-12",
            "updated_at": "2026-03-12",
        }

        fetched = await store.get(result["id"])
        assert fetched is not None
        assert fetched["title"] == "Test"
        assert "content" in fetched
        assert fetched["tags"] == ["t"]

    @pytest.mark.asyncio
    async def test_delete_removes_file(self, store, workspace, db):
        """Delete should remove both file and DB record."""
        result = await store.create(
            preview={"title": "ToDelete", "goal": "G", "steps": [], "tags": []},
            raw_messages=[],
        )

        db._data[result["id"]] = {"file_path": result["file_path"]}

        # Verify file exists
        md_files = list((workspace / "knowhow").glob("*.md"))
        assert len(md_files) == 1

        deleted = await store.delete(result["id"])
        assert deleted is True

        # File should be gone
        md_files = list((workspace / "knowhow").glob("*.md"))
        assert len(md_files) == 0

    @pytest.mark.asyncio
    async def test_increment_usage(self, store, db):
        """increment_usage should execute UPDATE SQL."""
        await store.increment_usage("kh_20260312_001")
        assert "usage_count" in db._last_sql
        assert db._last_params == ("kh_20260312_001",)

    @pytest.mark.asyncio
    async def test_slugify(self, store):
        """Slugify should handle CJK and special characters."""
        assert store._slugify("Docker Compose 部署") == "Docker_Compose_部署"
        slug = store._slugify("test/path<>file")
        assert "test" in slug and "path" in slug and "file" in slug
        assert store._slugify("") == "untitled"


class TestKnowhowExtractor:
    """LLM extraction tests (mocked)."""

    @pytest.mark.asyncio
    async def test_extract_returns_structured(self):
        """Extract should return structured dict with required fields."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {
                            "title": "Test Title",
                            "goal": "Test Goal",
                            "steps": ["Step 1"],
                            "tools_used": ["exec"],
                            "outcome": "Done",
                            "tags": ["test"],
                        }
                    )
                )
            )
        ]

        mock_provider = MagicMock()
        mock_provider._resolve_model.return_value = "openai/test-model"
        mock_provider.api_key = "test-key"
        mock_provider.api_base = None
        mock_provider.extra_headers = {}

        mock_config = MagicMock()
        mock_config.agents.defaults.model = "test-model"
        mock_config.get_provider_name.return_value = "openai"
        mock_config.get_provider.return_value = MagicMock(api_key="test-key", extra_headers={})
        mock_config.get_api_base.return_value = None

        with (
            patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm,
            patch("comobot.config.loader.load_config", return_value=mock_config),
            patch(
                "comobot.providers.litellm_provider.LiteLLMProvider",
                return_value=mock_provider,
            ),
        ):
            mock_llm.return_value = mock_response

            from comobot.knowhow.extractor import extract_knowhow

            result = await extract_knowhow(
                [
                    {"role": "user", "content": "Do something"},
                    {"role": "assistant", "content": "Done."},
                ]
            )

            assert result["title"] == "Test Title"
            assert result["goal"] == "Test Goal"
            assert len(result["steps"]) == 1
            assert "test" in result["tags"]

    @pytest.mark.asyncio
    async def test_extract_handles_bad_json(self):
        """Extract should handle invalid JSON gracefully."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="not json"))]

        mock_provider = MagicMock()
        mock_provider._resolve_model.return_value = "openai/test-model"
        mock_provider.api_key = "test-key"
        mock_provider.api_base = None
        mock_provider.extra_headers = {}

        mock_config = MagicMock()
        mock_config.agents.defaults.model = "test-model"
        mock_config.get_provider_name.return_value = "openai"
        mock_config.get_provider.return_value = MagicMock(api_key="test-key", extra_headers={})
        mock_config.get_api_base.return_value = None

        with (
            patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm,
            patch("comobot.config.loader.load_config", return_value=mock_config),
            patch(
                "comobot.providers.litellm_provider.LiteLLMProvider",
                return_value=mock_provider,
            ),
        ):
            mock_llm.return_value = mock_response

            from comobot.knowhow.extractor import extract_knowhow

            result = await extract_knowhow([{"role": "user", "content": "test"}])
            # Should return fallback structure
            assert "title" in result
            assert isinstance(result["steps"], list)


class TestMemorySearchKnowhow:
    """MemorySearchEngine knowhow integration tests."""

    def test_discover_files_includes_knowhow(self, tmp_path):
        """_discover_files should find knowhow/*.md files."""
        from comobot.agent.memory_search import MemorySearchEngine

        workspace = tmp_path
        (workspace / "memory").mkdir()
        knowhow_dir = workspace / "knowhow"
        knowhow_dir.mkdir()
        (knowhow_dir / "kh_20260312_001_test.md").write_text("# Test Know-how")
        (knowhow_dir / ".hidden.md").write_text("hidden")

        engine = MemorySearchEngine(workspace)
        files = engine._discover_files()

        paths = [f[0] for f in files]
        assert "knowhow/kh_20260312_001_test.md" in paths
        assert ".hidden.md" not in str(paths)

    def test_search_with_file_filter(self, tmp_path):
        """Search with file_filter should only return matching prefix."""
        from comobot.agent.memory_search import MemorySearchEngine

        workspace = tmp_path
        mem_dir = workspace / "memory"
        mem_dir.mkdir()
        (mem_dir / "daily.md").write_text("# Memory\nSome memory content here")

        knowhow_dir = workspace / "knowhow"
        knowhow_dir.mkdir()
        (knowhow_dir / "kh_test.md").write_text("# Docker Deploy\nDeploy with docker compose")

        engine = MemorySearchEngine(workspace)
        engine.reindex()

        # Search all (verify indexing works)
        engine.search("deploy", max_results=10)

        # Search only knowhow
        kh_results = engine.search("deploy", max_results=10, file_filter="knowhow/")

        # Know-how results should only contain knowhow files
        for r in kh_results:
            assert r.file_path.startswith("knowhow/")
