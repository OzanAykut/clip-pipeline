"""Sinematik motivasyon formati: siyah zemin, ortada 16:9 bant (soluk renk, yavas push-in, gren), ustte serif baslik,
altta cumle cumle serif altyazi (anahtar kelimeler altin), ortada yatay B-roll montaji, sonda siyah ekranda kapanis cumlesi.

  python motiv_cinematic.py <spec.json>
spec: {"src", "words", "out", "title", "subtitle", "keywords": [...], "broll": [{"at", "dur", "query"}],
       "music", "music_volume", "outro": "Call your mom.", "outro_seconds": 2.5}
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv()

W, H, FPS = 1080, 1920, 30
BAND_H = 608                       # 1080 genislikte 16:9
BAND_Y = (H - BAND_H) // 2 - 40    # biraz yukarida; alt tarafta altyazi icin yer
CACHE = Path("work/broll_cache_landscape")
FONT_DIR = "C:/Windows/Fonts"
GRADE = "eq=saturation=0.55:contrast=1.06:brightness=-0.02"


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise SystemExit(r.stderr[-1500:])


def duration(p: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True).stdout.strip())


def fetch_landscape(query: str) -> Path | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / (re.sub(r"[^a-z0-9]+", "_", query.lower()).strip("_") + ".mp4")
    if out.exists():
        return out
    r = requests.get("https://api.pexels.com/videos/search", headers={"Authorization": os.environ["PEXELS_API_KEY"]},
                     params={"query": query, "orientation": "landscape", "per_page": 8, "size": "medium"}, timeout=20)
    for v in r.json().get("videos", []):
        files = sorted([f for f in v["video_files"] if f.get("width") and f["width"] >= 1280 and f["width"] <= 2560],
                       key=lambda f: f["width"])
        if files and v.get("duration", 0) >= 3:
            out.write_bytes(requests.get(files[0]["link"], timeout=60).content)
            print(f"  broll '{query}' -> pexels {v['id']}")
            return out
    print(f"  broll '{query}' bulunamadi")
    return None


def ass_time(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def phrases(words: list[dict], max_words: int = 5) -> list[tuple[float, float, list[str]]]:
    out, cur = [], []
    for w in words:
        cur.append(w)
        txt = w["word"]
        if len(cur) >= max_words or txt.endswith((".", ",", "?", "!")) and len(cur) >= 2:
            out.append((cur[0]["start"], cur[-1]["end"], [x["word"] for x in cur]))
            cur = []
    if cur:
        out.append((cur[0]["start"], cur[-1]["end"], [x["word"] for x in cur]))
    # bosluklari kapat: bir sonraki cumleye kadar ekranda kalsin (en fazla 0.6 sn)
    fixed = []
    for i, (a, b, ws) in enumerate(out):
        nxt = out[i + 1][0] if i + 1 < len(out) else b + 0.6
        fixed.append((a, min(nxt, b + 0.6), ws))
    return fixed


def write_ass(spec: dict, words: list[dict], total: float, speech_end: float, path: Path) -> None:
    kw = [k.lower() for k in spec.get("keywords", [])]
    gold = r"{\c&H4FC6F2&\i1}"
    title_y = BAND_Y - 70
    cap_y = BAND_Y + BAND_H + 150
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,Georgia,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,2,70,70,0,1
Style: Sub,Georgia,36,&H00B4B4B4,&H00FFFFFF,&H00000000,&H00000000,0,1,0,0,100,100,2,0,1,0,0,2,70,70,0,1
Style: Cap,Georgia,62,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,0,3,8,80,80,0,1
Style: Outro,Georgia,84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,1,0,0,100,100,0,0,1,0,0,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # ffmpeg'in ass okuyucusu ilk olayi yutuyor: gorunmez bir yer tutucu ekle
    ev = [r"Dialogue: 0,0:00:00.00,0:00:00.05,Cap,,0,0,0,,{lpha&HFF&}."]
    title = spec["title"].replace("<br>", r"\N")
    ev.append(f"Dialogue: 0,{ass_time(0)},{ass_time(speech_end)},Title,,0,0,0,,{{\\pos({W // 2},{title_y - 60})\\fad(400,300)}}{title}")
    if spec.get("subtitle"):
        ev.append(f"Dialogue: 0,{ass_time(0)},{ass_time(speech_end)},Sub,,0,0,0,,{{\\pos({W // 2},{title_y})\\fad(400,300)}}{spec['subtitle']}")
    for a, b, ws in phrases(words):
        txt = " ".join(gold + w + r"{\r}" if re.sub(r"[^\w$]", "", w.lower()) in kw else w for w in ws)
        ev.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Cap,,0,0,0,,{{\\pos({W // 2},{cap_y})\\fad(120,80)}}{txt}")
    if spec.get("outro"):
        ev.append(f"Dialogue: 0,{ass_time(speech_end + 0.3)},{ass_time(total)},Outro,,0,0,0,,{{\\pos({W // 2},{H // 2})\\fad(500,0)}}{spec['outro']}")
    path.write_text(head + "\n".join(ev) + "\n", encoding="utf-8")


def main(spec_path: str) -> None:
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    src, out = Path(spec["src"]), Path(spec["out"])
    tmp = out.parent / (out.stem + "_tmp")
    tmp.mkdir(parents=True, exist_ok=True)
    words = json.loads(Path(spec["words"]).read_text(encoding="utf-8"))
    speech = duration(src)
    outro = float(spec.get("outro_seconds", 2.5)) if spec.get("outro") else 0.0
    total = speech + outro

    # B-roll parcalari: 1080xBAND_H, ayni renk ayari
    brolls = []
    for i, b in enumerate(spec.get("broll", [])):
        p = fetch_landscape(b["query"])
        if not p:
            continue
        clip = tmp / f"broll{i}.mp4"
        run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(p), "-t", f"{b['dur']:.2f}", "-an",
             "-vf", f"scale={W}:{BAND_H}:force_original_aspect_ratio=increase,crop={W}:{BAND_H},fps={FPS},{GRADE},"
                    f"fade=t=in:d=0.25,fade=t=out:st={b['dur'] - 0.25:.2f}:d=0.25",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", str(clip)])
        brolls.append((b["at"], b["dur"], clip))

    ass = tmp / "caps.ass"
    write_ass(spec, words, total, speech, ass)

    frames = int(total * FPS)
    inputs = ["-i", str(src)]
    for _, _, c in brolls:
        inputs += ["-i", str(c)]
    music = spec.get("music")
    if music:
        inputs += ["-i", music]
    # orta bant: yavas push-in (1.00 -> 1.07), soluk renk; sonra siyah zemine yerlestir
    fc = (f"[0:v]fps={FPS},scale=1920:1080,zoompan=z='1+0.07*on/{frames}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          f":s=1920x1080:fps={FPS},scale={W}:{BAND_H},{GRADE},tpad=stop_mode=add:stop_duration={outro:.2f}:color=black[band];"
          f"color=c=black:s={W}x{H}:r={FPS}:d={total:.2f}[bg];[bg][band]overlay=0:{BAND_Y}:shortest=1[v0];")
    last = "v0"
    for i, (at, dur, _) in enumerate(brolls):
        fc += f"[{i + 1}:v]setpts=PTS-STARTPTS+{at:.3f}/TB[r{i}];[{last}][r{i}]overlay=0:{BAND_Y}:eof_action=pass:enable='between(t,{at:.3f},{at + dur:.3f})'[v{i + 1}];"
        last = f"v{i + 1}"
    fc += (f"[{last}]subtitles='{ass.as_posix().replace(':', chr(92) + ':')}':fontsdir='{FONT_DIR.replace(':', chr(92) + ':')}',"
           f"noise=alls=7:allf=t,vignette=PI/5[v];")
    fc += f"[0:a]apad=pad_dur={outro:.2f}[sp];"
    if music:
        mi = 1 + len(brolls)
        vol = spec.get("music_volume", 0.2)
        fc += (f"[{mi}:a]atrim=0:{total:.2f},asetpts=PTS-STARTPTS,aresample=48000,volume={vol},afade=t=in:d=1.5,"
               f"afade=t=out:st={total - 1.8:.2f}:d=1.8[m];"
               f"[sp]asplit=2[s1][sc];[m][sc]sidechaincompress=threshold=0.04:ratio=2.5:attack=30:release=600[md];"
               f"[s1][md]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
    else:
        fc += "[sp]anull[a]"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
    print(f"OK -> {out} ({total:.1f}s)")


if __name__ == "__main__":
    main(sys.argv[1])
