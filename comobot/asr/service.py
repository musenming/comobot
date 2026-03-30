"""ASR service facade — unified entry point for all speech recognition.

Usage from any channel::

    from comobot.asr import ASRService

    service = ASRService(config.asr)
    result = await service.transcribe(pcm_bytes, language="zh")
    print(result.text, result.language, result.duration)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from .base import ASRProvider, ASRResult, ASRStreamSession, IntermediateCallback

if TYPE_CHECKING:
    from comobot.config.schema import ASRConfig


class ASRService:
    """Routes transcription requests to the configured ASR provider.

    Supports hot-switching: reads the active provider from config on each call,
    lazily initialises provider instances, and caches them for reuse.
    """

    def __init__(self, config: ASRConfig) -> None:
        self.config = config
        self._providers: dict[str, ASRProvider] = {}

    def _get_provider(self) -> tuple[str, ASRProvider]:
        """Return (name, provider) for the currently active provider."""
        name = self.config.provider
        if not name:
            raise RuntimeError("No active ASR provider configured")

        provider_cfg = self.config.providers.get(name)
        if not provider_cfg:
            raise RuntimeError(f"ASR provider '{name}' not found in config")

        # Return cached instance if available
        if name in self._providers:
            return name, self._providers[name]

        # Lazy-init based on mode
        provider = _create_provider(name, provider_cfg)
        self._providers[name] = provider
        logger.info("ASR provider '{}' initialised (mode={})", name, provider_cfg.mode)
        return name, provider

    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str | None = None,
        on_intermediate: IntermediateCallback | None = None,
    ) -> ASRResult:
        """Transcribe audio using the active provider.

        Args:
            audio_bytes: Raw PCM (16-bit LE, 16 kHz mono) or WAV bytes.
            language: BCP-47 hint. None = auto / provider default.
            on_intermediate: Optional callback for streaming partial results.

        Returns:
            ASRResult(text, language, duration)
        """
        if not self.config.enabled:
            raise RuntimeError("ASR is disabled")

        name, provider = self._get_provider()
        try:
            return await provider.transcribe(audio_bytes, language, on_intermediate)
        except Exception:
            logger.exception("ASR transcription failed [{}]", name)
            raise

    async def start_stream(
        self,
        language: str | None = None,
        on_intermediate: IntermediateCallback | None = None,
    ) -> ASRStreamSession:
        """Open a live streaming transcription session via the active provider."""
        if not self.config.enabled:
            raise RuntimeError("ASR is disabled")

        name, provider = self._get_provider()
        if not provider.supports_streaming:
            raise RuntimeError(f"ASR provider '{name}' does not support streaming")

        try:
            return await provider.start_stream(language, on_intermediate)
        except Exception:
            logger.exception("Failed to start ASR stream [{}]", name)
            raise

    @property
    def supports_streaming(self) -> bool:
        """Check if the active provider supports streaming."""
        try:
            _, provider = self._get_provider()
            return provider.supports_streaming
        except Exception:
            return False

    def invalidate_provider(self, name: str) -> None:
        """Remove a cached provider instance (e.g. after config change)."""
        old = self._providers.pop(name, None)
        if old:
            logger.debug("Invalidated ASR provider cache for '{}'", name)

    async def close(self) -> None:
        """Shut down all cached providers."""
        for name, provider in self._providers.items():
            try:
                await provider.close()
            except Exception:
                logger.warning("Error closing ASR provider '{}'", name)
        self._providers.clear()


def _create_provider(name: str, cfg) -> ASRProvider:
    """Factory: create the right provider based on config mode."""
    from comobot.config.schema import ASRProviderConfig

    assert isinstance(cfg, ASRProviderConfig)

    if cfg.mode == "ali_nls":
        from .ali_nls_provider import AliNlsASRProvider

        return AliNlsASRProvider(cfg)

    if cfg.mode in ("rest", "openai"):
        from .rest_provider import RestASRProvider

        return RestASRProvider(cfg)

    # Legacy: treat "ws" as ali_nls for backward compatibility
    if cfg.mode == "ws":
        from .ali_nls_provider import AliNlsASRProvider

        logger.warning(
            "ASR provider '{}' uses deprecated mode='ws', please change to 'ali_nls'",
            name,
        )
        return AliNlsASRProvider(cfg)

    raise ValueError(f"Unknown ASR mode '{cfg.mode}' for provider '{name}'")
