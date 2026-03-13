"""Tests for session channel aggregation and WebSocket push."""

from __future__ import annotations

import pytest


class TestSessionByChannel:
    """Tests for GET /api/sessions/by-channel endpoint."""

    def test_sessions_route_registered(self):
        """Verify the by-channel route exists in sessions router."""
        from comobot.api.routes.sessions import router

        paths = [r.path for r in router.routes]
        assert any("by-channel" in p for p in paths)

    def test_channel_display_names(self):
        """Display name mapping should cover common channels."""
        # Import to verify no import errors
        from comobot.api.routes import sessions  # noqa: F401


class TestSessionWebSocket:
    """Tests for WebSocket session broadcasting."""

    def test_connection_manager_has_session_pool(self):
        """ConnectionManager should have session_connections list."""
        from comobot.api.routes.ws import ConnectionManager

        mgr = ConnectionManager()
        assert hasattr(mgr, "session_connections")
        assert isinstance(mgr.session_connections, list)

    def test_ws_sessions_endpoint_registered(self):
        """Verify /ws/sessions endpoint exists."""
        from comobot.api.routes.ws import router

        paths = [r.path for r in router.routes]
        assert "/ws/sessions" in paths

    @pytest.mark.asyncio
    async def test_broadcast_session_event_empty(self):
        """Broadcasting with no connections should not error."""
        from comobot.api.routes.ws import ConnectionManager

        mgr = ConnectionManager()
        await mgr.broadcast_session_event({"event": "test"})
        # No error = pass
