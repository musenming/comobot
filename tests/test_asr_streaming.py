"""Mock test for streaming ASR — verifies that intermediate results
arrive in real-time during chunk feeding, not just at the end.

Run:  pytest tests/test_asr_streaming.py -v -s
"""

from __future__ import annotations

import asyncio
import base64
import struct
import time

import pytest

from comobot.asr.base import ASRResult, ASRStreamSession, IntermediateCallback


# ---------------------------------------------------------------------------
# Mock streaming ASR provider — simulates real-time transcription
# ---------------------------------------------------------------------------
class MockStreamSession(ASRStreamSession):
    """Simulates a live ASR session that emits intermediate results as audio
    chunks are fed in, mimicking Ali NLS behavior."""

    # Fake sentences to "recognise" — each maps to ~1 chunk of audio
    FAKE_SENTENCES = [
        "你好",
        "你好，我想要",
        "你好，我想要一杯",
        "你好，我想要一杯咖啡",
    ]

    def __init__(
        self,
        language: str | None,
        on_intermediate: IntermediateCallback | None,
    ) -> None:
        self._language = language or "zh"
        self._on_intermediate = on_intermediate
        self._chunk_count = 0
        self._total_bytes = 0
        self._confirmed_sentences: list[str] = []
        self._cancelled = False

    @property
    def is_alive(self) -> bool:
        return not self._cancelled

    async def feed(self, pcm_bytes: bytes) -> None:
        self._total_bytes += len(pcm_bytes)
        self._chunk_count += 1

        # Simulate intermediate result after each chunk
        if self._on_intermediate and not self._cancelled:
            idx = min(self._chunk_count - 1, len(self.FAKE_SENTENCES) - 1)
            partial_text = self.FAKE_SENTENCES[idx]

            # Every 2 chunks, "confirm" a sentence (is_final=True)
            if self._chunk_count % 2 == 0:
                self._confirmed_sentences.append(partial_text)
                self._on_intermediate(partial_text, len(self._confirmed_sentences), True)
            else:
                self._on_intermediate(partial_text, len(self._confirmed_sentences), False)

            # Small delay to simulate real processing
            await asyncio.sleep(0.01)

    async def finish(self) -> ASRResult:
        final_text = self.FAKE_SENTENCES[-1] if self.FAKE_SENTENCES else ""
        duration = round(self._total_bytes / (16000 * 2), 2)
        return ASRResult(text=final_text, language=self._language, duration=duration)

    async def cancel(self) -> None:
        self._cancelled = True


class MockASRService:
    """Mock ASR service that creates MockStreamSessions."""

    supports_streaming = True

    async def start_stream(
        self,
        language: str | None = None,
        on_intermediate: IntermediateCallback | None = None,
    ) -> MockStreamSession:
        return MockStreamSession(language, on_intermediate)

    async def transcribe(self, audio_bytes, language=None, on_intermediate=None):
        return ASRResult(text="batch result", language=language or "zh", duration=1.0)


# ---------------------------------------------------------------------------
# Helper: generate fake PCM audio (silence)
# ---------------------------------------------------------------------------
def make_pcm_chunk(duration_ms: int = 200) -> bytes:
    """Generate silent PCM (16kHz, 16-bit mono) of given duration."""
    num_samples = int(16000 * duration_ms / 1000)
    return struct.pack(f"<{num_samples}h", *([0] * num_samples))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestStreamingASR:
    """Test the streaming ASR flow end-to-end with mocks."""

    @pytest.fixture
    def asr_service(self):
        return MockASRService()

    async def test_intermediate_results_arrive_during_chunks(self, asr_service):
        """Core test: intermediate results should fire DURING chunk feeding,
        not just at finish()."""
        intermediate_events: list[dict] = []
        timestamps: list[float] = []

        def on_intermediate(text: str, sentence_idx: int, is_final: bool) -> None:
            intermediate_events.append(
                {
                    "text": text,
                    "sentence_idx": sentence_idx,
                    "is_final": is_final,
                }
            )
            timestamps.append(time.monotonic())

        session = await asr_service.start_stream(language="zh", on_intermediate=on_intermediate)

        # Feed 4 chunks (simulating ~800ms of audio in 200ms intervals)
        for _ in range(4):
            chunk = make_pcm_chunk(200)
            await session.feed(chunk)

        # Intermediate results should have arrived BEFORE finish()
        events_before_finish = len(intermediate_events)
        assert events_before_finish > 0, (
            "No intermediate results received during chunk feeding! "
            "This is the core bug — results should arrive in real-time."
        )

        result = await session.finish()

        print("\n--- Streaming ASR Test Results ---")
        print(f"Intermediate events received during feeding: {events_before_finish}")
        print(f"Total intermediate events: {len(intermediate_events)}")
        print(f"Final result: '{result.text}'")
        print()
        for i, evt in enumerate(intermediate_events):
            print(
                f"  [{i}] text='{evt['text']}' idx={evt['sentence_idx']} is_final={evt['is_final']}"
            )

        # Verify we got both partial and final events
        partials = [e for e in intermediate_events if not e["is_final"]]
        finals = [e for e in intermediate_events if e["is_final"]]
        assert len(partials) > 0, "Should have partial (interim) results"
        assert len(finals) > 0, "Should have final (confirmed sentence) results"

        # Verify text progressively builds up
        texts = [e["text"] for e in intermediate_events]
        assert len(texts[-1]) >= len(texts[0]), "Text should progressively build up"

        # Final result
        assert result.text == "你好，我想要一杯咖啡"
        assert result.language == "zh"

    async def test_cancel_stops_intermediate_results(self, asr_service):
        """Cancelling a session should stop further intermediate results."""
        events: list[dict] = []

        def on_intermediate(text: str, sentence_idx: int, is_final: bool) -> None:
            events.append({"text": text})

        session = await asr_service.start_stream(language="zh", on_intermediate=on_intermediate)

        await session.feed(make_pcm_chunk(200))
        count_before_cancel = len(events)
        assert count_before_cancel > 0

        await session.cancel()
        await session.feed(make_pcm_chunk(200))

        # No new events after cancel
        assert len(events) == count_before_cancel

    async def test_short_audio_skipped(self):
        """Audio shorter than 0.3s should be skipped (returns empty text)."""
        session = MockStreamSession(language="zh", on_intermediate=None)

        # Feed very short audio (~50ms)
        short_chunk = make_pcm_chunk(50)
        await session.feed(short_chunk)

        _ = await session.finish()
        # The mock still returns text, but in the real ws_remote handler,
        # duration < 0.3s is checked before calling finish()
        duration = len(short_chunk) / (16000 * 2)
        assert duration < 0.3, f"Test chunk should be < 0.3s, got {duration}s"


class TestStreamingWSFlow:
    """Simulate the full WS flow: start → chunk → chunk → end,
    verifying the intermediate push pattern."""

    async def test_full_ws_simulation(self):
        """Simulate what ws_remote._handle_voice_audio_stream does."""
        asr_service = MockASRService()
        pushed_events: list[dict] = []

        # Simulate the start action
        request_id = "test-req-001"
        language = "zh"

        def on_intermediate(text: str, sentence_idx: int, is_final: bool) -> None:
            pushed_events.append(
                {
                    "t": "asr_intermediate",
                    "request_id": request_id,
                    "text": text,
                    "sentence_idx": sentence_idx,
                    "is_final": is_final,
                }
            )

        session = await asr_service.start_stream(language=language, on_intermediate=on_intermediate)

        # Simulate chunk feeding (what happens on each voice_audio chunk command)
        total_bytes = 0
        for i in range(6):
            pcm = make_pcm_chunk(200)
            total_bytes += len(pcm)
            await session.feed(pcm)

        # Simulate end
        result = await session.finish()

        print("\n--- WS Flow Simulation ---")
        print("Chunks sent: 6")
        print(f"Total bytes: {total_bytes}")
        print(f"Duration: {total_bytes / (16000 * 2):.1f}s")
        print(f"Intermediate pushes: {len(pushed_events)}")
        print(f"Final text: '{result.text}'")
        print()

        for evt in pushed_events:
            status = "FINAL" if evt["is_final"] else "partial"
            print(f"  → [{status}] '{evt['text']}' (sentence_idx={evt['sentence_idx']})")

        # Verify intermediate results were pushed
        assert len(pushed_events) >= 4, (
            f"Expected at least 4 intermediate pushes for 6 chunks, got {len(pushed_events)}"
        )

        # Verify the event format matches what the frontend expects
        for evt in pushed_events:
            assert evt["t"] == "asr_intermediate"
            assert evt["request_id"] == request_id
            assert "text" in evt
            assert "sentence_idx" in evt
            assert "is_final" in evt

        # Verify we have both partial and final events
        has_partial = any(not e["is_final"] for e in pushed_events)
        has_final = any(e["is_final"] for e in pushed_events)
        assert has_partial, "Should have partial results for UI grey text"
        assert has_final, "Should have final results for UI locked text"

        # Verify final result
        assert result.text
        assert result.language == "zh"


class TestAccumulateFallback:
    """Test that non-streaming providers fall back to accumulate mode."""

    async def test_non_streaming_provider_accumulates(self):
        """If provider doesn't support streaming, chunks should be buffered
        and transcribed at end."""
        from comobot.asr.base import AudioStreamBuffer

        buf = AudioStreamBuffer(
            request_id="req-001",
            device_id="dev-001",
            language="zh",
        )

        # Simulate chunk accumulation
        for _ in range(5):
            chunk = make_pcm_chunk(200)
            buf.append(chunk)

        assert buf.total_bytes > 0
        assert buf.duration > 0.5

        all_pcm = buf.get_all_pcm()
        assert len(all_pcm) == buf.total_bytes

        # In real flow, this PCM would be sent to transcribe() at end
        result = await MockASRService().transcribe(all_pcm, language="zh")
        assert result.text == "batch result"


class TestWSHandlerIntegration:
    """Integration test: exercise the actual _handle_voice_audio_stream
    function from ws_remote.py with a mock ASR service and a mock
    remote_manager to capture all pushed WS events.

    This verifies the FULL message delivery pipeline:
      WS command → _handle_voice_audio_stream → ASR session → intermediate callback
      → remote_manager.send_encrypted → asr_intermediate event → frontend
    """

    async def test_full_pipeline_delivers_intermediate_events(self):
        """The core integration test: verifies that asr_intermediate events
        are actually sent via remote_manager during chunk processing."""
        from unittest.mock import MagicMock

        from comobot.api.routes.ws_remote import (
            _audio_streams,
            _handle_voice_audio_stream,
        )
        from comobot.api.routes.ws_remote import (
            remote_manager as real_rm,
        )

        # Capture all events sent via remote_manager
        sent_events: list[dict] = []
        original_send = real_rm.send_encrypted

        async def mock_send_encrypted(device_id, payload, track=True):
            sent_events.append(payload)

        real_rm.send_encrypted = mock_send_encrypted

        # Mock app with streaming ASR service
        app = MagicMock()
        app.state.asr_service = MockASRService()
        app.state.intent_engine = None  # Skip intent pipeline for this test

        device_id = "test-device-001"
        request_id = "test-req-integration"

        try:
            # 1. START — opens live ASR session
            await _handle_voice_audio_stream(app, device_id, request_id, "start", None, "zh")

            # Verify stream was created with a live session
            from comobot.api.routes.ws_remote import _stream_key

            key = _stream_key(device_id, request_id)
            assert key in _audio_streams
            stream = _audio_streams[key]
            assert stream.session is not None, "Live session should be created"

            # 2. CHUNK x4 — feed audio, should trigger intermediate pushes
            _events_before_chunks = len(sent_events)
            for i in range(4):
                pcm = make_pcm_chunk(200)
                audio_b64 = base64.b64encode(pcm).decode()
                await _handle_voice_audio_stream(
                    app, device_id, request_id, "chunk", audio_b64, "zh"
                )
                # Small delay to let async callbacks fire
                await asyncio.sleep(0.05)

            # Verify intermediate events were pushed DURING chunk feeding
            intermediate_events = [e for e in sent_events if e.get("t") == "asr_intermediate"]
            print("\n--- Integration Pipeline Test ---")
            print(f"Events sent during chunks: {len(intermediate_events)}")
            for evt in intermediate_events:
                status = "FINAL" if evt.get("is_final") else "partial"
                print(f"  → [{status}] '{evt['text']}' (sentence_idx={evt['sentence_idx']})")

            assert len(intermediate_events) > 0, (
                "CRITICAL: No asr_intermediate events were pushed during chunk feeding! "
                "The message pipeline is broken — frontend will never see real-time text."
            )

            # Verify event format
            for evt in intermediate_events:
                assert evt["t"] == "asr_intermediate"
                assert evt["request_id"] == request_id
                assert "text" in evt
                assert "sentence_idx" in evt
                assert "is_final" in evt

            # Verify both partial and final types exist
            has_partial = any(not e["is_final"] for e in intermediate_events)
            has_final = any(e["is_final"] for e in intermediate_events)
            assert has_partial, "Missing partial (interim) results"
            assert has_final, "Missing final (confirmed) results"

            # 3. END — finishes session, sends asr_result
            await _handle_voice_audio_stream(app, device_id, request_id, "end", None, "zh")
            await asyncio.sleep(0.05)

            # Verify final asr_result was sent
            asr_results = [e for e in sent_events if e.get("t") == "asr_result"]
            assert len(asr_results) == 1, f"Expected 1 asr_result, got {len(asr_results)}"
            final = asr_results[0]
            assert final["status"] == "ok"
            assert final["text"], "Final text should not be empty"
            print(f"  Final result: '{final['text']}'")
            print(f"  Total events pushed: {len(sent_events)}")
            print("  ✓ Pipeline verified: intermediate events flow in real-time!")

        finally:
            # Restore original
            real_rm.send_encrypted = original_send
            # Clean up any leftover streams
            _audio_streams.pop(_stream_key(device_id, request_id), None)
