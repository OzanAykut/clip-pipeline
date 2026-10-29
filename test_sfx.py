import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from render import render_clip, _find_hook_word_times

video_id = "majorlazer_hq2"
work_dir = Path("work") / video_id
source_path = work_dir / "source.webm"

with open("output/majorlazer_hq2/clips.json", encoding="utf-8") as f:
    clips = json.load(f)
clip = clips[0]
clip["hook_words"] = ["premises", "animal", "donkey"]
print("clip:", clip["title"], clip["start"], clip["end"])

transcript = json.load(open(work_dir / "transcript.json", encoding="utf-8"))
flat_words = [
    {"word": w["word"], "start": w["start"], "end": w["end"]}
    for seg in transcript["segments"]
    for w in seg.get("words", [])
]
clip_words = [w for w in flat_words if w["end"] > clip["start"] and w["start"] < clip["end"]]

sfx_times = _find_hook_word_times(clip["hook_words"], clip_words, clip["start"], clip["end"])
print("sfx_times (clip-relative sec):", sfx_times)

out_dir = Path("output/sfx_test")
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "01_sfx.mp4"

render_clip(source_path, clip, clip_words, out_path, work_dir / "tmp_sfx")
print("DONE ->", out_path)
