"""Audio format conversion for ASR — converts OGG/Opus/MP3/etc. to PCM 16kHz mono."""

from __future__ import annotations

import io
import wave

from loguru import logger

# PCM output format expected by ASR providers
SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2  # 16-bit
CHANNELS = 1


def to_pcm(audio_bytes: bytes) -> bytes:
    """Convert audio bytes (any format) to raw PCM 16-bit 16kHz mono.

    Supports: OGG/Opus, MP3, WAV, M4A, AAC, FLAC, AMR, and other formats
    handled by PyAV (libav/ffmpeg).

    If the input is already raw PCM (no recognisable header), returns as-is.

    Returns:
        Raw PCM bytes (16-bit LE, 16 kHz, mono).
    """
    if not audio_bytes:
        return audio_bytes

    # Already WAV — extract PCM payload
    if audio_bytes[:4] == b"RIFF":
        return _wav_to_pcm(audio_bytes)

    # Try PyAV for any container format (OGG, MP3, M4A, etc.)
    if _has_container_header(audio_bytes):
        try:
            return _av_decode_to_pcm(audio_bytes)
        except Exception as e:
            logger.warning("PyAV decode failed, returning raw bytes: {}", e)

    # Assume raw PCM
    return audio_bytes


def to_wav(audio_bytes: bytes) -> bytes:
    """Convert audio bytes to WAV format (16-bit 16kHz mono).

    If already WAV, returns as-is. Otherwise converts via to_pcm() + WAV header.
    """
    if audio_bytes[:4] == b"RIFF":
        return audio_bytes

    pcm = to_pcm(audio_bytes)
    return _pcm_to_wav(pcm)


def _wav_to_pcm(wav_bytes: bytes) -> bytes:
    """Extract raw PCM from WAV, resampling if needed."""
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as wf:
        if (
            wf.getnchannels() == CHANNELS
            and wf.getsampwidth() == SAMPLE_WIDTH
            and wf.getframerate() == SAMPLE_RATE
        ):
            return wf.readframes(wf.getnframes())

    # Need resampling — use PyAV
    try:
        return _av_decode_to_pcm(wav_bytes)
    except Exception:
        # Last resort: return raw frames without resampling
        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            return wf.readframes(wf.getnframes())


def _pcm_to_wav(pcm_bytes: bytes) -> bytes:
    """Wrap raw PCM in a WAV header."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def _has_container_header(data: bytes) -> bool:
    """Check if data starts with a known audio container header."""
    if len(data) < 4:
        return False
    # OGG (Opus/Vorbis)
    if data[:4] == b"OggS":
        return True
    # MP3 (ID3 tag or sync word)
    if data[:3] == b"ID3" or (data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return True
    # FLAC
    if data[:4] == b"fLaC":
        return True
    # M4A/AAC (ftyp box)
    if len(data) >= 8 and data[4:8] == b"ftyp":
        return True
    # AMR
    if data[:6] == b"#!AMR\n" or data[:9] == b"#!AMR-WB\n":
        return True
    return False


def _av_decode_to_pcm(audio_bytes: bytes) -> bytes:
    """Decode any audio format to PCM using PyAV."""
    import av

    buf = io.BytesIO(audio_bytes)
    container = av.open(buf, format=None)

    try:
        audio_stream = next(s for s in container.streams if s.type == "audio")
    except StopIteration:
        raise ValueError("No audio stream found in input")

    resampler = av.AudioResampler(
        format="s16",  # 16-bit signed LE
        layout="mono",
        rate=SAMPLE_RATE,
    )

    pcm_chunks: list[bytes] = []
    for frame in container.decode(audio_stream):
        resampled = resampler.resample(frame)
        for rf in resampled:
            pcm_chunks.append(rf.to_ndarray().tobytes())

    container.close()

    pcm = b"".join(pcm_chunks)
    duration = len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH)
    logger.debug("Audio converted to PCM: {:.1f}s, {} bytes", duration, len(pcm))
    return pcm
