"""ASR provider abstract base class and common types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class ASRResult:
    """Unified ASR transcription result."""

    text: str
    language: str
    duration: float  # seconds


# Callback signature: (intermediate_text: str, sentence_index: int, is_final: bool) → None
# is_final=False means partial/interim result (may change), True means sentence confirmed.
IntermediateCallback = Callable[[str, int, bool], None]


class ASRStreamSession(ABC):
    """A live streaming transcription session.

    Created by ``ASRProvider.start_stream()``.  Feed audio chunks as they
    arrive, receive intermediate results via callback, then call ``finish()``
    to get the final transcript.
    """

    @abstractmethod
    async def feed(self, pcm_bytes: bytes) -> None:
        """Feed a PCM audio chunk into the live session."""

    @abstractmethod
    async def finish(self) -> ASRResult:
        """Signal end-of-audio and return the final transcript."""

    @abstractmethod
    async def cancel(self) -> None:
        """Abort the session without waiting for a result."""


@dataclass
class AudioStreamBuffer:
    """Per-request accumulator for streaming audio chunks."""

    request_id: str
    device_id: str
    language: str | None = None
    chunks: list[bytes] = field(default_factory=list)
    total_bytes: int = 0
    on_intermediate: IntermediateCallback | None = None

    def append(self, pcm_bytes: bytes) -> None:
        self.chunks.append(pcm_bytes)
        self.total_bytes += len(pcm_bytes)

    def get_all_pcm(self) -> bytes:
        return b"".join(self.chunks)

    @property
    def duration(self) -> float:
        """Approximate duration in seconds (16kHz, 16-bit mono)."""
        return self.total_bytes / (16000 * 2)


class ASRProvider(ABC):
    """Abstract base for all ASR providers.

    Any channel (remote voice, WeChat voice message, Telegram voice, etc.)
    can call ``transcribe()`` to get text from audio.
    """

    @abstractmethod
    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str | None = None,
        on_intermediate: IntermediateCallback | None = None,
    ) -> ASRResult:
        """Transcribe audio bytes to text.

        Args:
            audio_bytes: Raw PCM (16-bit LE, 16 kHz mono) or WAV bytes.
            language: BCP-47 language hint (e.g. 'zh', 'en'). None = auto.
            on_intermediate: Optional callback fired with partial text during
                recognition.  Called from a worker thread — must be thread-safe.

        Returns:
            ASRResult with text, detected language, and duration.
        """

    @property
    def supports_streaming(self) -> bool:
        """Whether this provider can keep a session open across multiple feed() calls."""
        return False

    async def start_stream(
        self,
        language: str | None = None,
        on_intermediate: IntermediateCallback | None = None,
    ) -> ASRStreamSession:
        """Open a live streaming transcription session.

        Override in providers that support true streaming (e.g. Ali NLS).
        """
        raise NotImplementedError(f"{type(self).__name__} does not support streaming")

    async def close(self) -> None:
        """Release resources. Override if the provider holds connections."""
