import json
import os
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from dotenv import load_dotenv

load_dotenv()

from transcribe import transcribe_video
from select_moments import select_moments
from render import render_clip

video_id = "majorlazer_vod"
work_dir = Path("work") / video_id
source_path = work_dir / "source.webm"
out_dir = Path("output") / video_id
out_dir.mkdir(parents=True, exist_ok=True)

transcript = transcribe_video(source_path, work_dir, model_size="small", language="en")
print("Segments:", len(transcript["segments"]))

flat_words = [
    {"word": w["word"], "start": w["start"], "end": w["end"]}
    for seg in transcript["segments"]
    for w in seg.get("words", [])
]

clips = select_moments(
    transcript, os.environ["GEMINI_API_KEY"], num_clips=10, min_dur=15, max_dur=45
)
print("\nCandidates found:", len(clips))
for c in clips:
    print(f"  [{c['start']:.1f}-{c['end']:.1f}] score={c['score']} {c['title']}")

results = []
for i, clip in enumerate(clips, start=1):
    out_name = f"{i:02d}_clip.mp4"
    out_path = out_dir / out_name
    clip_words = [w for w in flat_words if w["end"] > clip["start"] and w["start"] < clip["end"]]
    try:
        render_clip(source_path, clip, clip_words, out_path, work_dir / "tmp")
        clip["file"] = out_name
        results.append(clip)
        print(f"OK -> {out_path}")
    except Exception as e:
        print(f"FAILED clip {i}: {e}")

with open(out_dir / "clips.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("\nDone.", len(results), "clips rendered.")
