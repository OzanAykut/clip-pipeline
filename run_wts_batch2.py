"""WTS 2. parti: RR 204'ten az kesilmis, Blake odakli 5 an (XO Shorts'ta tutmadi, atlandi).
Her klip: yt (Audio Library muzikli) + nomusic (TikTok/Instagram'da uygulama icinden muzik eklenecek)."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from smart_render import render_smart_clip
from wts_render import _fix_word, add_wts_bug, append_bumper

SOURCE = Path("work/wts/RR_EP_204_Textless_VFinal_260924.mp4")
OUT = Path("output/campaigns/batch2")
SAFE = {"split_people": False, "noface": "center"}  # cocuklari tek basina one cikarma
BANJO = Path("assets/music/banjo_doops.mp3")
SNEAKY = Path("assets/music/sneaky_spelunking.mp3")

tr = json.load(open("work/wts_rr204/transcript.json", encoding="utf-8"))
words = [_fix_word({"word": w["word"], "start": w["start"], "end": w["end"]}, {"emily": "Emaly"})
         for s in tr["segments"] for w in s.get("words", [])]

CLIPS = [
    {"name": "rr_oompa_loompas", "headline": "DAD NEVER WENT TO *HOMECOMING*",
     "teaser": [131.9, 135.95], "segments": [(110.7, 143.8)], "music": BANJO},
    {"name": "rr_remain_untouchable", "headline": "DAD'S ADVICE: *REMAIN UNTOUCHABLE*",
     "teaser": [161.4, 164.8], "segments": [(155.2, 180.5)], "music": BANJO},
    {"name": "rr_costs_me_money", "headline": "EVERYTHING *COSTS DAD MONEY*",
     "teaser": [206.0, 209.2], "segments": [(196.3, 215.2), (272.5, 278.6)], "music": BANJO},
    {"name": "rr_ate_the_beast", "headline": "DID DAD REALLY *EAT THAT?*",
     "teaser": [961.3, 965.8], "segments": [(954.1, 987.5)], "music": SNEAKY},
    {"name": "rr_just_waving", "headline": "THEY THOUGHT WE WERE *JUST WAVING*",
     "teaser": [786.2, 792.05], "segments": [(767.9, 792.05), (803.9, 819.3)], "music": SNEAKY},
]

only = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT.mkdir(parents=True, exist_ok=True)
for clip in CLIPS:
    if only and clip["name"] not in only:
        continue
    clip = {**clip, **SAFE}
    tmp = Path("work/wts_batch2") / clip["name"]
    for tag, spec in [("yt", clip), ("nomusic", {k: v for k, v in clip.items() if k != "music"})]:
        final = OUT / f"wts_{clip['name']}_{tag}.mp4"
        if final.exists():
            continue
        print(f"\n== {clip['name']} [{tag}]", flush=True)
        base, bugged = tmp / f"{tag}_smart.mp4", tmp / f"{tag}_bug.mp4"
        render_smart_clip(SOURCE, words, spec, base, tmp)
        add_wts_bug(base, bugged)
        append_bumper(bugged, final)
        base.unlink(missing_ok=True)
        bugged.unlink(missing_ok=True)
        print(f"  OK -> {final}", flush=True)
print("\nDONE")
