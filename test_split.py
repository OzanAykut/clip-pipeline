import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from render import render_split_clip

video_id = "majorlazer_hq"
work_dir = Path("work") / video_id
source_path = work_dir / "source.webm"
gameplay_path = Path("work/gameplay/subway.webm")

with open("output/majorlazer_hq/clips.json", encoding="utf-8") as f:
    clips = json.load(f)
clip = clips[0]  # Lean On producer clip, 29s
print("clip:", clip["title"], clip["duration"])

transcript = json.load(open(work_dir / "transcript.json", encoding="utf-8"))
flat_words = [
    {"word": w["word"], "start": w["start"], "end": w["end"]}
    for seg in transcript["segments"]
    for w in seg.get("words", [])
]
clip_words = [w for w in flat_words if w["end"] > clip["start"] and w["start"] < clip["end"]]

out_dir = Path("output/split_test")
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "01_split.mp4"

render_split_clip(source_path, clip, clip_words, gameplay_path, out_path, work_dir / "tmp_split", gameplay_offset=30.0)
print("DONE ->", out_path)
