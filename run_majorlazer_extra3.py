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

BUFFER = 6.0

jobs = [
    {
        "video_id": "majorlazer_extra3",
        "video_url": "https://www.youtube.com/watch?v=4i_c_EXZfO4",
        "candidates_file": "work/majorlazer_full/manual_candidates_2.json",
        "transcript_file": "work/majorlazer_full/transcript.json",
        "out_prefix": "d1",
    },
    {
        "video_id": "majorlazer_extra3",
        "video_url": "https://www.youtube.com/watch?v=bNEPRmpyolo",
        "candidates_file": "work/majorlazer_day2/manual_candidates_2.json",
        "transcript_file": "work/majorlazer_day2/transcript.json",
        "out_prefix": "d2",
    },
]

out_dir = Path("output/majorlazer_extra3")
out_dir.mkdir(parents=True, exist_ok=True)
all_results = []

for job in jobs:
    work_dir = Path("work") / job["video_id"]
    seg_dir = work_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    clips = json.load(open(job["candidates_file"], encoding="utf-8"))
    transcript = json.load(open(job["transcript_file"], encoding="utf-8"))
    flat_words = [
        {"word": w["word"], "start": w["start"], "end": w["end"]}
        for seg in transcript["segments"]
        for w in seg.get("words", [])
    ]

    for i, clip in enumerate(clips, start=1):
        tag = f"{job['out_prefix']}{i:02d}"
        dl_start = max(0.0, clip["start"] - BUFFER)
        dl_end = clip["end"] + BUFFER
        seg_base = seg_dir / f"{tag}_seg.mp4"
        print(f"\n[{tag}] downloading {dl_start:.1f}-{dl_end:.1f}")

        existing = list(seg_dir.glob(f"{tag}_seg.*"))
        if existing:
            seg_path = existing[0]
        else:
            cmd = [
                sys.executable, "-m", "yt_dlp",
                "-f", "bv*[height<=720][ext=mp4]+ba/best[height<=720]",
                "--download-sections", f"*{dl_start:.2f}-{dl_end:.2f}",
                "--force-keyframes-at-cuts",
                "-o", str(seg_base),
                job["video_url"],
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            found = list(seg_dir.glob(f"{tag}_seg.*"))
            if r.returncode != 0 or not found:
                print(f"DOWNLOAD FAILED {tag}: {r.stderr[-1200:]}")
                continue
            seg_path = found[0]

        local_clip = dict(clip)
        local_clip["start"] = clip["start"] - dl_start
        local_clip["end"] = clip["end"] - dl_start

        clip_words = []
        for w in flat_words:
            if w["end"] > clip["start"] and w["start"] < clip["end"]:
                clip_words.append({"word": w["word"], "start": w["start"] - dl_start, "end": w["end"] - dl_start})

        out_name = f"{tag}_clip.mp4"
        out_path = out_dir / out_name
        try:
            render_clip(seg_path, local_clip, clip_words, out_path, work_dir / "tmp")
            clip["file"] = out_name
            all_results.append(clip)
            print(f"OK -> {out_path}")
        except Exception as e:
            print(f"RENDER FAILED {tag}: {e}")

with open(out_dir / "clips.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)
print(f"\nDone. {len(all_results)} clips rendered.")
