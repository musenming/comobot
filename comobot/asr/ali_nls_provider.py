"""Alibaba Cloud NLS real-time speech transcription provider."""

from __future__ import annotations

import asyncio
import threading
import time
from typing import TYPE_CHECKING

from loguru import logger

from .base import ASRProvider, ASRResult, ASRStreamSession, IntermediateCallback
from .token_manager import TokenManager

if TYPE_CHECKING:
    from comobot.config.schema import ASRProviderConfig

# Default China-Shanghai NLS gateway
_DEFAULT_WS_URL = "wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1"

# ---------------------------------------------------------------------------
# Language → NLS extra payload mapping
# Ali NLS selects the recognition model via the appkey's project config,
# but we can override with "model" in the ex payload for mixed-language etc.
# ---------------------------------------------------------------------------
_NLS_LANGUAGE_EX: dict[str, dict] = {
    "zh-en": {"enable_nlp_model": True, "enable_words": True},
    "en": {"enable_nlp_model": True, "enable_words": True},
}


def _build_nls_ex(language: str | None) -> dict:
    """Build the NLS `ex` dict for sr.start() based on the requested language."""
    ex: dict = {"max_sentence_silence": 1200}
    if language and language in _NLS_LANGUAGE_EX:
        ex.update(_NLS_LANGUAGE_EX[language])
    return ex


class AliNlsStreamSession(ASRStreamSession):
    """A live Ali NLS streaming session that stays open across feed() calls.

    Architecture:
    - Worker thread owns the NLS SDK (blocking WebSocket).
    - ``queue.Queue`` (stdlib, thread-safe) passes PCM from the async world
      into the worker without any cross-thread asyncio coordination.
    - ``_ready`` event gates ``feed()`` until ``sr.start()`` succeeds.
    - ``_closed`` flag lets ``feed()`` detect a dead connection immediately.
    """

    def __init__(
        self,
        provider: AliNlsASRProvider,
        language: str | None,
        on_intermediate: IntermediateCallback | None,
    ) -> None:
        import queue as _queue_mod

        self._provider = provider
        self._language = language
        self._on_intermediate = on_intermediate
        self._loop = asyncio.get_running_loop()

        # Thread-safe stdlib queue (no asyncio cross-thread issues)
        self._audio_queue: _queue_mod.Queue[bytes | None] = _queue_mod.Queue()
        self._results: list[str] = []
        self._sentence_idx = 0

        # Sync primitives (all threading-based, no asyncio Events)
        self._ready = threading.Event()  # set when sr.start() succeeds
        self._done_flag = threading.Event()  # set on completed/error/close
        self._done_async = asyncio.Event()  # mirrors _done_flag for async callers

        self._error: str | None = None
        self._total_bytes = 0
        self._started = False
        self._closed = False  # True once NLS connection drops
        self._cancelled = False
        self._sr = None
        self._worker_thread: threading.Thread | None = None

    async def start(self) -> None:
        """Initialize the NLS session and wait for it to be ready."""
        token = await self._provider._get_token()
        self._worker_thread = threading.Thread(target=self._worker, args=(token,), daemon=True)
        self._worker_thread.start()

        # Wait up to 5s for NLS connection to be established
        ready = await asyncio.get_running_loop().run_in_executor(None, self._ready.wait, 5.0)
        if not ready:
            if self._error:
                raise RuntimeError(f"NLS stream start failed: {self._error}")
            raise RuntimeError("NLS stream start timed out (5s)")

        if self._error:
            raise RuntimeError(f"NLS stream start failed: {self._error}")

        self._started = True
        logger.info("[AliNLS-stream] session ready, accepting audio chunks")

    def _worker(self, token: str) -> None:
        """Background thread: open NLS session, consume audio queue, stream to NLS."""
        import queue as _queue_mod

        try:
            import nls
        except ImportError:
            self._error = (
                "alibabacloud-nls-python-sdk not installed. "
                "Install with: pip install alibabacloud-nls-python-sdk"
            )
            self._ready.set()
            self._signal_done()
            return

        results = self._results
        on_intermediate = self._on_intermediate

        def _build_full_text(current_intermediate: str = "") -> str:
            parts = list(results)
            if current_intermediate:
                parts.append(current_intermediate)
            return "".join(parts)

        def on_sentence_begin(message, *args):
            logger.debug("[AliNLS-stream] sentence_begin: {}", message[:200] if message else "")

        def on_sentence_end(message, *args):
            import json

            try:
                data = json.loads(message)
                text = data.get("payload", {}).get("result", "")
                if text:
                    results.append(text)
                    self._sentence_idx += 1
                    full = _build_full_text()
                    logger.info(
                        "[AliNLS-stream] sentence #{}: '{}' → push final '{}'",
                        self._sentence_idx,
                        text[:80],
                        full[:80],
                    )
                    if on_intermediate:
                        try:
                            on_intermediate(full, self._sentence_idx, True)
                        except Exception as exc:
                            logger.error(
                                "[AliNLS-stream] on_intermediate FINAL callback error: {}", exc
                            )
            except Exception as e:
                logger.warning("[AliNLS-stream] parse sentence_end failed: {}", e)

        def on_result_changed(message, *args):
            import json

            try:
                data = json.loads(message)
                text = data.get("payload", {}).get("result", "")
                if text:
                    full = _build_full_text(text)
                    logger.debug(
                        "[AliNLS-stream] partial: '{}' → push '{}'",
                        text[:60],
                        full[:80],
                    )
                    if on_intermediate:
                        try:
                            on_intermediate(full, self._sentence_idx, False)
                        except Exception as exc:
                            logger.error(
                                "[AliNLS-stream] on_intermediate PARTIAL callback error: {}", exc
                            )
            except Exception as exc:
                logger.warning("[AliNLS-stream] parse result_changed failed: {}", exc)

        def on_completed(message, *args):
            logger.info("[AliNLS-stream] transcription completed")
            self._signal_done()

        def on_error(message, *args):
            self._error = str(message)
            logger.error("[AliNLS-stream] ERROR: {}", message)
            self._closed = True
            self._ready.set()  # unblock start() if still waiting
            self._signal_done()

        def on_close(*args):
            logger.warning("[AliNLS-stream] connection closed (closed={})", self._closed)
            self._closed = True
            self._ready.set()  # unblock start() if still waiting
            self._signal_done()

        url = self._provider._config.api_base or _DEFAULT_WS_URL
        app_key = self._provider._config.app_key

        nls_ex = _build_nls_ex(self._language)
        logger.info(
            "[AliNLS-stream] connecting: url={} appkey={} token={}... lang={} ex={}",
            url,
            app_key,
            token[:16] if token else "(none)",
            self._language,
            nls_ex,
        )

        sr = nls.NlsSpeechTranscriber(
            url=url,
            token=token,
            appkey=app_key,
            on_sentence_begin=on_sentence_begin,
            on_sentence_end=on_sentence_end,
            on_result_changed=on_result_changed,
            on_completed=on_completed,
            on_error=on_error,
            on_close=on_close,
        )
        self._sr = sr

        try:
            sr.start(
                aformat="pcm",
                sample_rate=16000,
                ch=1,
                enable_intermediate_result=True,
                enable_punctuation_prediction=True,
                enable_inverse_text_normalization=True,
                ex=nls_ex,
            )
            logger.info("[AliNLS-stream] sr.start() returned OK")
        except Exception as e:
            self._error = f"NLS start() failed: {e}"
            logger.error("[AliNLS-stream] {}", self._error)
            self._ready.set()
            self._signal_done()
            return

        # Check if on_close/on_error fired during start()
        if self._closed:
            logger.warning(
                "[AliNLS-stream] connection closed during start(), error={}",
                self._error,
            )
            self._ready.set()
            return

        # Signal that the session is ready to receive audio
        self._ready.set()

        # Consume audio chunks from the stdlib queue (blocking, no asyncio)
        chunks_sent = 0
        while True:
            try:
                chunk = self._audio_queue.get(timeout=30)
            except _queue_mod.Empty:
                logger.warning("[AliNLS-stream] queue timeout (30s idle), stopping")
                break

            if chunk is None:
                # Sentinel: end of stream
                break

            if self._cancelled or self._closed:
                break

            # Feed to NLS in small sub-chunks (3200B = 100ms) with pacing
            for i in range(0, len(chunk), 3200):
                if self._closed:
                    break
                sub = chunk[i : i + 3200]
                sr.send_audio(sub)
            chunks_sent += 1

        logger.info("[AliNLS-stream] fed {} chunks total, calling stop()", chunks_sent)

        # Signal NLS to finalize
        if not self._closed:
            try:
                sr.stop()
            except Exception as e:
                logger.warning("[AliNLS-stream] stop() error: {}", e)
                if not self._error:
                    self._error = str(e)
                self._signal_done()

    def _signal_done(self) -> None:
        """Signal completion from any thread."""
        self._done_flag.set()
        try:
            self._loop.call_soon_threadsafe(self._done_async.set)
        except RuntimeError:
            pass  # loop already closed

    async def feed(self, pcm_bytes: bytes) -> None:
        if not self._started:
            raise RuntimeError("Stream session not started")
        if self._closed:
            logger.warning("[AliNLS-stream] feed() called on closed session, buffering locally")
        self._total_bytes += len(pcm_bytes)
        self._audio_queue.put_nowait(pcm_bytes)

    @property
    def is_alive(self) -> bool:
        """True if the NLS session is still connected."""
        return self._started and not self._closed

    async def finish(self) -> ASRResult:
        # Send sentinel to stop the worker
        self._audio_queue.put_nowait(None)

        # Wait for NLS completion (max 15s)
        try:
            await asyncio.wait_for(self._done_async.wait(), timeout=15)
        except asyncio.TimeoutError:
            logger.warning("[AliNLS-stream] timed out waiting for completion (15s)")

        if self._error:
            raise RuntimeError(f"Ali NLS stream error: {self._error}")

        text = "".join(self._results).strip()
        lang = self._language or self._provider._config.language or "zh"
        duration = round(self._total_bytes / (16000 * 2), 2)

        logger.info(
            "[AliNLS-stream] DONE: {:.1f}s → '{}' (sentences={})",
            duration,
            text[:100] if text else "(empty)",
            len(self._results),
        )
        return ASRResult(text=text, language=lang, duration=duration)

    async def cancel(self) -> None:
        self._cancelled = True
        self._audio_queue.put_nowait(None)


class AliNlsASRProvider(ASRProvider):
    """ASR via Alibaba Cloud NLS WebSocket SDK (alibabacloud-nls-python-sdk).

    Features:
    - Automatic token lifecycle management (AK/SK → CreateToken → cache)
    - Falls back to static token if AK/SK not provided
    - Sends PCM in 3200-byte chunks (100 ms at 16 kHz 16-bit)
    - Collects sentence-end results for final transcript
    - Streams intermediate results via on_intermediate callback
    """

    def __init__(self, provider_config: ASRProviderConfig) -> None:
        self._config = provider_config
        self._token_manager: TokenManager | None = None

        # Set up token management
        if provider_config.access_key_id and provider_config.access_key_secret:
            self._token_manager = TokenManager(
                provider_config.access_key_id,
                provider_config.access_key_secret,
            )
            logger.info(
                "[AliNLS] init: AK/SK token management enabled, app_key={}",
                provider_config.app_key[:8] + "..." if provider_config.app_key else "(empty)",
            )
        elif provider_config.api_key:
            logger.info(
                "[AliNLS] init: using static token ({}...), app_key={}",
                provider_config.api_key[:8],
                provider_config.app_key[:8] + "..." if provider_config.app_key else "(empty)",
            )
        else:
            raise ValueError(
                "Ali NLS provider requires either access_key_id/access_key_secret "
                "or a static api_key (token)"
            )

    async def _get_token(self) -> str:
        """Get a valid NLS token."""
        if self._token_manager:
            return await self._token_manager.get_token()
        return self._config.api_key

    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str | None = None,
        on_intermediate: IntermediateCallback | None = None,
    ) -> ASRResult:
        """Transcribe audio via Ali NLS SDK."""
        token = await self._get_token()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._transcribe_sync,
            token,
            audio_bytes,
            language,
            on_intermediate,
        )

    def _transcribe_sync(
        self,
        token: str,
        audio_bytes: bytes,
        language: str | None,
        on_intermediate: IntermediateCallback | None,
    ) -> ASRResult:
        """Synchronous Ali NLS transcription (runs in thread executor)."""
        try:
            import nls
        except ImportError:
            raise RuntimeError(
                "alibabacloud-nls-python-sdk not installed. "
                "Install with: pip install alibabacloud-nls-python-sdk"
            )

        # Strip WAV header if present → raw PCM
        raw_pcm = audio_bytes
        if raw_pcm[:4] == b"RIFF":
            raw_pcm = raw_pcm[44:]

        duration = len(raw_pcm) / (16000 * 2)  # 16 kHz, 16-bit

        results: list[str] = []
        sentence_idx = 0
        # Use threading.Event since we're in a sync context
        import threading

        done = threading.Event()
        error_msg: str | None = None

        def _build_full_text(current_intermediate: str = "") -> str:
            """Build full text = confirmed sentences + current intermediate."""
            parts = list(results)
            if current_intermediate:
                parts.append(current_intermediate)
            return "".join(parts)

        def on_sentence_begin(message, *args):
            logger.info("[AliNLS] sentence_begin: {}", message[:200] if message else "")

        def on_sentence_end(message, *args):
            nonlocal sentence_idx
            import json

            logger.info("[AliNLS] sentence_end: {}", message[:200] if message else "")
            try:
                data = json.loads(message)
                text = data.get("payload", {}).get("result", "")
                if text:
                    results.append(text)
                    sentence_idx += 1
                    logger.info("[AliNLS] collected sentence #{}: '{}'", sentence_idx, text[:100])
                    # Push confirmed text to mobile
                    if on_intermediate:
                        try:
                            on_intermediate(_build_full_text(), sentence_idx, True)
                        except Exception:
                            pass
            except Exception as e:
                logger.warning("[AliNLS] failed to parse sentence_end: {}", e)

        def on_result_changed(message, *args):
            import json

            try:
                data = json.loads(message)
                text = data.get("payload", {}).get("result", "")
                if text:
                    logger.debug("[AliNLS] intermediate: '{}'", text[:100])
                    # Push partial text = confirmed sentences + current partial
                    if on_intermediate:
                        try:
                            on_intermediate(_build_full_text(text), sentence_idx, False)
                        except Exception:
                            pass
            except Exception:
                pass

        def on_completed(message, *args):
            logger.info("[AliNLS] transcription completed")
            done.set()

        def on_error(message, *args):
            nonlocal error_msg
            error_msg = str(message)
            logger.error("[AliNLS] ERROR: {}", message)
            done.set()

        def on_close(*args):
            logger.debug("[AliNLS] connection closed")
            done.set()

        url = self._config.api_base or _DEFAULT_WS_URL
        app_key = self._config.app_key

        nls_ex = _build_nls_ex(language)
        logger.info(
            "[AliNLS] connecting: url={} appkey={} token={}... audio={:.1f}s ({}B PCM) lang={} ex={}",
            url,
            app_key,
            token[:16] if token else "(none)",
            duration,
            len(raw_pcm),
            language,
            nls_ex,
        )

        sr = nls.NlsSpeechTranscriber(
            url=url,
            token=token,
            appkey=app_key,
            on_sentence_begin=on_sentence_begin,
            on_sentence_end=on_sentence_end,
            on_result_changed=on_result_changed,
            on_completed=on_completed,
            on_error=on_error,
            on_close=on_close,
        )

        try:
            sr.start(
                aformat="pcm",
                sample_rate=16000,
                ch=1,
                enable_intermediate_result=True,
                enable_punctuation_prediction=True,
                enable_inverse_text_normalization=True,
                ex=nls_ex,
            )
            logger.info("[AliNLS] start() OK — transcription session active")
        except Exception as e:
            logger.error("[AliNLS] start() failed: {}", e)
            raise RuntimeError(f"NLS start() failed: {e}") from e

        logger.info("[AliNLS] streaming {} chunks ...", (len(raw_pcm) + 3199) // 3200)

        # Send audio in 3200-byte chunks (100 ms at 16 kHz 16-bit)
        chunk_size = 3200
        chunks_sent = 0
        for i in range(0, len(raw_pcm), chunk_size):
            chunk = raw_pcm[i : i + chunk_size]
            sr.send_audio(chunk)
            chunks_sent += 1
            time.sleep(0.05)  # ~50 ms pacing

        logger.info("[AliNLS] all {} chunks sent, calling stop()", chunks_sent)
        sr.stop()

        # Wait for completion (max 15s)
        done.wait(timeout=15)

        if error_msg:
            raise RuntimeError(f"Ali NLS error: {error_msg}")

        if not done.is_set():
            logger.warning("[AliNLS] timed out waiting for completion (15s)")

        text = "".join(results).strip()
        lang = language or self._config.language or "zh"

        logger.info(
            "[AliNLS] DONE: {:.1f}s audio → '{}' (lang={}, sentences={})",
            duration,
            text[:100] if text else "(empty)",
            lang,
            len(results),
        )
        return ASRResult(text=text, language=lang, duration=round(duration, 2))

    @property
    def supports_streaming(self) -> bool:
        return True

    async def start_stream(
        self,
        language: str | None = None,
        on_intermediate: IntermediateCallback | None = None,
    ) -> AliNlsStreamSession:
        session = AliNlsStreamSession(self, language, on_intermediate)
        await session.start()
        return session

    async def close(self) -> None:
        """Nothing to clean up — each transcribe call is self-contained."""
