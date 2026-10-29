"""WTS - baska kliperlarin kesmedigi anlar (doygunluk yuzunden Shorts akisi 0 kalmisti).
Yeni layout + flash-forward + WTS bug + bumper. YouTube versiyonuna Audio Library muzigi, Instagram/TikTok
icin muziksiz versiyon (brief: muzik sadece platformun kendi kutuphanesinden)."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from smart_render import render_smart_clip
from wts_render import _fix_word, add_wts_bug, append_bumper

OUT = Path("output/campaigns")
SAFE = {"split_people": False, "noface": "center"}  # cocuklari tek basina one cikarma


def load_words(path: str, fixes: dict[str, str]) -> list[dict]:
    tr = json.load(open(path, encoding="utf-8"))
    return [_fix_word({"word": w["word"], "start": w["start"], "end": w["end"]}, fixes)
            for s in tr["segments"] for w in s.get("words", [])]


SOURCES = {
    "rr": (Path("work/wts/RR_EP_204_Textless_VFinal_260924.mp4"),
           load_words("work/wts_rr204/transcript.json", {"emily": "Emaly"})),
    "xo": (Path("work/wts/101TEXTLESSXOCC.mp4"),
           load_words("work/wts_xo101_med/transcript.json", {"kara": "Cara", "karra": "Cara", "kurtis": "Curtis"})),
}

CLIPS = [
    {
        "src": "rr",
        "name": "rr_left_on_island",
        "headline": "DAD LEFT THEM ON THE ISLAND *TO TEACH A LESSON*",
        "teaser": [597.8, 601.6],
        "segments": [(547.4, 556.35), (574.2, 587.7), (590.4, 601.6), (603.3, 611.3)],
        "music": Path("assets/music/sneaky_spelunking.mp3"),
        **SAFE,
    },
    {
        "src": "xo",
        "name": "xo_canceled_cable",
        "headline": "WE CANCELED CABLE AND *GOT OUR KIDS BACK*",
        "teaser": [664.6, 668.35],
        "segments": [(619.0, 626.95), (627.45, 651.75), (652.05, 660.05)],
        **SAFE,
    },
]

only = [a for a in sys.argv[1:] if not a.startswith("--")]
only_tag = next((a[6:] for a in sys.argv[1:] if a.startswith("--tag=")), None)
OUT.mkdir(parents=True, exist_ok=True)
for clip in CLIPS:
    if only and clip["name"] not in only:
        continue
    source, words = SOURCES[clip["src"]]
    tmp = Path("work/wts_new") / clip["name"]
    variants = [("yt", clip)]
    if clip.get("music"):
        variants.append(("nomusic", {k: v for k, v in clip.items() if k != "music"}))
    for tag, spec in variants:
        if only_tag and tag != only_tag:
            continue
        print(f"\n== {clip['name']} [{tag}]", flush=True)
        base = tmp / f"{tag}_smart.mp4"
        bugged = tmp / f"{tag}_bug.mp4"
        final = OUT / f"wts_{clip['name']}_{tag}.mp4"
        render_smart_clip(source, words, spec, base, tmp)
        add_wts_bug(base, bugged)
        append_bumper(bugged, final)
        base.unlink(missing_ok=True)
        bugged.unlink(missing_ok=True)
        print(f"  OK -> {final}", flush=True)
print("\nDONE")
