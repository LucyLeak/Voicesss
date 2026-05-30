from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .audio import MicrophoneVAD, list_input_devices
from .config import VoiceConfig
from .correction import SelfReferenceFeminizer
from .rocm import check_rocm
from .transcription import FasterWhisperTranscriber, pcm16_to_float32_audio

app = typer.Typer(
    help="Detector de voz e transcritor em portugues com auto-referencias no feminino.",
    no_args_is_help=True,
)
console = Console()


def _build_feminizer(lexicon: Optional[Path]) -> SelfReferenceFeminizer:
    return SelfReferenceFeminizer.from_json(lexicon)


def _append_output(path: Optional[Path], text: str) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(text + "\n")


def _build_transcriber(
    *,
    model: str,
    language: str,
    device: str,
    compute_type: str,
    cpu_threads: int,
    beam_size: int,
    vad_filter: bool,
) -> FasterWhisperTranscriber:
    return FasterWhisperTranscriber(
        model=model,
        language=language,
        device=device,
        compute_type=compute_type,
        cpu_threads=cpu_threads,
        beam_size=beam_size,
        vad_filter=vad_filter,
    )


@app.command("normalize")
def normalize_text(
    text: str = typer.Argument(..., help="Texto a normalizar."),
    lexicon: Optional[Path] = typer.Option(None, "--lexicon", "-l", help="JSON com termos personalizados."),
) -> None:
    """Aplica apenas a normalizacao feminina, sem transcrever audio."""

    feminizer = _build_feminizer(lexicon)
    console.print(feminizer.normalize(text))


@app.command("devices")
def devices(
    show_all: bool = typer.Option(False, "--all", help="Mostrar tambem APIs antigas e dispositivos virtuais."),
) -> None:
    """Lista microfones disponiveis para captura."""

    title = "Microfones" if show_all else "Microfones recomendados"
    table = Table(title=title)
    table.add_column("Indice", justify="right")
    table.add_column("Nome")
    table.add_column("API")
    table.add_column("Canais", justify="right")
    table.add_column("Hz padrao", justify="right")
    table.add_column("Padrao", justify="center")
    for device in list_input_devices(include_all=show_all, refresh=True):
        table.add_row(
            str(device.index),
            device.name,
            device.host_api,
            str(device.channels),
            str(device.default_sample_rate),
            "sim" if device.is_default else "",
        )
    console.print(table)


@app.command("rocm")
def rocm() -> None:
    """Verifica ROCm/HIP e suporte do motor de transcricao."""

    status = check_rocm()
    table = Table(title="Diagnostico ROCm")
    table.add_column("Item")
    table.add_column("Valor")
    table.add_row("hipcc", status.hipcc or "nao encontrado")
    table.add_row("HIP runtime DLL", status.hip_runtime_dll or "nao encontrada")
    table.add_row("HIP runtime OK", "sim" if status.hip_runtime_available else "nao")
    if status.hip_runtime_error:
        table.add_row("HIP erro", status.hip_runtime_error)
    table.add_row("HIP runtime version", str(status.hip_runtime_version or "desconhecida"))
    table.add_row("HIP driver version", str(status.hip_driver_version or "desconhecida"))
    table.add_row("HIP device count", str(status.hip_device_count if status.hip_device_count is not None else "desconhecido"))
    table.add_row("CTranslate2", status.ctranslate2_version or "nao instalado")
    table.add_row("CTranslate2 ROCm", "sim" if status.ctranslate2_rocm_supported else "nao")
    if status.ctranslate2_rocm_error:
        table.add_row("CTranslate2 ROCm erro", status.ctranslate2_rocm_error)
    console.print(table)

    if status.hip_runtime_available and status.hip_device_count:
        console.print("[green]ROCm/HIP esta visivel para este processo Python.[/green]")
    else:
        console.print("[yellow]ROCm/HIP nao esta pronto para este processo Python.[/yellow]")

    if not status.ctranslate2_rocm_supported:
        console.print(
            "[yellow]O motor atual do Voicesss usa faster-whisper/CTranslate2 de PyPI, "
            "que aqui nao expõe dispositivo ROCm. Use CPU neste app.[/yellow]"
        )


@app.command("file")
def transcribe_file(
    audio_path: Path = typer.Argument(..., exists=True, dir_okay=False, help="Arquivo de audio."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Arquivo para acrescentar a transcricao."),
    lexicon: Optional[Path] = typer.Option(None, "--lexicon", "-l", help="JSON com termos personalizados."),
    model: str = typer.Option(VoiceConfig.model, "--model", "-m", help="Modelo faster-whisper."),
    language: str = typer.Option(VoiceConfig.language, "--language", help="Idioma esperado."),
    device: str = typer.Option(VoiceConfig.device, "--device", help="cpu ou cuda (NVIDIA)."),
    compute_type: str = typer.Option(VoiceConfig.compute_type, "--compute-type", help="int8, float16, float32..."),
    cpu_threads: int = typer.Option(VoiceConfig.cpu_threads, "--cpu-threads", min=1, help="Threads usadas em CPU."),
    beam_size: int = typer.Option(VoiceConfig.beam_size, "--beam-size", min=1, max=10, help="Busca do decodificador."),
    no_correction: bool = typer.Option(False, "--no-correction", help="Nao aplicar normalizacao feminina."),
    show_raw: bool = typer.Option(False, "--show-raw", help="Mostrar tambem a transcricao original."),
) -> None:
    """Transcreve um arquivo de audio."""

    transcriber = _build_transcriber(
        model=model,
        language=language,
        device=device,
        compute_type=compute_type,
        cpu_threads=cpu_threads,
        beam_size=beam_size,
        vad_filter=True,
    )
    result = transcriber.transcribe(audio_path)
    text = result.text
    corrected = text if no_correction else _build_feminizer(lexicon).normalize(text)

    if show_raw and corrected != text:
        console.print("[dim]Original:[/dim]", text)
    console.print(corrected)
    _append_output(output, corrected)


@app.command("listen")
def listen(
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Arquivo para acrescentar as transcricoes."),
    lexicon: Optional[Path] = typer.Option(None, "--lexicon", "-l", help="JSON com termos personalizados."),
    input_device: Optional[int] = typer.Option(None, "--input-device", "-i", help="Indice do microfone."),
    model: str = typer.Option(VoiceConfig.model, "--model", "-m", help="Modelo faster-whisper."),
    language: str = typer.Option(VoiceConfig.language, "--language", help="Idioma esperado."),
    device: str = typer.Option(VoiceConfig.device, "--device", help="cpu ou cuda (NVIDIA)."),
    compute_type: str = typer.Option(VoiceConfig.compute_type, "--compute-type", help="int8, float16, float32..."),
    cpu_threads: int = typer.Option(VoiceConfig.cpu_threads, "--cpu-threads", min=1, help="Threads usadas em CPU."),
    beam_size: int = typer.Option(VoiceConfig.beam_size, "--beam-size", min=1, max=10, help="Busca do decodificador."),
    vad_aggressiveness: int = typer.Option(
        VoiceConfig.vad_aggressiveness,
        "--vad",
        min=0,
        max=3,
        help="Sensibilidade do detector de voz: 0 permissivo, 3 agressivo.",
    ),
    once: bool = typer.Option(False, "--once", help="Transcrever apenas a primeira fala detectada."),
    no_correction: bool = typer.Option(False, "--no-correction", help="Nao aplicar normalizacao feminina."),
) -> None:
    """Escuta o microfone, detecta fala e transcreve cada trecho."""

    config = VoiceConfig(vad_aggressiveness=vad_aggressiveness)
    transcriber = _build_transcriber(
        model=model,
        language=language,
        device=device,
        compute_type=compute_type,
        cpu_threads=cpu_threads,
        beam_size=beam_size,
        vad_filter=False,
    )
    feminizer = _build_feminizer(lexicon)
    microphone = MicrophoneVAD(
        device=input_device,
        sample_rate=config.sample_rate,
        frame_ms=config.frame_ms,
        aggressiveness=config.vad_aggressiveness,
        min_speech_ms=config.min_speech_ms,
        silence_ms=config.silence_ms,
        max_utterance_ms=config.max_utterance_ms,
    )

    console.print("[bold]Escutando...[/bold] fale e pause para transcrever. Ctrl+C para sair.")
    try:
        for chunk in microphone.iter_utterances():
            audio = pcm16_to_float32_audio(chunk.pcm, source_sample_rate=chunk.sample_rate)
            result = transcriber.transcribe(audio)
            if not result.text:
                continue

            corrected = result.text if no_correction else feminizer.normalize(result.text)
            console.print(corrected)
            _append_output(output, corrected)
            if once:
                break
    except KeyboardInterrupt:
        console.print("\n[dim]Encerrado.[/dim]")
