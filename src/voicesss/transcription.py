from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

import numpy as np

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
if not os.getenv("HF_TOKEN") and not os.getenv("HUGGING_FACE_HUB_TOKEN"):
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")


@dataclass(frozen=True, slots=True)
class TranscriptionSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    text: str
    language: str | None
    language_probability: float | None
    segments: tuple[TranscriptionSegment, ...]


class Transcriber(Protocol):
    def transcribe(self, source: str | Path | np.ndarray) -> TranscriptionResult:
        ...


WHISPER_SAMPLE_RATE = 16_000


def resample_audio(audio: np.ndarray, source_sample_rate: int, target_sample_rate: int = WHISPER_SAMPLE_RATE) -> np.ndarray:
    if source_sample_rate == target_sample_rate:
        return audio.astype(np.float32, copy=False)

    if source_sample_rate > target_sample_rate and source_sample_rate % target_sample_rate == 0:
        ratio = source_sample_rate // target_sample_rate
        usable = (audio.size // ratio) * ratio
        if usable == 0:
            return np.array([], dtype=np.float32)
        return audio[:usable].reshape(-1, ratio).mean(axis=1).astype(np.float32)

    duration = audio.size / source_sample_rate
    target_size = max(1, int(round(duration * target_sample_rate)))
    source_positions = np.linspace(0.0, duration, num=audio.size, endpoint=False)
    target_positions = np.linspace(0.0, duration, num=target_size, endpoint=False)
    return np.interp(target_positions, source_positions, audio).astype(np.float32)


def pcm16_to_float32_audio(
    pcm: bytes,
    *,
    source_sample_rate: int = WHISPER_SAMPLE_RATE,
    target_sample_rate: int = WHISPER_SAMPLE_RATE,
) -> np.ndarray:
    samples = np.frombuffer(pcm, dtype=np.int16)
    audio = samples.astype(np.float32) / 32768.0
    return resample_audio(audio, source_sample_rate, target_sample_rate)


class FasterWhisperTranscriber:
    def __init__(
        self,
        model: str = "small",
        *,
        language: str = "pt",
        device: str = "auto",
        compute_type: str = "auto",
        cpu_threads: int = 0,
        beam_size: int = 5,
        vad_filter: bool = True,
    ) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "O motor faster-whisper nao esta instalado. "
                'Instale com: pip install -e ".[stt]"'
            ) from exc

        self.language = language
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self._model = WhisperModel(
            model,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads,
        )

    def transcribe(self, source: str | Path | np.ndarray) -> TranscriptionResult:
        segments_iter, info = self._model.transcribe(
            str(source) if isinstance(source, Path) else source,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
            condition_on_previous_text=False,
        )
        segments = tuple(self._convert_segments(segments_iter))
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return TranscriptionResult(
            text=text,
            language=getattr(info, "language", None),
            language_probability=getattr(info, "language_probability", None),
            segments=segments,
        )

    @staticmethod
    def _convert_segments(segments: Iterable[Any]) -> Iterable[TranscriptionSegment]:
        for segment in segments:
            yield TranscriptionSegment(
                start=float(segment.start),
                end=float(segment.end),
                text=str(segment.text).strip(),
            )
