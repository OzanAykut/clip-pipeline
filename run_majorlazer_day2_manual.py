import json
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from render import render_clip

VIDEO_URL = "https://www.youtube.com/watch?v=bNEPRmpyolo"
BUFFER = 6.0

video_id = "majorlazer_day2_manual"
work_dir = Path("work") / video_id
seg_dir = work_dir / "segments"
seg_dir.mkdir(parents=True, exist_ok=True)
out_dir = Path("output") / video_id
out_dir.mkdir(parents=True, exist_ok=True)

clips = json.load(open("work/majorlazer_day2/manual_candidates.json", encoding="utf-8"))
transcript = json.load(open("work/majorlazer_day2/transcript.json", encoding="utf-8"))
flat_words = [
    {"word": w["word"], "start": w["start"], "end": w["end"]}
    for seg in transcript["segments"]
    for w in seg.get("words", [])
]

results = []
for i, clip in enumerate(clips, start=1):
    dl_start = max(0.0, clip["start"] - BUFFER)
    dl_end = clip["end"] + BUFFER
    seg_base = seg_dir / f"{i:02d}_seg.mp4"
    print(f"\n[{i}/{len(clips)}] downloading {dl_start:.1f}-{dl_end:.1f} -> {seg_base}")

    existing = list(seg_dir.glob(f"{i:02d}_seg.*"))
    if existing:
        seg_path = existing[0]
    else:
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "-f", "bv*[height<=720][ext=mp4]+ba/best[height<=720]",
            "--download-sections", f"*{dl_start:.2f}-{dl_end:.2f}",
            "--force-keyframes-at-cuts",
            "-o", str(seg_base),
            VIDEO_URL,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        found = list(seg_dir.glob(f"{i:02d}_seg.*"))
        if r.returncode != 0 or not found:
            print(f"DOWNLOAD FAILED for clip {i}: {r.stderr[-1500:]}")
            continue
        seg_path = found[0]

    local_clip = dict(clip)
    local_clip["start"] = clip["start"] - dl_start
    local_clip["end"] = clip["end"] - dl_start

    clip_words = []
    for w in flat_words:
        if w["end"] > clip["start"] and w["start"] < clip["end"]:
            clip_words.append({
                "word": w["word"],
                "start": w["start"] - dl_start,
                "end": w["end"] - dl_start,
            })

    out_name = f"{i:02d}_clip.mp4"
    out_path = out_dir / out_name
    try:
        render_clip(seg_path, local_clip, clip_words, out_path, work_dir / "tmp")
        clip["file"] = out_name
        results.append(clip)
        print(f"OK -> {out_path}")
    except Exception as e:
        print(f"RENDER FAILED clip {i}: {e}")

with open(out_dir / "clips.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\nDone. {len(results)}/{len(clips)} clips rendered.")
