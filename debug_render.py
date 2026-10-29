import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import render

# monkeypatch to print the actual cmd list before running
_orig_run = render.subprocess.run
def spy_run(cmd, *a, **kw):
    print("CMD:", " ".join(cmd), flush=True)
    result = _orig_run(cmd, *a, **kw)
    print("RETURNCODE:", result.returncode, flush=True)
    if result.returncode != 0:
        print("STDERR TAIL:", result.stderr[-3000:], flush=True)
    return result
render.subprocess.run = spy_run

with open("output/majorlazer_vod/clips.json", encoding="utf-8") as f:
    clips = json.load(f)
clip = clips[0]
print("clip:", clip)

transcript = json.load(open("work/majorlazer_vod/transcript.json", encoding="utf-8"))
flat_words = [
    {"word": w["word"], "start": w["start"], "end": w["end"]}
    for seg in transcript["segments"]
    for w in seg.get("words", [])
]
clip_words = [w for w in flat_words if w["end"] > clip["start"] and w["start"] < clip["end"]]
print("num clip_words:", len(clip_words))

out_path = Path("work/debug_01.mp4")
render.render_clip(Path("work/majorlazer_vod/source.webm"), clip, clip_words, out_path, Path("work/debug_tmp"))
print("DONE")
