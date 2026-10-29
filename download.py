"""Girdi cozumleme: YouTube linki indirme (yt-dlp) veya yerel dosya kullanma. work/<video_id>/ altinda cache'ler."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from utils import console, die, sanitize_filename

WORK_DIR = Path("work")


@dataclass
class VideoInfo:
    video_id: str
    path: Path
    title: str
    work_dir: Path


def is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def _local_video_id(path: Path) -> str:
    abs_path = str(path.resolve())
    h = hashlib.md5(abs_path.encode("utf-8")).hexdigest()[:8]
    stem = sanitize_filename(path.stem, max_len=40)
    return f"{stem}-{h}"


def resolve_video(input_str: str) -> VideoInfo:
    if is_url(input_str):
        return _download_youtube(input_str)
    local_path = Path(input_str)
    if not local_path.exists():
        die(f"Yerel dosya bulunamadi: {input_str}")
    video_id = _local_video_id(local_path)
    work_dir = WORK_DIR / video_id
    work_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"[cyan]Yerel dosya kullaniliyor:[/cyan] {local_path} (id={video_id})")
    return VideoInfo(video_id=video_id, path=local_path, title=local_path.stem, work_dir=work_dir)


def _download_youtube(url: str) -> VideoInfo:
    import yt_dlp

    # Once sadece bilgi cek (indirme yapmadan) video_id ve baslik icin.
    probe_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(probe_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    video_id = info["id"]
    title = info.get("title", video_id)
    work_dir = WORK_DIR / video_id
    work_dir.mkdir(parents=True, exist_ok=True)
    target = work_dir / "source.mp4"

    if target.exists():
        console.print(f"[green]Cache'te bulundu, indirme atlaniyor:[/green] {target}")
        return VideoInfo(video_id=video_id, path=target, title=title, work_dir=work_dir)

    console.print(f"[cyan]Indiriliyor:[/cyan] {title} ({video_id})")
    download_opts = {
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best[height<=1080]",
        "merge_output_format": "mp4",
        "outtmpl": str(work_dir / "source.%(ext)s"),
        "quiet": False,
        "no_warnings": True,
        "noprogress": False,
    }
    with yt_dlp.YoutubeDL(download_opts) as ydl:
        ydl.download([url])

    if not target.exists():
        # ext mp4 olmayan bir sey indirilmis olabilir, bul ve yeniden adlandir gerekirse
        candidates = list(work_dir.glob("source.*"))
        video_candidates = [c for c in candidates if c.suffix.lower() in (".mp4", ".mkv", ".webm")]
        if not video_candidates:
            die(f"Indirme sonrasi video dosyasi bulunamadi: {work_dir}")
        target = video_candidates[0]

    return VideoInfo(video_id=video_id, path=target, title=title, work_dir=work_dir)
