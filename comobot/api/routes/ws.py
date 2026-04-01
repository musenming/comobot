"""WebSocket endpoints for real-time log streaming, status updates, and chat."""

import asyncio
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from comobot.db.connection import Database

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections for broadcasting."""

    def __init__(self):
        self.log_connections: list[WebSocket] = []
        self.status_connections: list[WebSocket] = []
        self.cron_connections: list[WebSocket] = []
        self.session_connections: list[WebSocket] = []
        # Chat connections keyed by session_key
        self.chat_connections: dict[str, list[WebSocket]] = {}
        # Reference to RemoteConnectionManager (set during app init)
        self.remote_manager = None

    async def connect_logs(self, ws: WebSocket):
        await ws.accept()
        self.log_connections.append(ws)

    async def connect_status(self, ws: WebSocket):
        await ws.accept()
        self.status_connections.append(ws)

    async def connect_cron(self, ws: WebSocket):
        await ws.accept()
        self.cron_connections.append(ws)

    def register_chat(self, session_key: str, ws: WebSocket):
        if session_key not in self.chat_connections:
            self.chat_connections[session_key] = []
        if ws not in self.chat_connections[session_key]:
            self.chat_connections[session_key].append(ws)

    def unregister_chat(self, ws: WebSocket):
        for key in list(self.chat_connections):
            if ws in self.chat_connections[key]:
                self.chat_connections[key].remove(ws)
            if not self.chat_connections[key]:
                del self.chat_connections[key]

    def disconnect_logs(self, ws: WebSocket):
        if ws in self.log_connections:
            self.log_connections.remove(ws)

    def disconnect_status(self, ws: WebSocket):
        if ws in self.status_connections:
            self.status_connections.remove(ws)

    def disconnect_cron(self, ws: WebSocket):
        if ws in self.cron_connections:
            self.cron_connections.remove(ws)

    async def broadcast_log(self, data: dict):
        disconnected = []
        for ws in self.log_connections:
            try:
                await ws.send_json(data)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect_logs(ws)

    async def broadcast_status(self, data: dict):
        disconnected = []
        for ws in self.status_connections:
            try:
                await ws.send_json(data)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect_status(ws)

    async def broadcast_cron(self, data: dict):
        """Broadcast cron events (job_added, job_fired, job_updated)."""
        disconnected = []
        for ws in self.cron_connections:
            try:
                await ws.send_json(data)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect_cron(ws)

    async def connect_sessions(self, ws: WebSocket):
        await ws.accept()
        self.session_connections.append(ws)

    def disconnect_sessions(self, ws: WebSocket):
        if ws in self.session_connections:
            self.session_connections.remove(ws)

    async def broadcast_session_event(self, event: dict):
        """Broadcast session events (new_message) to all listeners."""
        disconnected = []
        for ws in self.session_connections:
            try:
                await ws.send_json(event)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect_sessions(ws)
        # Also forward to subscribed remote devices
        session_key = event.get("session_key")
        if session_key:
            await self._broadcast_to_remote(session_key, event)

    async def broadcast_chat(self, session_key: str, data: dict):
        """Send a message to all chat WebSocket clients for a given session."""
        connections = self.chat_connections.get(session_key, [])
        disconnected = []
        for ws in connections:
            try:
                await ws.send_json(data)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.unregister_chat(ws)
        # Also forward to subscribed remote devices
        await self._broadcast_to_remote(session_key, data)

    async def broadcast_session_update(
        self, session_key: str, *, title: str | None = None, summary: str | None = None
    ) -> None:
        """Broadcast session metadata update (title/summary) to web + remote devices."""
        event = {
            "event": "update-session",
            "session_key": session_key,
            "title": title,
            "summary": summary,
        }
        # Web clients
        disconnected = []
        for ws in self.session_connections:
            try:
                await ws.send_json(event)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect_sessions(ws)
        # Remote devices
        if self.remote_manager:
            try:
                await self.remote_manager.broadcast_to_subscribers(
                    session_key,
                    {
                        "t": "update-session",
                        "session_key": session_key,
                        "title": title,
                        "summary": summary,
                    },
                )
            except Exception:
                pass

    async def _broadcast_to_remote(self, session_key: str, data: dict) -> None:
        """Forward session events to mobile devices subscribed to this session."""
        if self.remote_manager:
            try:
                await self.remote_manager.broadcast_to_subscribers(
                    session_key,
                    {
                        "t": "new-message",
                        "sid": session_key,
                        "message": data,
                    },
                )
            except Exception:
                pass  # Don't let remote failures affect web clients


manager = ConnectionManager()


@router.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    """Real-time log streaming via WebSocket."""
    await manager.connect_logs(websocket)
    try:
        # Send initial recent logs
        db: Database = websocket.app.state.db
        recent = await db.fetchall("SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 50")
        if recent:
            for row in reversed(recent):
                await websocket.send_json(dict(row))

        # Keep connection alive and relay new logs
        while True:
            # Wait for client messages (ping/pong keepalive)
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                # Send ping to keep alive
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        manager.disconnect_logs(websocket)
    except Exception:
        manager.disconnect_logs(websocket)


@router.websocket("/ws/status")
async def ws_status(websocket: WebSocket):
    """Real-time agent/channel status updates."""
    await manager.connect_status(websocket)
    try:
        # Send initial status
        await websocket.send_json(
            {
                "type": "status",
                "agent": "online",
                "channels": {},
            }
        )

        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        manager.disconnect_status(websocket)
    except Exception:
        manager.disconnect_status(websocket)


@router.websocket("/ws/cron")
async def ws_cron(websocket: WebSocket):
    """Real-time cron job updates via WebSocket."""
    await manager.connect_cron(websocket)
    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        manager.disconnect_cron(websocket)
    except Exception:
        manager.disconnect_cron(websocket)


@router.websocket("/ws/sessions")
async def ws_sessions(websocket: WebSocket):
    """Real-time session message updates via WebSocket."""
    await manager.connect_sessions(websocket)
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        manager.disconnect_sessions(websocket)
    except Exception:
        manager.disconnect_sessions(websocket)


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """WebSocket endpoint for real-time chat with the agent."""
    await websocket.accept()
    db: Database = websocket.app.state.db
    current_session_key: str | None = None

    try:
        while True:
            raw = await websocket.receive_json()
            msg_type = raw.get("type", "message")

            if msg_type == "message":
                content = raw.get("content", "").strip()
                session_key = raw.get("session_key") or f"web:{uuid.uuid4().hex[:12]}"

                # Track this connection's session for cron delivery
                if session_key != current_session_key:
                    manager.unregister_chat(websocket)
                    manager.register_chat(session_key, websocket)
                    current_session_key = session_key

                if not content:
                    await websocket.send_json({"type": "error", "error": "Empty message"})
                    continue

                # Ensure session exists
                session = await db.fetchone(
                    "SELECT id FROM sessions WHERE session_key = ?", (session_key,)
                )
                if not session:
                    await db.execute(
                        "INSERT INTO sessions (session_key, platform) VALUES (?, 'web')",
                        (session_key,),
                    )
                    session = await db.fetchone(
                        "SELECT id FROM sessions WHERE session_key = ?", (session_key,)
                    )

                # Store user message
                await db.execute(
                    "INSERT INTO messages (session_id, role, content) VALUES (?, 'user', ?)",
                    (session["id"], content),
                )

                # Acknowledge receipt
                await websocket.send_json(
                    {
                        "type": "ack",
                        "session_key": session_key,
                    }
                )

                # Try to get agent and run
                agent = getattr(websocket.app.state, "agent", None)
                if agent and hasattr(agent, "process_direct"):
                    try:
                        session_id = session["id"]

                        # Send + persist thinking indicator
                        await websocket.send_json(
                            {
                                "type": "thinking",
                                "session_key": session_key,
                            }
                        )
                        await db.execute(
                            "INSERT INTO messages (session_id, role, content, tool_calls) "
                            "VALUES (?, 'process', '{}', ?)",
                            (session_id, '"thinking"'),
                        )

                        async def on_progress(
                            prog_content: str,
                            *,
                            tool_hint: bool = False,
                            step_id: str | None = None,
                            thinking: bool = False,
                            **_kw: object,
                        ):
                            if thinking:
                                msg_type = "thinking_content"
                            elif tool_hint:
                                msg_type = "tool_hint"
                            else:
                                msg_type = "progress"
                            payload: dict = {
                                "type": msg_type,
                                "session_key": session_key,
                                "content": prog_content,
                            }
                            if step_id:
                                payload["step_id"] = step_id
                            await websocket.send_json(payload)
                            # Thinking content is transient (shown during streaming,
                            # cleared when response arrives) — skip persistence.
                            if thinking:
                                return
                            # Persist to DB
                            import json as _json

                            process_data = {"content": prog_content}
                            if step_id:
                                process_data["step_id"] = step_id
                            await db.execute(
                                "INSERT INTO messages (session_id, role, content, tool_calls) "
                                "VALUES (?, 'process', ?, ?)",
                                (
                                    session_id,
                                    _json.dumps(process_data, ensure_ascii=False),
                                    _json.dumps(msg_type),
                                ),
                            )

                        response = await agent.process_direct(
                            content,
                            session_key=session_key,
                            channel="web",
                            chat_id=session_key,
                            on_progress=on_progress,
                            ws_send=websocket.send_json,
                        )
                        response_text = response if isinstance(response, str) else str(response)

                        # Store assistant message
                        await db.execute(
                            "INSERT INTO messages (session_id, role, content) "
                            "VALUES (?, 'assistant', ?)",
                            (session["id"], response_text),
                        )

                        await websocket.send_json(
                            {
                                "type": "response",
                                "session_key": session_key,
                                "content": response_text,
                                "role": "assistant",
                            }
                        )
                    except Exception as e:
                        error_msg = f"Agent error: {e}"
                        await websocket.send_json(
                            {
                                "type": "error",
                                "session_key": session_key,
                                "error": error_msg,
                            }
                        )
                else:
                    # No agent available, echo back as a simple response
                    fallback = (
                        "Agent is not currently running. "
                        "Please start the agent with `comobot agent` first."
                    )
                    await db.execute(
                        "INSERT INTO messages (session_id, role, content) "
                        "VALUES (?, 'assistant', ?)",
                        (session["id"], fallback),
                    )
                    await websocket.send_json(
                        {
                            "type": "response",
                            "session_key": session_key,
                            "content": fallback,
                            "role": "assistant",
                        }
                    )

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.unregister_chat(websocket)
    except Exception:
        manager.unregister_chat(websocket)


def get_ws_manager() -> ConnectionManager:
    """Get the global WS connection manager."""
    return manager
