from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


@dataclass(frozen=True)
class VoiceConfig:
    model: str = os.getenv("VOICESSS_MODEL", "tiny")
    language: str = os.getenv("VOICESSS_LANGUAGE", "pt")
    device: str = os.getenv("VOICESSS_DEVICE", "cpu")
    compute_type: str = os.getenv("VOICESSS_COMPUTE_TYPE", "int8")
    cpu_threads: int = _env_int("VOICESSS_CPU_THREADS", min(os.cpu_count() or 4, 4))
    beam_size: int = _env_int("VOICESSS_BEAM_SIZE", 1)
    sample_rate: int = _env_int("VOICESSS_SAMPLE_RATE", 16_000)
    frame_ms: int = _env_int("VOICESSS_FRAME_MS", 30)
    vad_aggressiveness: int = _env_int("VOICESSS_VAD_AGGRESSIVENESS", 2)
    min_speech_ms: int = _env_int("VOICESSS_MIN_SPEECH_MS", 120)
    silence_ms: int = _env_int("VOICESSS_SILENCE_MS", 500)
    max_utterance_ms: int = _env_int("VOICESSS_MAX_UTTERANCE_MS", 4_000)
