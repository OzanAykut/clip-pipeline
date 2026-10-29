"""We The Studios kampanyasina ozel son adimlar: zorunlu network bug ve bumper."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from render import add_headline_overlay, add_pattern_interrupts, render_clip

WTS_DIR = Path("work") / "wts"
BUG_PATH = WTS_DIR / "WTS_NetworkBug_White.png"
BUMPER_PATH = WTS_DIR / "9x16_WTS_BUMPER_May_2026.mp4"

# WTS Bug Standard v1 (1080x1920): merkez 871,431. Referans gorselde logo 248px genis.
BUG_WIDTH = 248
BUG_CENTER = (871, 431)


def _run(cmd: list[str], what: str) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg {what} basarisiz\n{result.stderr[-2000:]}")


def add_wts_bug(in_path: Path, out_path: Path) -> None:
    bug_h = round(BUG_WIDTH * 402 / 1200)
    x = BUG_CENTER[0] - BUG_WIDTH // 2
    y = BUG_CENTER[1] - bug_h // 2
    _run([
        "ffmpeg", "-y", "-i", str(in_path), "-i", str(BUG_PATH),
        "-filter_complex", f"[1:v]scale={BUG_WIDTH}:{bug_h}[bug];[0:v][bug]overlay={x}:{y}[v]",
        "-map", "[v]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "copy",
        str(out_path),
    ], "wts bug")


def append_bumper(in_path: Path, out_path: Path) -> None:
    """Bumper'i oldugu gibi (kesme, hiz ya da renk degisikligi olmadan) sona ekler.
    Sadece birlestirmek icin 1080x1920'ye olceklenir."""
    fc = (
        "[0:v]scale=1080:1920,fps=30,setsar=1[v0];"
        "[1:v]scale=1080:1920:flags=lanczos,fps=30,setsar=1[v1];"
        "[0:a]aresample=48000,aformat=channel_layouts=stereo[a0];"
        "[1:a]aresample=48000,aformat=channel_layouts=stereo[a1];"
        "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
    )
    _run([
        "ffmpeg", "-y", "-i", str(in_path), "-i", str(BUMPER_PATH),
        "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        str(out_path),
    ], "bumper")


HEADLINE_SECONDS = 3.0


def _fix_word(w: dict, name_fixes: dict[str, str]) -> dict:
    core = re.sub(r"[^\w']", "", w["word"])
    fixed = name_fixes.get(core.lower())
    if not fixed:
        return w
    return {**w, "word": w["word"].replace(core, fixed)}


def _concat(parts: list[Path], out_path: Path) -> None:
    if len(parts) == 1:
        parts[0].replace(out_path)
        return
    inputs = []
    for p in parts:
        inputs += ["-i", str(p)]
    streams = "".join(f"[{i}:v][{i}:a]" for i in range(len(parts)))
    _run([
        "ffmpeg", "-y", *inputs,
        "-filter_complex", f"{streams}concat=n={len(parts)}:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ], "concat")


def render_wts_clips(
    source: Path,
    transcript_path: Path,
    work: Path,
    clips: list[dict],
    name_fixes: dict[str, str],
    out_dir: Path = Path("output/campaigns"),
) -> None:
    """Her klip: segmentleri (flash-forward icin sirali birden fazla olabilir) yuz takipli
    kirp + altyazi + zoom, birlestir, ilk 3 sn baslik, WTS bug, sonda bumper."""
    transcript = json.load(open(transcript_path, encoding="utf-8"))
    words = [_fix_word({"word": w["word"], "start": w["start"], "end": w["end"]}, name_fixes)
             for s in transcript["segments"] for w in s.get("words", [])]
    work.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    for clip in clips:
        print(f"\n== {clip['name']}", flush=True)
        parts = []
        for j, (start, end) in enumerate(clip["segments"]):
            seg_words = [w for w in words if w["end"] > start and w["start"] < end]
            seg = {"name": f"{clip['name']}_{j}", "start": start, "end": end,
                   "hook_words": clip["hook_words"], "split": False}
            base = work / f"{clip['name']}_{j}_base.mp4"
            punch = work / f"{clip['name']}_{j}_punch.mp4"
            render_clip(source, seg, seg_words, base, work / "tmp")
            add_pattern_interrupts(base, clip["hook_words"], seg_words, start, end, punch)
            base.unlink(missing_ok=True)
            parts.append(punch)
            print(f"  segment {j} OK ({end - start:.1f}s)", flush=True)

        joined = work / f"{clip['name']}_joined.mp4"
        headlined = work / f"{clip['name']}_headline.mp4"
        bugged = work / f"{clip['name']}_bug.mp4"
        final = out_dir / f"wts_{clip['name']}.mp4"
        _concat(parts, joined)
        add_headline_overlay(joined, clip["headline"], headlined, work / "tmp", display_seconds=HEADLINE_SECONDS)
        add_wts_bug(headlined, bugged)
        append_bumper(bugged, final)
        for p in parts + [joined, headlined, bugged]:
            p.unlink(missing_ok=True)
        print(f"  OK -> {final}", flush=True)
