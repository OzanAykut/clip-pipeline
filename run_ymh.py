import json
import random
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from render import render_clip, render_split_clip

video_id = "ymh_zacefron"
work_dir = Path("work") / video_id
source_path = work_dir / "source.mp4"
gameplay_path = Path("work") / "gameplay" / "subway.webm"
out_dir = Path("output") / video_id
out_dir.mkdir(parents=True, exist_ok=True)

clips = json.load(open(work_dir / "manual_candidates.json", encoding="utf-8"))
transcript = json.load(open(work_dir / "transcript.json", encoding="utf-8"))
flat_words = [
    {"word": w["word"], "start": w["start"], "end": w["end"]}
    for seg in transcript["segments"]
    for w in seg.get("words", [])
]

GAMEPLAY_DURATION = 377.0

results = []
for i, clip in enumerate(clips, start=1):
    out_name = f"{i:02d}_clip.mp4"
    out_path = out_dir / out_name
    clip_words = [w for w in flat_words if w["end"] > clip["start"] and w["start"] < clip["end"]]
    tag = "SPLIT" if clip.get("split") else "NORMAL"
    print(f"\n[{i}/{len(clips)}] ({tag}) {clip['title']} [{clip['start']:.1f}-{clip['end']:.1f}]")
    try:
        if clip.get("split"):
            duration = clip["end"] - clip["start"]
            max_offset = max(0.0, GAMEPLAY_DURATION - duration - 1.0)
            gp_offset = random.uniform(0.0, max_offset)
            render_split_clip(source_path, clip, clip_words, gameplay_path, out_path, work_dir / "tmp", gameplay_offset=gp_offset)
        else:
            render_clip(source_path, clip, clip_words, out_path, work_dir / "tmp")
        clip["file"] = out_name
        results.append(clip)
        print(f"OK -> {out_path}")
    except Exception as e:
        print(f"FAILED clip {i}: {e}")

with open(out_dir / "clips.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\nDone. {len(results)}/{len(clips)} clips rendered.")
