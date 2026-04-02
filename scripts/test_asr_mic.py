#!/usr/bin/env python3
"""Quick ASR test: record from microphone → transcribe via configured ASR provider.

Usage:
    python scripts/test_asr_mic.py              # Record 5 seconds, then transcribe
    python scripts/test_asr_mic.py --duration 10  # Record 10 seconds
    python scripts/test_asr_mic.py --lang en      # Force English
"""

import argparse
import asyncio
import sys

import numpy as np
import sounddevice as sd


def record_audio(duration: float, sample_rate: int = 16000) -> bytes:
    """Record audio from default microphone, return raw PCM bytes."""
    print(f"🎙  Recording {duration}s ... (speak now)")
    audio = sd.rec(
        int(duration * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        blocking=True,
    )
    print("   Recording complete.")
    # Convert to bytes
    return audio.astype(np.int16).tobytes()


async def main():
    parser = argparse.ArgumentParser(description="Test ASR with microphone input")
    parser.add_argument("--duration", type=float, default=5, help="Recording duration in seconds")
    parser.add_argument("--lang", type=str, default=None, help="Language hint (zh, en, ja, etc.)")
    args = parser.parse_args()

    # Record
    pcm_bytes = record_audio(args.duration)
    print(f"   Audio size: {len(pcm_bytes)} bytes ({len(pcm_bytes) / (16000 * 2):.1f}s)")

    # Load config and create ASR service
    from comobot.asr import ASRService
    from comobot.config.loader import load_config

    config = load_config()
    if not config.asr.enabled:
        print("ERROR: ASR is not enabled in config. Set asr.enabled = true")
        sys.exit(1)
    if not config.asr.provider:
        print("ERROR: No active ASR provider configured.")
        sys.exit(1)

    print(
        f"   Provider: {config.asr.provider} (mode={config.asr.providers[config.asr.provider].mode})"
    )

    service = ASRService(config.asr)
    try:
        result = await service.transcribe(pcm_bytes, language=args.lang)
        print("\n✅ Result:")
        print(f"   Text:     {result.text}")
        print(f"   Language: {result.language}")
        print(f"   Duration: {result.duration}s")
    except Exception as e:
        print(f"\n❌ ASR failed: {e}")
        sys.exit(1)
    finally:
        await service.close()


if __name__ == "__main__":
    asyncio.run(main())
