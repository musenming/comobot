"""Tests for multi-channel session sync and broadcast behaviour."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from comobot.bus.events import InboundMessage
from comobot.bus.queue import MessageBus
from comobot.db.connection import Database
from comobot.db.migrations import run_migrations
from comobot.session.sqlite_manager import SQLiteSessionManager

# ---------------------------------------------------------------------------
# Bug 1: External channel messages must be persisted to DB so they survive
#         a page refresh in the web UI.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_append_messages_persists_text(tmp_path: Path) -> None:
    """Plain text user+assistant messages end up in the DB."""
    db = Database(tmp_path / "test.db")
    await db.connect()
    await run_migrations(db)
    sm = SQLiteSessionManager(db)

    sid = await sm.ensure_session("telegram:999")
    await sm.append_messages(
        sid,
        [
            {"role": "user", "content": "hello", "timestamp": "t1"},
            {"role": "assistant", "content": "hi!", "timestamp": "t2"},
        ],
    )

    rows = await db.fetchall(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id", (sid,)
    )
    assert len(rows) == 2
    assert rows[0]["role"] == "user"
    assert rows[0]["content"] == "hello"
    assert rows[1]["role"] == "assistant"
    assert rows[1]["content"] == "hi!"
    await db.close()


@pytest.mark.asyncio
async def test_append_messages_handles_list_content(tmp_path: Path) -> None:
    """Multimodal (list) content is flattened to text."""
    db = Database(tmp_path / "test.db")
    await db.connect()
    await run_migrations(db)
    sm = SQLiteSessionManager(db)

    sid = await sm.ensure_session("telegram:999")
    await sm.append_messages(
        sid,
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "look at this"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                ],
                "timestamp": "t1",
            },
        ],
    )

    rows = await db.fetchall("SELECT content FROM messages WHERE session_id = ?", (sid,))
    assert len(rows) == 1
    assert "look at this" in rows[0]["content"]
    await db.close()


@pytest.mark.asyncio
async def test_append_messages_handles_none_content(tmp_path: Path) -> None:
    """content=None is stored as empty string."""
    db = Database(tmp_path / "test.db")
    await db.connect()
    await run_migrations(db)
    sm = SQLiteSessionManager(db)

    sid = await sm.ensure_session("telegram:999")
    await sm.append_messages(
        sid,
        [
            {"role": "user", "content": None, "timestamp": "t1"},
        ],
    )

    rows = await db.fetchall("SELECT content FROM messages WHERE session_id = ?", (sid,))
    assert len(rows) == 1
    assert rows[0]["content"] == ""
    await db.close()


@pytest.mark.asyncio
async def test_append_messages_skips_tool_role(tmp_path: Path) -> None:
    """Tool messages are NOT persisted (only user/assistant)."""
    db = Database(tmp_path / "test.db")
    await db.connect()
    await run_migrations(db)
    sm = SQLiteSessionManager(db)

    sid = await sm.ensure_session("telegram:999")
    await sm.append_messages(
        sid,
        [
            {"role": "user", "content": "x", "timestamp": "t1"},
            {"role": "tool", "content": "tool output", "tool_call_id": "tc1"},
            {"role": "assistant", "content": "done", "timestamp": "t3"},
        ],
    )

    rows = await db.fetchall("SELECT role FROM messages WHERE session_id = ? ORDER BY id", (sid,))
    assert [r["role"] for r in rows] == ["user", "assistant"]
    await db.close()


@pytest.mark.asyncio
async def test_ensure_session_idempotent(tmp_path: Path) -> None:
    """Calling ensure_session twice returns the same ID."""
    db = Database(tmp_path / "test.db")
    await db.connect()
    await run_migrations(db)
    sm = SQLiteSessionManager(db)

    id1 = await sm.ensure_session("telegram:999")
    id2 = await sm.ensure_session("telegram:999")
    assert id1 == id2
    await db.close()


# ---------------------------------------------------------------------------
# Bug 2: Web-originated messages must NOT be broadcast to /ws/sessions,
#         because the /ws/chat WebSocket already delivers them.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_web_channel_skips_broadcast() -> None:
    """_process_message must NOT broadcast when channel == 'web'."""
    from comobot.agent.loop import AgentLoop

    bus = MessageBus()
    provider = MagicMock()
    workspace = Path("/tmp/test_ws")
    workspace.mkdir(exist_ok=True)

    agent = AgentLoop(bus=bus, provider=provider, workspace=workspace)

    # Mock _broadcast_session_messages to track calls
    agent._broadcast_session_messages = AsyncMock()
    agent._sync_session_to_db = AsyncMock()

    # Mock _run_agent_loop to return a simple response
    agent._run_agent_loop = AsyncMock(
        return_value=(
            "test response",
            [],
            [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "test response"},
            ],
        )
    )

    # Simulate a web message to a feishu session
    msg = InboundMessage(
        channel="web",
        sender_id="user",
        chat_id="feishu:ou_123",
        content="hello",
    )
    await agent._process_message(msg, session_key="feishu:ou_123")

    # _broadcast_session_messages should NOT have been called
    agent._broadcast_session_messages.assert_not_called()


@pytest.mark.asyncio
async def test_external_channel_does_broadcast() -> None:
    """_process_message MUST broadcast when channel is external (e.g. telegram)."""
    from comobot.agent.loop import AgentLoop

    bus = MessageBus()
    provider = MagicMock()
    workspace = Path("/tmp/test_ws2")
    workspace.mkdir(exist_ok=True)

    agent = AgentLoop(bus=bus, provider=provider, workspace=workspace)

    agent._broadcast_session_messages = AsyncMock()
    agent._sync_session_to_db = AsyncMock()

    agent._run_agent_loop = AsyncMock(
        return_value=(
            "response",
            [],
            [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "response"},
            ],
        )
    )

    msg = InboundMessage(
        channel="telegram",
        sender_id="user",
        chat_id="12345",
        content="hi",
    )
    await agent._process_message(msg)

    # _broadcast_session_messages MUST be called for external channels
    agent._broadcast_session_messages.assert_called_once()
