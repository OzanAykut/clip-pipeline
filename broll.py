"""Pexels'ten gercek stok B-roll (once dikey video, yoksa dikey foto) ve iki gosterim modu:
  - full: 1.5-2 sn tam ekran kesit, hafif yakinlasma (izleyici icin net bir 'gorsel an')
  - pip:  kosede kucuk yuvarlatilmis kart, beyaz cerceve + golge (izlemeyi bolmez)
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFilter

from utils import console

W, H, FPS = 1080, 1920, 30
PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
PEXELS_PHOTO_URL = "https://api.pexels.com/v1/search"
CACHE = Path("work") / "broll_cache"

FULL_ZOOM = 0.08  # tam ekran kesitte toplam yakinlasma
PIP_SIZE = 380
PIP_BORDER = 10
PIP_RADIUS = 36
PIP_SHADOW = 22


def _key() -> str | None:
    load_dotenv()
    return os.environ.get("PEXELS_API_KEY")


def _slug(q: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in q.lower())[:50]


def fetch_broll(query: str) -> Path | None:
    """Dikey stok video (tercih) ya da dikey foto indirir, onbellege alir."""
    key = _key()
    if not key:
        console.print("[yellow]PEXELS_API_KEY yok, B-roll atlanacak.[/yellow]")
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    for ext in (".mp4", ".jpg"):
        cached = CACHE / f"{_slug(query)}{ext}"
        if cached.exists():
            return cached
    try:
        r = requests.get(PEXELS_VIDEO_URL, headers={"Authorization": key}, timeout=15,
                         params={"query": query, "orientation": "portrait", "per_page": 5})
        r.raise_for_status()
        for v in r.json().get("videos", []):
            if v.get("duration", 0) < 3:
                continue
            files = [f for f in v["video_files"] if f.get("file_type") == "video/mp4"
                     and f.get("height", 0) >= 1280 and f.get("height", 0) > f.get("width", 0)]
            if not files:
                continue
            best = min(files, key=lambda f: abs(f["height"] - 1920))
            out = CACHE / f"{_slug(query)}.mp4"
            out.write_bytes(requests.get(best["link"], timeout=60).content)
            return out
        r = requests.get(PEXELS_PHOTO_URL, headers={"Authorization": key}, timeout=15,
                         params={"query": query, "orientation": "portrait", "per_page": 1})
        r.raise_for_status()
        photos = r.json().get("photos", [])
        if photos:
            out = CACHE / f"{_slug(query)}.jpg"
            out.write_bytes(requests.get(photos[0]["src"]["large2x"], timeout=30).content)
            return out
    except Exception as e:
        console.print(f"[yellow]Pexels hatasi ({query}): {e}[/yellow]")
    return None


def _input_args(src: Path, dur: float) -> list[str]:
    if src.suffix.lower() == ".jpg":
        return ["-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", str(src)]
    return ["-ss", "1.0", "-t", f"{dur:.3f}", "-i", str(src)]


def _run(cmd: list[str], what: str) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg {what} basarisiz\n{r.stderr[-2000:]}")


def prepare_full(src: Path, dur: float, out: Path) -> None:
    """Tam ekran 1080x1920 kesit, sure boyunca yavasca yakinlasir."""
    z = f"(1+{FULL_ZOOM}*t/{dur:.3f})"
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        f"scale=w='trunc({W}*{z}/2)*2':h='trunc({H}*{z}/2)*2':eval=frame,crop={W}:{H},"
        f"fps={FPS},setsar=1,format=yuv420p"
    )
    _run(["ffmpeg", "-y", *_input_args(src, dur), "-vf", vf, "-an", "-frames:v", str(round(dur * FPS)),
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", str(out)], "broll full")


def _pip_mask(tmp: Path) -> tuple[Path, Path]:
    """Yuvarlatilmis kose maskesi ve cerceve+golge katmani."""
    mask = tmp / "pip_mask.png"
    frame = tmp / "pip_frame.png"
    inner = PIP_SIZE - PIP_BORDER * 2
    m = Image.new("L", (inner, inner), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, inner - 1, inner - 1), PIP_RADIUS - PIP_BORDER, fill=255)
    m.save(mask)
    full = PIP_SIZE + PIP_SHADOW * 2
    f = Image.new("RGBA", (full, full), (0, 0, 0, 0))
    sh = Image.new("RGBA", (full, full), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((PIP_SHADOW, PIP_SHADOW + 8, PIP_SHADOW + PIP_SIZE, PIP_SHADOW + PIP_SIZE + 8),
                                         PIP_RADIUS, fill=(0, 0, 0, 140))
    f = Image.alpha_composite(f, sh.filter(ImageFilter.GaussianBlur(10)))
    ImageDraw.Draw(f).rounded_rectangle((PIP_SHADOW, PIP_SHADOW, PIP_SHADOW + PIP_SIZE, PIP_SHADOW + PIP_SIZE),
                                        PIP_RADIUS, fill=(255, 255, 255, 255))
    f.save(frame)
    return mask, frame


def prepare_pip(src: Path, dur: float, out: Path, tmp: Path) -> None:
    """Seffaf arka planli kart (png-in-mov, alfa kanalli): golge + beyaz cerceve + yuvarlak kose video."""
    mask, frame = _pip_mask(tmp)
    inner = PIP_SIZE - PIP_BORDER * 2
    off = PIP_SHADOW + PIP_BORDER
    fc = (
        f"[0:v]scale={inner}:{inner}:force_original_aspect_ratio=increase,crop={inner}:{inner},fps={FPS},format=rgba[v];"
        f"[1:v]format=gray[m];[v][m]alphamerge[r];"
        f"[2:v]format=rgba[f];[f][r]overlay={off}:{off}:shortest=1,"
        f"fade=t=in:st=0:d=0.15:alpha=1,fade=t=out:st={dur - 0.15:.3f}:d=0.15:alpha=1[o]"
    )
    _run(["ffmpeg", "-y", *_input_args(src, dur), "-loop", "1", "-i", str(mask), "-loop", "1", "-i", str(frame),
          "-filter_complex", fc, "-map", "[o]", "-frames:v", str(round(dur * FPS)), "-an",
          "-c:v", "png", str(out)], "broll pip")


