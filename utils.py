"""Ortak yardımcı fonksiyonlar: ortam kontrolü, path escape, sanitize, subprocess."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from rich.console import Console

# legacy_windows=False: eski Windows konsollarindaki unicode/charmap crash'lerini
# onlemek icin ANSI render moduna zorlar (Windows 10/11'de varsayilan konsollar destekler).
console = Console(legacy_windows=False)


def die(message: str) -> None:
    console.print(f"[bold red]HATA:[/bold red] {message}")
    sys.exit(1)


def check_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        die(
            "ffmpeg/ffprobe bulunamadi. Windows'ta kurmak icin:\n"
            "  winget install --id Gyan.FFmpeg -e\n"
            "Kurduktan sonra yeni bir terminal acip tekrar deneyin."
        )


def check_api_key(api_key: str | None) -> str:
    if not api_key:
        die(
            "GEMINI_API_KEY bulunamadi. Proje kokune bir .env dosyasi olusturup\n"
            "  GEMINI_API_KEY=xxxx\n"
            "satirini ekleyin (.env.example dosyasina bakin)."
        )
    return api_key  # type: ignore[return-value]


def sanitize_filename(text: str, max_len: int = 60) -> str:
    text = text.strip().lower()
    # Turkce karakterleri sadelestir
    tr_map = str.maketrans("çğıöşü", "cgiosu")
    text = text.translate(tr_map)
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text).strip("-")
    text = re.sub(r"-+", "-", text)
    return text[:max_len] or "klip"


def ffmpeg_path_escape(path: str | Path) -> str:
    """ffmpeg filtergraph icinde (subtitles= gibi) kullanilacak path'i hazirlar.

    Windows'ta mutlak yol kullanmak surucu harfinden sonra gelen ':' yuzunden
    ffmpeg'in filtergraph parser'ini kirar (bilinen bir Windows/ffmpeg sorunu).
    Bunu tamamen atlatmak icin path'i calisma dizinine (cwd) GORE RELATIF hale
    getiriyoruz; boylece ':' hic gorunmuyor. Ayni surucude degilse (nadir durum)
    mutlak yola duser.
    """
    p = Path(path)
    try:
        rel = Path(os.path.relpath(p, Path.cwd()))
        return str(rel).replace("\\", "/")
    except ValueError:
        return str(p.resolve()).replace("\\", "/")


def run_subprocess(cmd: list[str], desc: str = "") -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(
            f"Komut basarisiz ({desc}): {' '.join(cmd[:3])}...\n"
            f"stderr (son 2000 karakter):\n{result.stderr[-2000:]}"
        )
    return result


def ffprobe_duration(path: str | Path) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ]
    result = run_subprocess(cmd, "ffprobe duration")
    return float(result.stdout.strip())


def ffprobe_resolution(path: str | Path) -> tuple[int, int]:
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0", str(path),
    ]
    result = run_subprocess(cmd, "ffprobe resolution")
    w, h = result.stdout.strip().split("x")
    return int(w), int(h)


def ffprobe_audio_samplerate(path: str | Path) -> int:
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=sample_rate",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ]
    result = run_subprocess(cmd, "ffprobe sample rate")
    return int(result.stdout.strip())
