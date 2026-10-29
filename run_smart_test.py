import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from smart_render import render_smart_clip

src = Path("work/newheights_cruise/source.mp4")
tr = json.load(open("work/newheights_cruise/transcript.json", encoding="utf-8"))
words = [{"word": w["word"], "start": w["start"], "end": w["end"]} for s in tr["segments"] for w in s.get("words", [])]

clip = {
    "name": "airplane_smart",
    "headline": "FAT SUIT VS *HANGING OFF A PLANE*",
    "teaser": [2806.8, 2810.45],
    "segments": [[2796.8, 2828.0]],
    # soldan saga: Travis, Jason, Tom
    "speakers": [[2796.8, 2801.5, "center"], [2801.5, 2818.5, "right"], [2818.5, 2828.0, "center"]],
    "broll": [
        {"at": 2798.9, "query": "vintage propeller airplane flying", "mode": "full", "dur": 1.6},
        {"at": 2812.9, "query": "birds flying sky", "mode": "pip", "dur": 2.0},
        {"at": 2816.0, "query": "airplane takeoff runway", "mode": "full", "dur": 1.6},
    ],
}
out = Path("output/smart_test")
out.mkdir(parents=True, exist_ok=True)
render_smart_clip(src, words, clip, out / f"{clip['name']}.mp4", Path("work/smart_tmp"))
print("DONE")
