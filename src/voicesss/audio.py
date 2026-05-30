from __future__ import annotations

import queue
import unicodedata
from collections import deque
from dataclasses import dataclass
from threading import Event
from typing import Iterator


@dataclass(frozen=True, slots=True)
class AudioChunk:
    pcm: bytes
    sample_rate: int

    @property
    def seconds(self) -> float:
        return len(self.pcm) / (self.sample_rate * 2)


@dataclass(frozen=True, slots=True)
class InputDevice:
    index: int
    name: str
    channels: int
    default_sample_rate: int
    host_api: str = ""
    is_default: bool = False
    is_recommended: bool = True

    @property
    def stable_key(self) -> str:
        return f"{_fold_text(self.name)}|{_fold_text(self.host_api)}"


def _fold_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    folded = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(folded.casefold().split())


def _looks_like_placeholder(name: str) -> bool:
    folded = _fold_text(name)
    blocked = (
        "mapeador de som",
        "sound mapper",
        "driver de captura de som primario",
        "primary sound capture",
        "mixagem stereo",
        "stereo mix",
        "loopback",
        "what u hear",
        "monitor",
    )
    return any(term in folded for term in blocked)


def _looks_virtual(name: str) -> bool:
    folded = _fold_text(name)
    virtual_terms = (
        "virtual",
        "vb-audio",
        "cable output",
        "voicewave",
        "voicemod",
        "audiorelay",
    )
    return any(term in folded for term in virtual_terms)


def _is_recommended_input_device(device: InputDevice) -> bool:
    if _looks_like_placeholder(device.name):
        return False
    if device.is_default:
        return True

    host_api = _fold_text(device.host_api)
    if "wasapi" not in host_api:
        return False
    if _looks_virtual(device.name):
        return False

    folded_name = _fold_text(device.name)
    mic_terms = ("microfone", "microphone", "mic")
    return any(term in folded_name for term in mic_terms)


def _refresh_portaudio(sd: object) -> None:
    terminate = getattr(sd, "_terminate", None)
    initialize = getattr(sd, "_initialize", None)
    if callable(terminate) and callable(initialize):
        terminate()
        initialize()


def _preferred_default_input(sd: object, host_apis: tuple[dict, ...] | list[dict]) -> int:
    for host_api in host_apis:
        api_name = _fold_text(str(host_api.get("name", "")))
        api_default = int(host_api.get("default_input_device", -1))
        if "wasapi" in api_name and api_default >= 0:
            return api_default

    default_input = sd.default.device[0]
    return int(default_input) if default_input is not None else -1


def list_input_devices(*, include_all: bool = False, refresh: bool = False) -> list[InputDevice]:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError(
            "O suporte a microfone nao esta instalado. "
            'Instale com: pip install -e ".[mic]"'
        ) from exc

    if refresh:
        _refresh_portaudio(sd)

    host_apis = sd.query_hostapis()
    preferred_default_input = _preferred_default_input(sd, host_apis)

    devices: list[InputDevice] = []
    for index, device in enumerate(sd.query_devices()):
        channels = int(device.get("max_input_channels", 0))
        if channels <= 0:
            continue

        host_api_index = int(device.get("hostapi", -1))
        host_api_name = ""
        if 0 <= host_api_index < len(host_apis):
            host_api_name = str(host_apis[host_api_index].get("name", ""))

        input_device = InputDevice(
            index=index,
            name=str(device.get("name", f"device-{index}")),
            channels=channels,
            default_sample_rate=int(device.get("default_samplerate", 0)),
            host_api=host_api_name,
            is_default=index == preferred_default_input,
            is_recommended=False,
        )
        input_device = InputDevice(
            index=input_device.index,
            name=input_device.name,
            channels=input_device.channels,
            default_sample_rate=input_device.default_sample_rate,
            host_api=input_device.host_api,
            is_default=input_device.is_default,
            is_recommended=_is_recommended_input_device(input_device),
        )

        if include_all or input_device.is_recommended:
            devices.append(input_device)

    if not devices and not include_all:
        return list_input_devices(include_all=True, refresh=False)

    return sorted(
        devices,
        key=lambda item: (
            not item.is_default,
            0 if "wasapi" in _fold_text(item.host_api) else 1,
            _looks_virtual(item.name),
            _fold_text(item.name),
            item.index,
        ),
    )


class MicrophoneVAD:
    def __init__(
        self,
        *,
        device: int | None = None,
        sample_rate: int | None = 16_000,
        frame_ms: int = 30,
        aggressiveness: int = 2,
        min_speech_ms: int = 240,
        silence_ms: int = 900,
        max_utterance_ms: int = 30_000,
    ) -> None:
        if sample_rate is not None and sample_rate not in {8_000, 16_000, 32_000, 48_000}:
            raise ValueError("sample_rate precisa ser 8000, 16000, 32000 ou 48000.")
        if frame_ms not in {10, 20, 30}:
            raise ValueError("frame_ms precisa ser 10, 20 ou 30 para o WebRTC VAD.")
        if not 0 <= aggressiveness <= 3:
            raise ValueError("aggressiveness precisa estar entre 0 e 3.")

        self.device = device
        self.requested_sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.aggressiveness = aggressiveness
        self.min_speech_frames = max(1, min_speech_ms // frame_ms)
        self.silence_frames = max(1, silence_ms // frame_ms)
        self.max_frames = max(1, max_utterance_ms // frame_ms)

    def iter_utterances(self, stop_event: Event | None = None) -> Iterator[AudioChunk]:
        try:
            import sounddevice as sd
            import webrtcvad
        except ImportError as exc:
            raise RuntimeError(
                "O suporte a captura/VAD nao esta instalado. "
                'Instale com: pip install -e ".[mic]"'
            ) from exc

        sample_rate = self._select_sample_rate(sd)
        frame_samples = int(sample_rate * self.frame_ms / 1000)
        vad = webrtcvad.Vad(self.aggressiveness)
        frames: queue.Queue[bytes] = queue.Queue()

        def callback(indata: bytes, frame_count: int, time_info: object, status: object) -> None:
            del frame_count, time_info, status
            frames.put(bytes(indata))

        with sd.RawInputStream(
            samplerate=sample_rate,
            blocksize=frame_samples,
            device=self.device,
            channels=1,
            dtype="int16",
            callback=callback,
        ):
            yield from self._collect_utterances(frames, vad, sample_rate=sample_rate, stop_event=stop_event)

    def _select_sample_rate(self, sd: object) -> int:
        candidates: list[int] = []
        if self.requested_sample_rate is not None:
            candidates.append(self.requested_sample_rate)

        if self.device is not None:
            default_rate = int(sd.query_devices(self.device).get("default_samplerate", 0))
            if default_rate in {8_000, 16_000, 32_000, 48_000}:
                candidates.append(default_rate)

        candidates.extend([48_000, 32_000, 16_000, 8_000])

        seen: set[int] = set()
        for sample_rate in candidates:
            if sample_rate in seen:
                continue
            seen.add(sample_rate)
            try:
                sd.check_input_settings(
                    device=self.device,
                    channels=1,
                    dtype="int16",
                    samplerate=sample_rate,
                )
            except Exception:
                continue
            return sample_rate

        raise RuntimeError(
            "Nao consegui abrir este microfone em 8000, 16000, 32000 ou 48000 Hz. "
            "Tente outro microfone ou marque 'Mostrar todos' e escolha uma entrada WASAPI."
        )

    def _collect_utterances(
        self,
        frames: queue.Queue[bytes],
        vad: object,
        *,
        sample_rate: int,
        stop_event: Event | None = None,
    ) -> Iterator[AudioChunk]:
        padding = deque(maxlen=self.min_speech_frames)
        voiced: list[bytes] = []
        triggered = False
        speech_count = 0
        silence_count = 0

        while stop_event is None or not stop_event.is_set():
            try:
                frame = frames.get(timeout=0.1)
            except queue.Empty:
                continue
            is_speech = bool(vad.is_speech(frame, sample_rate))

            if not triggered:
                padding.append(frame)
                speech_count = speech_count + 1 if is_speech else max(0, speech_count - 1)
                if speech_count >= self.min_speech_frames:
                    triggered = True
                    voiced = list(padding)
                    padding.clear()
                    silence_count = 0
                continue

            voiced.append(frame)
            if is_speech:
                silence_count = 0
            else:
                silence_count += 1

            utterance_is_done = silence_count >= self.silence_frames
            utterance_is_too_long = len(voiced) >= self.max_frames
            if utterance_is_done or utterance_is_too_long:
                if voiced:
                    yield AudioChunk(pcm=b"".join(voiced), sample_rate=sample_rate)
                triggered = False
                speech_count = 0
                silence_count = 0
                voiced = []
                padding.clear()
