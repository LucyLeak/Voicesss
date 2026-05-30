from __future__ import annotations

import multiprocessing as mp
import queue
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk
from typing import Literal

from .audio import InputDevice, MicrophoneVAD, list_input_devices
from .config import VoiceConfig
from .correction import SelfReferenceFeminizer
from .transcription import FasterWhisperTranscriber, pcm16_to_float32_audio

UiKind = Literal["append", "done", "error", "status"]


@dataclass(frozen=True, slots=True)
class UiEvent:
    kind: UiKind
    text: str


def _run_transcription_worker(
    events: mp.Queue,
    stop_event: mp.Event,
    device_index: int,
    model: str,
    device: str,
    compute_type: str,
    apply_correction: bool,
) -> None:
    try:
        config = VoiceConfig()
        feminizer = SelfReferenceFeminizer()
        events.put(UiEvent("status", f"Carregando modelo {model}..."))
        transcriber = FasterWhisperTranscriber(
            model=model,
            language=config.language,
            device=device,
            compute_type=compute_type,
            cpu_threads=config.cpu_threads,
            beam_size=config.beam_size,
            vad_filter=False,
        )
        microphone = MicrophoneVAD(
            device=device_index,
            sample_rate=config.sample_rate,
            frame_ms=config.frame_ms,
            aggressiveness=config.vad_aggressiveness,
            min_speech_ms=config.min_speech_ms,
            silence_ms=config.silence_ms,
            max_utterance_ms=config.max_utterance_ms,
        )

        events.put(UiEvent("status", "Escutando..."))
        for chunk in microphone.iter_utterances(stop_event=stop_event):
            if stop_event.is_set():
                break
            events.put(UiEvent("status", f"Transcrevendo... captura {chunk.sample_rate} Hz"))
            result = transcriber.transcribe(
                pcm16_to_float32_audio(chunk.pcm, source_sample_rate=chunk.sample_rate)
            )
            if result.text:
                text = feminizer.normalize(result.text) if apply_correction else result.text
                events.put(UiEvent("append", text))
            if not stop_event.is_set():
                events.put(UiEvent("status", "Escutando..."))
    except Exception as exc:
        events.put(UiEvent("error", str(exc)))
    finally:
        events.put(UiEvent("done", "Parado."))


class VoicesssApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Voicesss")
        self.geometry("820x560")
        self.minsize(680, 460)

        self.devices: list[InputDevice] = []
        self.compute_device_choices = self._compute_device_choices()
        self.worker: mp.Process | None = None
        self.stop_event: mp.Event | None = None
        self.events: mp.Queue = mp.Queue()
        self.force_stop_scheduled = False

        self.microphone_var = tk.StringVar()
        self.model_var = tk.StringVar(value=VoiceConfig.model)
        self.device_var = tk.StringVar(value=self._device_label_from_value(VoiceConfig.device))
        self.compute_type_var = tk.StringVar(value=VoiceConfig.compute_type)
        self.apply_correction_var = tk.BooleanVar(value=True)
        self.show_all_microphones_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Pronto.")

        self._build_ui()
        self._refresh_devices()
        self.after(100, self._drain_events)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        title = ttk.Label(self, text="Voicesss", font=("Segoe UI", 18, "bold"))
        title.grid(row=0, column=0, sticky="w", padx=16, pady=(14, 6))

        controls = ttk.Frame(self, padding=(16, 8))
        controls.grid(row=1, column=0, sticky="ew")
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(3, weight=0)

        ttk.Label(controls, text="Microfone").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.microphone_box = ttk.Combobox(
            controls,
            textvariable=self.microphone_var,
            state="readonly",
            width=48,
        )
        self.microphone_box.grid(row=0, column=1, columnspan=3, sticky="ew", pady=4)
        self.refresh_button = ttk.Button(controls, text="Atualizar", command=self._refresh_devices)
        self.refresh_button.grid(
            row=0, column=4, sticky="ew", padx=(8, 0), pady=4
        )
        self.show_all_check = ttk.Checkbutton(
            controls,
            text="Mostrar todos",
            variable=self.show_all_microphones_var,
            command=self._refresh_devices,
        )
        self.show_all_check.grid(row=0, column=5, sticky="w", padx=(8, 0), pady=4)

        ttk.Label(controls, text="Modelo").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.model_box = ttk.Combobox(
            controls,
            textvariable=self.model_var,
            state="readonly",
            values=("tiny", "base", "small", "medium", "large-v3"),
            width=14,
        )
        self.model_box.grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(controls, text="Dispositivo").grid(row=1, column=2, sticky="e", padx=(12, 8), pady=4)
        self.device_box = ttk.Combobox(
            controls,
            textvariable=self.device_var,
            state="readonly",
            values=tuple(self.compute_device_choices),
            width=18,
        )
        self.device_box.grid(row=1, column=3, sticky="w", pady=4)

        ttk.Label(controls, text="Precisao").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        self.compute_type_box = ttk.Combobox(
            controls,
            textvariable=self.compute_type_var,
            state="readonly",
            values=("int8", "float16", "float32"),
            width=14,
        )
        self.compute_type_box.grid(row=2, column=1, sticky="w", pady=4)

        self.correction_check = ttk.Checkbutton(
            controls,
            text="Feminino",
            variable=self.apply_correction_var,
        )
        self.correction_check.grid(row=2, column=2, sticky="e", padx=(12, 8), pady=4)

        buttons = ttk.Frame(controls)
        buttons.grid(row=2, column=3, columnspan=2, sticky="e", pady=4)
        self.start_button = ttk.Button(buttons, text="Iniciar", command=self._start)
        self.start_button.grid(row=0, column=0, padx=(0, 8))
        self.stop_button = ttk.Button(buttons, text="Parar", command=self._stop, state="disabled")
        self.stop_button.grid(row=0, column=1)

        transcript_frame = ttk.Frame(self, padding=(16, 8))
        transcript_frame.grid(row=2, column=0, sticky="nsew")
        transcript_frame.columnconfigure(0, weight=1)
        transcript_frame.rowconfigure(0, weight=1)

        self.transcript = tk.Text(
            transcript_frame,
            wrap="word",
            undo=True,
            font=("Segoe UI", 11),
            padx=10,
            pady=10,
            height=12,
        )
        self.transcript.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(transcript_frame, orient="vertical", command=self.transcript.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.transcript.configure(yscrollcommand=scrollbar.set)

        bottom = ttk.Frame(self, padding=(16, 8, 16, 14))
        bottom.grid(row=3, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        ttk.Label(bottom, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        ttk.Button(bottom, text="Limpar", command=self._clear_transcript).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(bottom, text="Copiar", command=self._copy_transcript).grid(row=0, column=2, padx=(8, 0))

    def _refresh_devices(self) -> None:
        previous_device = self._selected_device()
        previous_key = previous_device.stable_key if previous_device else None
        try:
            self.devices = list_input_devices(
                include_all=self.show_all_microphones_var.get(),
                refresh=True,
            )
        except RuntimeError as exc:
            self.devices = []
            self.microphone_box.configure(values=())
            self.microphone_var.set("")
            self.status_var.set(str(exc))
            return

        labels = [self._device_label(device) for device in self.devices]
        self.microphone_box.configure(values=labels)
        if labels:
            selected = self._pick_device_after_refresh(previous_key)
            self.microphone_var.set(self._device_label(selected))
            mode = "todos" if self.show_all_microphones_var.get() else "recomendados"
            self.status_var.set(f"{len(labels)} microfone(s) {mode}. Selecionado: {selected.name}.")
        else:
            self.microphone_var.set("")
            self.status_var.set("Nenhum microfone encontrado.")

    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return

        selected_device = self._selected_device()
        if selected_device is None:
            messagebox.showwarning("Voicesss", "Selecione um microfone antes de iniciar.")
            return

        self.stop_event = mp.Event()
        self.force_stop_scheduled = False
        self._set_running(True)
        self.status_var.set("Iniciando processo de transcricao...")
        self.worker = mp.Process(
            target=_run_transcription_worker,
            args=(
                self.events,
                self.stop_event,
                selected_device.index,
                self.model_var.get(),
                self._selected_compute_device(),
                self.compute_type_var.get(),
                self.apply_correction_var.get(),
            ),
            daemon=True,
        )
        self.worker.start()

    def _stop(self) -> None:
        if self.stop_event is not None:
            self.stop_event.set()
            self.status_var.set("Parando...")
        self.stop_button.configure(text="Forcar", state="normal", command=self._force_stop)
        if not self.force_stop_scheduled:
            self.force_stop_scheduled = True
            self.after(1500, self._force_stop_if_needed)

    def _force_stop_if_needed(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            self._force_stop()

    def _force_stop(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            self.worker.terminate()
            self.worker.join(timeout=1)
            if self.worker.is_alive():
                self.worker.kill()
                self.worker.join(timeout=1)
        self.events.put(UiEvent("done", "Parado a forca."))

    def _drain_events(self) -> None:
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break

            if event.kind == "append":
                self.transcript.insert("end", event.text + "\n")
                self.transcript.see("end")
            elif event.kind == "status":
                self.status_var.set(event.text)
            elif event.kind == "error":
                self.status_var.set("Erro.")
                messagebox.showerror("Voicesss", event.text)
            elif event.kind == "done":
                self.status_var.set(event.text)
                self._set_running(False)
                self._cleanup_worker()

        self.after(100, self._drain_events)

    def _set_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        readonly_state = "disabled" if running else "readonly"
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        self.stop_button.configure(text="Parar", command=self._stop)
        self.refresh_button.configure(state=state)
        self.microphone_box.configure(state=readonly_state)
        self.model_box.configure(state=readonly_state)
        self.device_box.configure(state=readonly_state)
        self.compute_type_box.configure(state=readonly_state)
        self.correction_check.configure(state=state)
        self.show_all_check.configure(state=state)

    def _selected_device(self) -> InputDevice | None:
        selected = self.microphone_var.get()
        for device in self.devices:
            if self._device_label(device) == selected:
                return device
        return None

    def _pick_device_after_refresh(self, previous_key: str | None) -> InputDevice:
        if previous_key is not None:
            for device in self.devices:
                if device.stable_key == previous_key:
                    return device
        for device in self.devices:
            if device.is_default:
                return device
        return self.devices[0]

    @staticmethod
    def _device_label(device: InputDevice) -> str:
        details = [device.host_api] if device.host_api else []
        if device.is_default:
            details.append("padrao")
        suffix = f" ({', '.join(details)})" if details else ""
        return f"{device.index} - {device.name}{suffix}"

    @staticmethod
    def _compute_device_choices() -> dict[str, str]:
        choices = {"CPU (AMD/Intel)": "cpu"}
        try:
            import ctranslate2

            ctranslate2.get_supported_compute_types("cuda")
        except Exception:
            return choices

        choices["CUDA (NVIDIA)"] = "cuda"
        return choices

    def _device_label_from_value(self, value: str) -> str:
        for label, device in self.compute_device_choices.items():
            if device == value:
                return label
        return next(iter(self.compute_device_choices))

    def _selected_compute_device(self) -> str:
        return self.compute_device_choices.get(self.device_var.get(), "cpu")

    def _cleanup_worker(self) -> None:
        if self.worker is not None and not self.worker.is_alive():
            self.worker.join(timeout=0.1)
            self.worker = None
        self.stop_event = None
        self.force_stop_scheduled = False

    def _clear_transcript(self) -> None:
        self.transcript.delete("1.0", "end")

    def _copy_transcript(self) -> None:
        text = self.transcript.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("Texto copiado.")

    def _on_close(self) -> None:
        if self.stop_event is not None:
            self.stop_event.set()
        if self.worker is not None and self.worker.is_alive():
            self.worker.terminate()
            self.worker.join(timeout=1)
            if self.worker.is_alive():
                self.worker.kill()
        self.destroy()


def main() -> None:
    mp.freeze_support()
    app = VoicesssApp()
    app.protocol("WM_DELETE_WINDOW", app._on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
