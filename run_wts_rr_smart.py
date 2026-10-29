"""Raising Reynolds (WTS kampanyasi) - yeni akilli layout + flash-forward + WTS bug + bumper.
Kampanya kurali: sadece kendi footage'lari -> B-roll yok."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from smart_render import render_smart_clip
from wts_render import _fix_word, add_wts_bug, append_bumper

SOURCE = Path("work/wts/RR_EP_204_Textless_VFinal_260924.mp4")
TMP = Path("work/wts_rr204/smart")
OUT = Path("output/campaigns")
NAME_FIXES = {"emily": "Emaly"}

tr = json.load(open("work/wts_rr204/transcript.json", encoding="utf-8"))
words = [_fix_word({"word": w["word"], "start": w["start"], "end": w["end"]}, NAME_FIXES)
         for s in tr["segments"] for w in s.get("words", [])]

# Brief: cocuklari asla tek basina one cikarma -> cok kisili sahneler bolunmez.
# Reality sahnelerinde yuzsuz cekimler (gol, tekne) manzara -> ortadan tam ekran.
SAFE = {"split_people": False, "noface": "center"}

CLIPS = [
    {
        "name": "rr_ive_got_it_handled",
        "headline": "HE SAID *\"I'VE GOT IT HANDLED\"*",
        "teaser": [836.1, 840.3],
        "segments": [(277.0, 278.3), (283.1, 287.8), (294.8, 299.7), (743.0, 752.9), (757.0, 763.9), (840.3, 848.8)],
        **SAFE,
    },
    {
        "name": "rr_survival_dad",
        "headline": "DAD'S SURVIVAL LESSON *WENT TOO FAR*",
        "teaser": [473.9, 475.8],
        "segments": [(442.2, 486.5)],
        **SAFE,
    },
]

only = sys.argv[1:]
OUT.mkdir(parents=True, exist_ok=True)
for clip in CLIPS:
    if only and clip["name"] not in only:
        continue
    print(f"\n== {clip['name']}", flush=True)
    base = TMP / f"{clip['name']}_smart.mp4"
    bugged = TMP / f"{clip['name']}_bug.mp4"
    final = OUT / f"wts_{clip['name']}_v2.mp4"
    render_smart_clip(SOURCE, words, clip, base, TMP)
    add_wts_bug(base, bugged)
    append_bumper(bugged, final)
    base.unlink(missing_ok=True)
    bugged.unlink(missing_ok=True)
    print(f"  OK -> {final}", flush=True)
print("\nDONE")
