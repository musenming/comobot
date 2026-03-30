"""ASR (Automatic Speech Recognition) module.

Provides a unified ``ASRService`` that any channel can use::

    from comobot.asr import ASRService, ASRResult

    service = ASRService(config.asr)
    result = await service.transcribe(audio_bytes, language="zh")
"""

from .audio_converter import to_pcm, to_wav
from .base import ASRProvider, ASRResult, ASRStreamSession, IntermediateCallback
from .service import ASRService

__all__ = [
    "ASRProvider",
    "ASRResult",
    "ASRService",
    "ASRStreamSession",
    "IntermediateCallback",
    "to_pcm",
    "to_wav",
]
