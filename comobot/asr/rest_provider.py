"""OpenAI-compatible REST ASR provider (Groq, OpenAI Whisper, etc.)."""

from __future__ import annotations

import io
import wave
from typing import TYPE_CHECKING

import httpx
from loguru import logger

from .base import ASRProvider, ASRResult, IntermediateCallback

if TYPE_CHECKING:
    from comobot.config.schema import ASRProviderConfig


class RestASRProvider(ASRProvider):
    """ASR via OpenAI-compatible ``/audio/transcriptions`` endpoint.

    Works with Groq, OpenAI, local faster-whisper servers, etc.
    """

    def __init__(self, provider_config: ASRProviderConfig) -> None:
        self._config = provider_config
        if not provider_config.api_key:
            raise ValueError("REST ASR provider requires an api_key")
        if not provider_config.api_base:
            raise ValueError("REST ASR provider requires an api_base URL")

    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str | None = None,
        on_intermediate: IntermediateCallback | None = None,
    ) -> ASRResult:
        """Transcribe via POST /audio/transcriptions."""
        wav_bytes = _ensure_wav(audio_bytes)

        api_base = self._config.api_base.rstrip("/")
        url = f"{api_base}/audio/transcriptions"
        model = self._config.model or "whisper-large-v3"
        lang = language or self._config.language

        headers = {"Authorization": f"Bearer {self._config.api_key}"}
        files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
        data: dict = {"model": model, "response_format": "verbose_json"}
        if lang:
            data["language"] = lang

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, headers=headers, files=files, data=data)
                resp.raise_for_status()
                result = resp.json()

            text = result.get("text", "").strip()
            detected_lang = result.get("language", lang or "")
            duration = result.get("duration", 0)

            logger.debug(
                "REST ASR: {:.1f}s → '{}' (lang={})",
                duration,
                text[:80],
                detected_lang,
            )
            return ASRResult(
                text=text,
                language=detected_lang,
                duration=round(duration, 2) if duration else 0,
            )

        except httpx.HTTPStatusError as e:
            logger.error("REST ASR error: {} {}", e.response.status_code, e.response.text[:200])
            raise RuntimeError(f"ASR API error: {e.response.status_code}") from e
        except Exception as e:
            logger.error("REST ASR failed: {}", e)
            raise


def _ensure_wav(audio_bytes: bytes) -> bytes:
    """Wrap raw PCM in a WAV header if not already WAV."""
    if audio_bytes[:4] == b"RIFF":
        return audio_bytes

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio_bytes)
    return buf.getvalue()
