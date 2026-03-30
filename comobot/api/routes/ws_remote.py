"""Dedicated WebSocket endpoint for Comobot Remote mobile devices."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from dataclasses import field as dc_field

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from comobot.api.remote.demand_capture import (
    DemandCaptureResult,
    DemandCaptureSession,
    build_context_lines,
)
from comobot.api.remote.ws_manager import (
    HEARTBEAT_INTERVAL,
    HEARTBEAT_TIMEOUT,
    RemoteConnectionManager,
)
from comobot.security.nacl_crypto import compute_shared_key

router = APIRouter()

# Global remote connection manager instance
remote_manager = RemoteConnectionManager()


def get_remote_manager() -> RemoteConnectionManager:
    """Get the global RemoteConnectionManager instance."""
    return remote_manager


@router.websocket("/ws/remote")
async def ws_remote(websocket: WebSocket):
    """Dedicated mobile WebSocket endpoint with encrypted transport.

    Auth: JWT token in query param (?token=...)
    After auth, all messages are NaCl-encrypted via the shared key from pairing.

    Commands:
      - subscribe(session_key)    — subscribe to real-time session updates
      - unsubscribe(session_key)  — unsubscribe from session
      - send_message(session_key, content) — send message to a session
      - agent_command(agent_id, command)   — pause/resume agent
      - voice_intent(transcript, context)  — submit voice intent
      - voice_audio(audio, request_id, language) — stream audio for ASR + intent
      - intervene(session_key, action, content) — descend mode intervention
      - sync(last_seq)            — reconnection sync (replay missed messages)
      - ping                      — keepalive
    """
    # --- Auth phase ---
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    app = websocket.app
    auth = app.state.auth
    payload = auth.verify_device_token(token)
    if not payload or payload.get("type") != "device":
        await websocket.close(code=4001, reason="Invalid token")
        return

    device_id = payload["device_id"]

    # --- Look up device and compute shared key ---
    dm = getattr(app.state, "device_manager", None)
    if not dm:
        await websocket.close(code=4003, reason="Service unavailable")
        return

    device = await dm.get_device(device_id)
    if not device or not device["is_active"]:
        await websocket.close(code=4001, reason="Device not found or inactive")
        return

    try:
        shared_key = compute_shared_key(
            our_secret=base64.b64decode(device["server_secret_key"]),
            their_public=base64.b64decode(device["device_public_key"]),
        )
    except Exception as e:
        logger.error("Failed to compute shared key for device {}: {}", device_id, e)
        await websocket.close(code=4002, reason="Encryption error")
        return

    # --- Establish encrypted connection ---
    conn = await remote_manager.connect(device_id, websocket, shared_key)
    await dm.touch_device(device_id)

    # Send welcome message
    await remote_manager.send_encrypted(
        device_id,
        {
            "t": "welcome",
            "device_id": device_id,
            "server_version": "1.0",
            "heartbeat_interval": HEARTBEAT_INTERVAL,
        },
        track=False,
    )

    # --- Run receive loop and heartbeat loop concurrently ---
    receive_task = asyncio.create_task(_receive_loop(app, device_id, conn))
    heartbeat_task = asyncio.create_task(_heartbeat_loop(app, device_id, conn))

    try:
        # Wait for either task to finish (receive loop exits on disconnect)
        done, pending = await asyncio.wait(
            [receive_task, heartbeat_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        # Propagate any exception from the completed task
        for task in done:
            if task.exception() and not isinstance(task.exception(), asyncio.CancelledError):
                raise task.exception()
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as e:
        logger.error("WS error for device {}: {}", device_id, e)
    finally:
        receive_task.cancel()
        heartbeat_task.cancel()
        # Only remove if this is still the active connection (not replaced by a reconnect)
        remote_manager.disconnect(device_id, conn)


async def _receive_loop(app, device_id: str, conn) -> None:
    """Continuously receive and dispatch decrypted commands from a device."""
    while True:
        msg = await remote_manager.receive_decrypted(conn)
        if msg is None:
            break
        await _handle_command(app, device_id, msg)


async def _heartbeat_loop(app, device_id: str, conn) -> None:
    """Server-side heartbeat: send ping if idle, disconnect if unresponsive."""
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)

        # Stop if this connection has been replaced by a newer one
        current = remote_manager.connections.get(device_id)
        if current is not conn:
            break

        idle = remote_manager.seconds_since_last_message(device_id)

        if idle >= HEARTBEAT_TIMEOUT:
            # Device hasn't responded for too long — force disconnect
            logger.warning(
                "Device {} heartbeat timeout ({:.0f}s idle), disconnecting",
                device_id,
                idle,
            )
            try:
                await conn.ws.close(code=4008, reason="Heartbeat timeout")
            except Exception:
                pass
            break

        if idle >= HEARTBEAT_INTERVAL:
            # Send server-initiated ping (plaintext, no outbox tracking)
            await remote_manager.send_encrypted(
                device_id,
                {"t": "ping", "ts": int(asyncio.get_event_loop().time() * 1000)},
                track=False,
            )

        # Periodic outbox cleanup
        remote_manager.cleanup_outbox(device_id)

        # Expire stale pending_confirmation intents for this device
        intent_engine = getattr(app.state, "intent_engine", None)
        if intent_engine:
            await intent_engine.expire_device_intents(device_id, remote_manager)


async def _execute_confirmed_intent(app, device_id: str, intent_row: dict) -> None:
    """Execute a user-confirmed intent by injecting into the agent message bus."""
    intent_id = intent_row["id"]
    intent_engine = getattr(app.state, "intent_engine", None)
    if not intent_engine:
        return

    demand_summary = intent_row.get("demand_summary") or intent_row["transcript"]

    try:
        await intent_engine._update_status(intent_id, "processing")
        await remote_manager.send_encrypted(
            device_id,
            {"t": "intent_update", "intent_id": intent_id, "status": "processing"},
        )

        bus = getattr(app.state, "bus", None)
        if not bus:
            raise RuntimeError("MessageBus not available")

        from comobot.bus.events import InboundMessage

        session_key = f"voice:{device_id[:12]}"
        await bus.publish_inbound(
            InboundMessage(
                channel="voice",
                sender_id=device_id,
                chat_id=device_id[:12],
                content=demand_summary,
                session_key_override=session_key,
                metadata={"intent_id": intent_id, "device_id": device_id},
            )
        )

        await intent_engine._update_status(intent_id, "processing", session_key=session_key)

    except Exception as e:
        logger.error("Execute confirmed intent {} failed: {}", intent_id, e)
        if intent_engine:
            await intent_engine._update_status(intent_id, "failed", error=str(e))
        await remote_manager.send_encrypted(
            device_id,
            {"t": "intent_update", "intent_id": intent_id, "status": "failed", "error": str(e)},
        )


async def _handle_command(app, device_id: str, msg: dict) -> None:
    """Route a decrypted command from a mobile device."""
    cmd = msg.get("cmd")
    if not cmd:
        return

    # Update heartbeat timestamp (already done in receive_decrypted, but explicit for clarity)
    remote_manager.touch(device_id)

    if cmd == "ping":
        await remote_manager.send_encrypted(device_id, {"t": "pong"}, track=False)

    elif cmd == "pong":
        # Client responding to our server-initiated ping — just update timestamp (already done)
        pass

    elif cmd == "subscribe":
        session_key = msg.get("session_key")
        if session_key:
            remote_manager.subscribe(device_id, session_key)
            # Fetch recent messages for the session
            db = app.state.db
            session = await db.fetchone(
                "SELECT id FROM sessions WHERE session_key = ?", (session_key,)
            )
            if session:
                messages = await db.fetchall(
                    "SELECT id, role, content, tool_calls, created_at "
                    "FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT 50",
                    (session["id"],),
                )
                messages.reverse()
                await remote_manager.send_encrypted(
                    device_id,
                    {
                        "t": "subscribed",
                        "session_key": session_key,
                        "messages": messages,
                    },
                )
            else:
                await remote_manager.send_encrypted(
                    device_id,
                    {
                        "t": "error",
                        "detail": f"Session not found: {session_key}",
                    },
                    track=False,
                )

    elif cmd == "unsubscribe":
        session_key = msg.get("session_key")
        if session_key:
            remote_manager.unsubscribe(device_id, session_key)
            await remote_manager.send_encrypted(
                device_id,
                {
                    "t": "unsubscribed",
                    "session_key": session_key,
                },
                track=False,
            )

    elif cmd == "send_message":
        session_key = msg.get("session_key")
        content = msg.get("content")
        if session_key and content:
            bus = getattr(app.state, "bus", None)
            if bus:
                from comobot.bus.events import InboundMessage

                chat_id = session_key.split(":", 1)[-1] if ":" in session_key else session_key
                await bus.publish_inbound(
                    InboundMessage(
                        channel="mobile",
                        sender_id=device_id,
                        chat_id=chat_id,
                        content=content,
                        session_key_override=session_key,
                    )
                )
                await remote_manager.send_encrypted(
                    device_id,
                    {"t": "message_sent", "session_key": session_key},
                )
            else:
                await remote_manager.send_encrypted(
                    device_id,
                    {"t": "error", "detail": "Message bus not available"},
                    track=False,
                )

    elif cmd == "voice_intent":
        intent_engine = getattr(app.state, "intent_engine", None)
        if not intent_engine:
            await remote_manager.send_encrypted(
                device_id,
                {"t": "error", "detail": "Intent engine not available"},
                track=False,
            )
            return

        action = msg.get("action")  # confirm / cancel / None (new submission)

        if action == "confirm":
            intent_id = msg.get("intent_id")
            if not intent_id:
                await remote_manager.send_encrypted(
                    device_id,
                    {"t": "error", "detail": "Missing intent_id for confirm"},
                    track=False,
                )
                return
            row = await intent_engine.confirm_intent(intent_id)
            if not row:
                await remote_manager.send_encrypted(
                    device_id,
                    {"t": "error", "detail": f"Intent {intent_id} not pending confirmation"},
                    track=False,
                )
                return
            await remote_manager.send_encrypted(
                device_id,
                {"t": "intent_update", "intent_id": intent_id, "status": "confirmed"},
            )
            # Launch agent execution asynchronously
            asyncio.create_task(_execute_confirmed_intent(app, device_id, row))

        elif action == "cancel":
            intent_id = msg.get("intent_id")
            if intent_id:
                cancelled = await intent_engine.cancel_pending_intent(intent_id)
                await remote_manager.send_encrypted(
                    device_id,
                    {
                        "t": "intent_update",
                        "intent_id": intent_id,
                        "status": "cancelled" if cancelled else "error",
                    },
                )

        else:
            # New voice intent submission
            transcript = msg.get("transcript")
            context = msg.get("context")
            if transcript:
                result = await intent_engine.submit_intent(device_id, transcript, context)
                await remote_manager.send_encrypted(device_id, {"t": "intent_submitted", **result})
                # Kick off multi-stage processing asynchronously
                agent_loop = getattr(app.state, "agent", None)
                asyncio.create_task(
                    intent_engine.process_intent(
                        result["intent_id"],
                        agent_loop=agent_loop,
                        remote_manager=remote_manager,
                        device_id=device_id,
                    )
                )

    elif cmd == "voice_audio":
        audio_b64 = msg.get("audio")
        request_id = msg.get("request_id", "")
        language = msg.get("language")
        stream_action = msg.get("stream_action")  # "start" | "chunk" | "end" | None

        if stream_action:
            # --- Streaming mode ---
            await _handle_voice_audio_stream(
                app, device_id, request_id, stream_action, audio_b64, language
            )
        else:
            # --- Legacy batch mode (entire audio in one message) ---
            await _handle_voice_audio_batch(app, device_id, request_id, audio_b64, language)

    elif cmd == "agent_command":
        agent_id = msg.get("agent_id")
        command = msg.get("command")  # "pause" | "resume"
        if agent_id and command:
            # Delegate to agent management (to be expanded)
            await remote_manager.send_encrypted(
                device_id,
                {
                    "t": "agent_command_ack",
                    "agent_id": agent_id,
                    "command": command,
                    "status": "ok",
                },
            )

    elif cmd == "intervene":
        session_key = msg.get("session_key")
        action = msg.get("action")  # "approve" | "edit" | "reject"
        content = msg.get("content")
        if session_key and action:
            # Look for intervention callback on the agent loop
            agent = getattr(app.state, "agent", None)
            if agent and hasattr(agent, "register_intervention_response"):
                agent.register_intervention_response(session_key, action, content or "")
                await remote_manager.send_encrypted(
                    device_id,
                    {
                        "t": "intervene_ack",
                        "session_key": session_key,
                        "action": action,
                    },
                )

    elif cmd == "sync":
        last_seq = msg.get("last_seq", 0)
        missed = remote_manager.get_missed_messages(device_id, last_seq)
        logger.info(
            "Device {} sync from seq {}: {} missed messages",
            device_id,
            last_seq,
            len(missed),
        )
        # Send sync_ack with count, then replay missed messages
        await remote_manager.send_encrypted(
            device_id,
            {
                "t": "sync_ack",
                "last_seq": last_seq,
                "missed_count": len(missed),
                "status": "ok",
            },
            track=False,
        )
        # Replay missed envelopes directly (already encrypted)
        for envelope in missed:
            conn = remote_manager.connections.get(device_id)
            if not conn:
                break
            try:
                await conn.ws.send_json(envelope)
            except Exception:
                break

    else:
        await remote_manager.send_encrypted(
            device_id,
            {
                "t": "error",
                "detail": f"Unknown command: {cmd}",
            },
            track=False,
        )


# ---------------------------------------------------------------------------
# Live streaming ASR sessions: keyed by (device_id, request_id)
# ---------------------------------------------------------------------------


@dataclass
class _LiveStream:
    """Tracks a live streaming ASR session + fallback buffer."""

    request_id: str
    device_id: str
    language: str | None = None
    session: object | None = None  # ASRStreamSession when provider supports streaming
    demand_capture: DemandCaptureSession | None = None
    # Fallback buffer for providers that don't support streaming
    chunks: list[bytes] = dc_field(default_factory=list)
    total_bytes: int = 0


_audio_streams: dict[str, _LiveStream] = {}


def _stream_key(device_id: str, request_id: str) -> str:
    return f"{device_id}:{request_id}"


async def _handle_voice_audio_stream(
    app,
    device_id: str,
    request_id: str,
    action: str,
    audio_b64: str | None,
    language: str | None,
) -> None:
    """Handle streaming voice_audio commands (start / chunk / end).

    If the ASR provider supports true streaming (e.g. Ali NLS), we open a live
    session and feed chunks in real-time → intermediate results are pushed back
    immediately.  Otherwise we fall back to accumulate-then-transcribe.
    """
    key = _stream_key(device_id, request_id)

    if action == "start":
        stream = _LiveStream(request_id=request_id, device_id=device_id, language=language)

        # --- Set up real-time demand capture session ---
        agent_loop = getattr(app.state, "agent", None)
        provider = getattr(agent_loop, "provider", None) if agent_loop else None
        if provider:
            db = getattr(app.state, "db", None)
            context_lines = ""
            if db:
                try:
                    context_lines = await build_context_lines(db, device_id)
                except Exception:
                    pass

            async def _on_demand(result: DemandCaptureResult) -> None:
                """Push demand_detected event to frontend in real-time."""
                try:
                    await remote_manager.send_encrypted(
                        device_id,
                        {
                            "t": "demand_detected",
                            "request_id": request_id,
                            "demand_summary": result.demand_summary,
                            "confidence": result.confidence,
                            "intent": result.intent,
                        },
                    )
                except Exception as exc:
                    logger.error(
                        "[DemandCapture] send demand_detected FAILED: {}", exc
                    )

            stream.demand_capture = DemandCaptureSession(
                device_id=device_id,
                _provider=provider,
                _on_demand=_on_demand,
                _context_lines=context_lines,
            )

        # --- Try to open a live streaming ASR session ---
        asr_service = getattr(app.state, "asr_service", None)
        if asr_service and getattr(asr_service, "supports_streaming", False):
            try:
                _loop = asyncio.get_running_loop()

                def _on_intermediate(text: str, sentence_idx: int, is_final: bool = False) -> None:
                    tag = "FINAL" if is_final else "partial"
                    logger.info(
                        "[ASR-stream] _on_intermediate({}) device={} text='{}'",
                        tag,
                        device_id[:12],
                        text[:80],
                    )

                    async def _send() -> None:
                        try:
                            await remote_manager.send_encrypted(
                                device_id,
                                {
                                    "t": "asr_intermediate",
                                    "request_id": request_id,
                                    "text": text,
                                    "sentence_idx": sentence_idx,
                                    "is_final": is_final,
                                },
                                track=False,
                            )
                        except Exception as exc:
                            logger.error(
                                "[ASR-stream] send_encrypted FAILED for device={}: {}",
                                device_id[:12],
                                exc,
                            )

                        # Feed demand capture session
                        s = _audio_streams.get(key)
                        if s and s.demand_capture:
                            s.demand_capture.on_sentence(text, is_final)

                    _loop.call_soon_threadsafe(asyncio.ensure_future, _send())

                session = await asr_service.start_stream(
                    language=language, on_intermediate=_on_intermediate
                )
                stream.session = session
                logger.info(
                    "[ASR-stream] device={} request={} live ASR session started",
                    device_id[:12],
                    request_id,
                )
            except Exception as e:
                logger.warning(
                    "[ASR-stream] device={} failed to start live session ({}), "
                    "falling back to accumulate mode",
                    device_id[:12],
                    e,
                )
        else:
            logger.info(
                "[ASR-stream] device={} request={} stream started (accumulate mode)",
                device_id[:12],
                request_id,
            )

        _audio_streams[key] = stream

    elif action == "chunk":
        stream = _audio_streams.get(key)
        if not stream:
            logger.warning(
                "[ASR-stream] device={} request={} chunk for unknown stream",
                device_id[:12],
                request_id,
            )
            return

        if audio_b64:
            pcm = base64.b64decode(audio_b64)
            if pcm[:4] == b"RIFF" and len(pcm) > 44:
                pcm = pcm[44:]

            stream.total_bytes += len(pcm)

            # Always keep a copy for fallback batch transcription
            stream.chunks.append(pcm)

            if stream.session and getattr(stream.session, "is_alive", False):
                # Feed directly into live ASR session → intermediate results via callback
                await stream.session.feed(pcm)
                logger.debug(
                    "[ASR-stream] device={} request={} fed {}B (total {:.1f}s)",
                    device_id[:12],
                    request_id,
                    len(pcm),
                    stream.total_bytes / (16000 * 2),
                )
            elif stream.session and not getattr(stream.session, "is_alive", True):
                # Live session died — just accumulate (already appended above)
                logger.debug(
                    "[ASR-stream] device={} request={} session dead, buffering +{}B",
                    device_id[:12],
                    request_id,
                    len(pcm),
                )
            else:
                logger.debug(
                    "[ASR-stream] device={} request={} buffered +{}B (total {:.1f}s)",
                    device_id[:12],
                    request_id,
                    len(pcm),
                    stream.total_bytes / (16000 * 2),
                )

    elif action == "end":
        stream = _audio_streams.pop(key, None)
        if not stream:
            logger.warning(
                "[ASR-stream] device={} request={} end for unknown stream",
                device_id[:12],
                request_id,
            )
            return

        # Feed final chunk if present
        if audio_b64:
            pcm = base64.b64decode(audio_b64)
            if pcm[:4] == b"RIFF" and len(pcm) > 44:
                pcm = pcm[44:]
            stream.total_bytes += len(pcm)
            stream.chunks.append(pcm)
            if stream.session and getattr(stream.session, "is_alive", False):
                await stream.session.feed(pcm)

        duration = stream.total_bytes / (16000 * 2)
        logger.info(
            "[ASR-stream] device={} request={} stream ended — {:.1f}s ({} bytes)",
            device_id[:12],
            request_id,
            duration,
            stream.total_bytes,
        )

        if duration < 0.3:
            logger.info(
                "[ASR-stream] device={} audio too short ({:.1f}s), skipping",
                device_id[:12],
                duration,
            )
            if stream.session:
                await stream.session.cancel()
            await remote_manager.send_encrypted(
                device_id,
                {
                    "t": "asr_result",
                    "request_id": request_id,
                    "status": "ok",
                    "text": "",
                    "language": language or "unknown",
                    "duration": duration,
                },
            )
            return

        # Try live session first; fall back to batch if it died or returned empty
        use_batch = True
        if stream.session and getattr(stream.session, "is_alive", False):
            try:
                await _finish_live_stream(app, device_id, request_id, stream)
                use_batch = False
            except Exception as e:
                logger.warning(
                    "[ASR-stream] device={} live session finish failed ({}), falling back to batch",
                    device_id[:12],
                    e,
                )
        elif stream.session:
            logger.warning(
                "[ASR-stream] device={} live session was dead, using batch fallback",
                device_id[:12],
            )
            # Cancel the dead session cleanly
            try:
                await stream.session.cancel()
            except Exception:
                pass

        if use_batch:
            # Fallback: transcribe accumulated audio
            all_pcm = b"".join(stream.chunks)
            await _transcribe_and_submit(app, device_id, request_id, all_pcm, stream.language)


async def _finish_live_stream(app, device_id: str, request_id: str, stream: _LiveStream) -> None:
    """Finish a live streaming ASR session and send the final result + intent."""
    try:
        result = await stream.session.finish()

        logger.info(
            "[ASR-stream] device={} request={} live result: '{}' lang={} dur={:.1f}s",
            device_id[:12],
            request_id,
            result.text[:80] if result.text else "(empty)",
            result.language,
            result.duration,
        )

        await remote_manager.send_encrypted(
            device_id,
            {
                "t": "asr_result",
                "request_id": request_id,
                "status": "ok",
                "text": result.text,
                "language": result.language,
                "duration": result.duration,
            },
        )

        if not result.text:
            return

        # --- Finalize real-time demand capture ---
        demand_result = None
        if stream.demand_capture:
            try:
                demand_result = await stream.demand_capture.finalize()
            except Exception as e:
                logger.warning("[ASR-stream] demand capture finalize failed: {}", e)

        # If demand capture already detected a demand, use it to fast-track intent
        intent_engine = getattr(app.state, "intent_engine", None)
        if intent_engine:
            intent = await intent_engine.submit_intent(
                device_id, result.text, {"source": "voice_audio"}
            )
            intent_id = intent.get("intent_id", "")
            logger.info(
                "[ASR-stream] device={} intent submitted: {}",
                device_id[:12],
                intent_id,
            )
            await remote_manager.send_encrypted(device_id, {"t": "intent_submitted", **intent})

            if demand_result and demand_result.has_demand and demand_result.confidence >= 0.6:
                # Fast-track: demand already captured during streaming → skip LLM re-analysis
                logger.info(
                    "[ASR-stream] device={} fast-track intent from real-time demand: '{}'",
                    device_id[:12],
                    demand_result.demand_summary[:60],
                )
                asyncio.create_task(
                    intent_engine.process_intent_with_demand(
                        intent_id,
                        demand_summary=demand_result.demand_summary,
                        intent_type=demand_result.intent,
                        confidence=demand_result.confidence,
                        remote_manager=remote_manager,
                        device_id=device_id,
                    )
                )
            else:
                # Normal path: full LLM analysis
                agent_loop = getattr(app.state, "agent", None)
                asyncio.create_task(
                    intent_engine.process_intent(
                        intent_id,
                        agent_loop=agent_loop,
                        remote_manager=remote_manager,
                        device_id=device_id,
                    )
                )

    except Exception as e:
        logger.error(
            "[ASR-stream] device={} request={} finish FAILED: {}",
            device_id[:12],
            request_id,
            e,
        )
        await remote_manager.send_encrypted(
            device_id,
            {
                "t": "asr_result",
                "request_id": request_id,
                "status": "error",
                "error": str(e),
            },
            track=False,
        )


async def _handle_voice_audio_batch(
    app,
    device_id: str,
    request_id: str,
    audio_b64: str | None,
    language: str | None,
) -> None:
    """Handle legacy batch voice_audio (entire audio in one message)."""
    if not audio_b64:
        logger.warning("[ASR] device={} empty audio in voice_audio cmd", device_id[:12])
        await remote_manager.send_encrypted(
            device_id,
            {"t": "asr_result", "request_id": request_id, "status": "error", "error": "No audio"},
            track=False,
        )
        return

    audio_bytes = base64.b64decode(audio_b64)
    # Strip WAV header if present
    if audio_bytes[:4] == b"RIFF" and len(audio_bytes) > 44:
        audio_bytes = audio_bytes[44:]

    logger.info(
        "[ASR] device={} request={} batch voice_audio ({:.1f}s, lang={})",
        device_id[:12],
        request_id,
        len(audio_bytes) / (16000 * 2),
        language or "auto",
    )

    await _transcribe_and_submit(app, device_id, request_id, audio_bytes, language)


async def _transcribe_and_submit(
    app,
    device_id: str,
    request_id: str,
    pcm_bytes: bytes,
    language: str | None,
) -> None:
    """Common path: transcribe PCM audio, send result, auto-submit intent."""
    import time as _time

    asr_service = getattr(app.state, "asr_service", None)
    if not asr_service:
        logger.error("[ASR] device={} ASR service not available", device_id[:12])
        await remote_manager.send_encrypted(
            device_id,
            {
                "t": "asr_result",
                "request_id": request_id,
                "status": "error",
                "error": "ASR not available",
            },
            track=False,
        )
        return

    try:
        t0 = _time.monotonic()
        _loop = asyncio.get_running_loop()

        def _on_intermediate(text: str, sentence_idx: int, is_final: bool = False) -> None:
            tag = "FINAL" if is_final else "partial"
            logger.info(
                "[ASR-batch] _on_intermediate({}) device={} text='{}'",
                tag,
                device_id[:12],
                text[:80],
            )

            async def _send() -> None:
                try:
                    await remote_manager.send_encrypted(
                        device_id,
                        {
                            "t": "asr_intermediate",
                            "request_id": request_id,
                            "text": text,
                            "sentence_idx": sentence_idx,
                            "is_final": is_final,
                        },
                        track=False,
                    )
                except Exception as exc:
                    logger.error(
                        "[ASR-batch] send_encrypted FAILED for device={}: {}",
                        device_id[:12],
                        exc,
                    )

            _loop.call_soon_threadsafe(asyncio.ensure_future, _send())

        result = await asr_service.transcribe(
            pcm_bytes, language=language, on_intermediate=_on_intermediate
        )
        elapsed = _time.monotonic() - t0

        logger.info(
            "[ASR] device={} request={} OK in {:.2f}s → '{}' lang={} dur={:.1f}s",
            device_id[:12],
            request_id,
            elapsed,
            result.text[:80] if result.text else "(empty)",
            result.language,
            result.duration,
        )

        await remote_manager.send_encrypted(
            device_id,
            {
                "t": "asr_result",
                "request_id": request_id,
                "status": "ok",
                "text": result.text,
                "language": result.language,
                "duration": result.duration,
            },
        )

        # Auto-submit non-empty transcript → multi-stage pipeline
        if result.text:
            intent_engine = getattr(app.state, "intent_engine", None)
            if intent_engine:
                intent = await intent_engine.submit_intent(
                    device_id, result.text, {"source": "voice_audio"}
                )
                logger.info(
                    "[ASR] device={} intent submitted: {}",
                    device_id[:12],
                    intent.get("intent_id", "?"),
                )
                await remote_manager.send_encrypted(device_id, {"t": "intent_submitted", **intent})
                agent_loop = getattr(app.state, "agent", None)
                asyncio.create_task(
                    intent_engine.process_intent(
                        intent["intent_id"],
                        agent_loop=agent_loop,
                        remote_manager=remote_manager,
                        device_id=device_id,
                    )
                )

    except Exception as e:
        logger.error("[ASR] device={} request={} FAILED: {}", device_id[:12], request_id, e)
        logger.exception("[ASR] traceback:")
        await remote_manager.send_encrypted(
            device_id,
            {"t": "asr_result", "request_id": request_id, "status": "error", "error": str(e)},
            track=False,
        )
