"""faster-whisper ile kelime seviyesinde zaman damgali transkript. GPU varsa otomatik kullanir."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from utils import console


def _add_nvidia_dll_dirs() -> None:
    """pip ile kurulan nvidia-cublas-cu12/nvidia-cudnn-cu12 DLL'leri Windows'ta PATH'e
    otomatik eklenmiyor; ctranslate2 import edilmeden once elle eklememiz gerekiyor."""
    if sys.platform != "win32":
        return
    import importlib.util

    spec = importlib.util.find_spec("nvidia")
    if spec is None or not spec.submodule_search_locations:
        return
    base = Path(next(iter(spec.submodule_search_locations)))
    found_dirs: list[str] = []
    for sub in ("cublas", "cudnn", "cuda_nvrtc"):
        bin_dir = base / sub / "bin"
        if bin_dir.is_dir():
            found_dirs.append(str(bin_dir))
            try:
                os.add_dll_directory(str(bin_dir))
            except OSError:
                pass
    if found_dirs:
        # ctranslate2'nin ctranslate2.pyd'si cuBLAS/cuDNN'i lazy-load ederken
        # add_dll_directory'yi yeterince guvenmiyor gibi gorunuyor; klasik PATH
        # tabanli DLL aramasi (LoadLibrary'nin varsayilan davranisi) gercekten
        # calisan yontem oldu - test ederek dogrulandi.
        os.environ["PATH"] = os.pathsep.join(found_dirs) + os.pathsep + os.environ.get("PATH", "")


_add_nvidia_dll_dirs()


def _detect_device() -> tuple[str, str]:
    """(device, compute_type) dondurur. CUDA calisiyorsa GPU float16, yoksa CPU int8."""
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def _run_transcription(
    video_path: Path, model_size: str, language: str, device: str, compute_type: str
) -> tuple[list[dict[str, Any]], Any]:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    lang_arg = None if language == "auto" else language

    segments_iter, info = model.transcribe(
        str(video_path),
        language=lang_arg,
        word_timestamps=True,
        vad_filter=True,
    )

    segments: list[dict[str, Any]] = []
    with Progress(
        SpinnerColumn(spinner_name="line"),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Transkript isleniyor...", total=None)
        for seg in segments_iter:
            words = [
                {"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
                for w in (seg.words or [])
            ]
            segments.append(
                {
                    "id": seg.id,
                    "start": round(seg.start, 3),
                    "end": round(seg.end, 3),
                    "text": seg.text.strip(),
                    "words": words,
                }
            )
            progress.update(task, description=f"Transkript isleniyor... ({seg.end:.0f}s)")

    return segments, info


def transcribe_video(
    video_path: Path,
    work_dir: Path,
    model_size: str = "small",
    language: str = "auto",
) -> dict[str, Any]:
    transcript_path = work_dir / "transcript.json"
    if transcript_path.exists():
        console.print(f"[green]Transkript cache'te bulundu:[/green] {transcript_path}")
        with open(transcript_path, "r", encoding="utf-8") as f:
            return json.load(f)

    device, compute_type = _detect_device()
    console.print(f"[cyan]Transkript cikartiliyor[/cyan] (model={model_size}, device={device}, compute={compute_type})")

    try:
        segments, info = _run_transcription(video_path, model_size, language, device, compute_type)
    except Exception as e:
        if device == "cuda":
            console.print(
                f"[yellow]CUDA ile transkript basarisiz oldu ({e}), CPU'ya (int8) geciliyor...[/yellow]"
            )
            device, compute_type = "cpu", "int8"
            segments, info = _run_transcription(video_path, model_size, language, device, compute_type)
        else:
            raise

    transcript = {
        "language": info.language,
        "duration": info.duration,
        "segments": segments,
    }

    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, ensure_ascii=False, indent=2)

    console.print(f"[green]Transkript kaydedildi:[/green] {transcript_path} ({len(segments)} segment)")
    return transcript
