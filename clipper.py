#!/usr/bin/env python
"""Uzun videodan TikTok/Shorts icin dikey klip ureten CLI araci.

Kullanim:
    python clipper.py <youtube_linki_veya_yerel_dosya> [--clips 10] [--min 25] [--max 60] [--lang auto]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Windows'ta eski konsol kod sayfalari (cp1252/cp850) Turkce/unicode karakterlerde
# UnicodeEncodeError firlatabilir; stdout/stderr'i UTF-8'e zorla.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from dotenv import load_dotenv
from rich.table import Table

from utils import check_api_key, check_ffmpeg, console, die, sanitize_filename

OUTPUT_DIR = Path("output")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Uzun videodan dikey klip uretici")
    parser.add_argument("input", help="YouTube linki veya yerel video dosyasi yolu")
    parser.add_argument("--clips", type=int, default=10, help="Uretilecek klip sayisi (varsayilan: 10)")
    parser.add_argument("--min", type=int, default=25, dest="min_dur", help="Min klip suresi saniye (varsayilan: 25)")
    parser.add_argument("--max", type=int, default=60, dest="max_dur", help="Max klip suresi saniye (varsayilan: 60)")
    parser.add_argument("--lang", type=str, default="auto", help="Transkript dili (tr, en, auto...)")
    parser.add_argument("--model", type=str, default="small", help="faster-whisper model boyutu")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    check_ffmpeg()
    api_key = check_api_key(os.environ.get("GEMINI_API_KEY"))

    from download import resolve_video
    from transcribe import transcribe_video
    from select_moments import select_moments
    from render import render_clip

    video = resolve_video(args.input)

    transcript = transcribe_video(
        video.path, video.work_dir, model_size=args.model, language=args.lang
    )

    flat_words = [
        {"word": w["word"], "start": w["start"], "end": w["end"]}
        for seg in transcript["segments"]
        for w in seg.get("words", [])
    ]

    clips = select_moments(
        transcript, api_key, num_clips=args.clips, min_dur=args.min_dur, max_dur=args.max_dur
    )

    if not clips:
        die("Uygun klip bulunamadi. Video suresi kisa olabilir veya Gemini yaniti alinamadi.")

    out_dir = OUTPUT_DIR / video.video_id
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = video.work_dir / "tmp"

    console.print(f"\n[bold cyan]{len(clips)} klip render ediliyor...[/bold cyan]\n")

    results = []
    for i, clip in enumerate(clips, start=1):
        title_slug = sanitize_filename(clip["title"])
        out_name = f"{i:02d}_{title_slug}.mp4"
        out_path = out_dir / out_name

        clip_words = [w for w in flat_words if w["end"] > clip["start"] and w["start"] < clip["end"]]

        console.print(f"[cyan]({i}/{len(clips)})[/cyan] Render ediliyor: {out_name} [{clip['duration']:.0f}s, skor={clip['score']}]")
        try:
            render_clip(video.path, clip, clip_words, out_path, tmp_dir)
            clip["file"] = out_name
            clip["order"] = i
            results.append(clip)
            console.print(f"  [green]OK[/green] -> {out_path}")
        except Exception as e:
            console.print(f"  [red]HATA, bu klip atlandi:[/red] {e}")
            continue

    clips_json_path = out_dir / "clips.json"
    with open(clips_json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    if not results:
        die("Hicbir klip basariyla render edilemedi.")

    table = Table(title=f"Klip Ozeti - {video.title}")
    table.add_column("Sira", justify="right")
    table.add_column("Dosya")
    table.add_column("Sure", justify="right")
    table.add_column("Skor", justify="right")
    table.add_column("Baslik")

    for c in results:
        table.add_row(str(c["order"]), c["file"], f"{c['duration']:.0f}s", str(c["score"]), c["title"])

    console.print("\n")
    console.print(table)
    console.print(f"\n[bold green]Tamamlandi.[/bold green] Ciktilar: {out_dir}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Iptal edildi.[/yellow]")
        sys.exit(1)
