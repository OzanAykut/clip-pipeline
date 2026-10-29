"""Evangelist x Street We Grew Up On (Kerry Washington) - Ben Affleck bolumu, Whop $3 CPM.
Kurallar: sadece kampanya klipleri, abartisiz baslik, telifli muzik yok, aciklamada #ad + full episode notu."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from smart_render import render_smart_clip

SRC = Path("work/campaigns/affleck/src")
OUT = Path("output/campaigns/affleck")
FIX = {"Kira": "Kerry", "Rashid": "Washington", "KCF": "Casey", "Fucky,": "Lucky,", "Carrie": "Kerry", "Carrie's": "Kerry's", "sad": "SAG", "tired.": "tall.", "shit.": "s**t.", "odyssey": "Odyssey", "animals.": "Animals."}


def words_for(i: int) -> list[dict]:
    tr = json.load(open(f"work/campaigns/affleck/tr{i}/transcript.json", encoding="utf-8"))
    out = []
    for s in tr["segments"]:
        for w in s.get("words", []):
            t = w["word"].strip()
            out.append({"word": FIX.get(t, t), "start": w["start"], "end": w["end"]})
    if i == 4:  # whisper "f***ing"i atlamis (altyazi sesle eslesmeli); zamanlar 3 sn'lik yeniden transkriptten
        for w in out:
            if w["word"] == "uncoordinated." and 296 < w["start"] < 297.5:
                w["start"], w["end"] = 297.28, 297.78
        out.append({"word": "f***ing", "start": 296.86, "end": 297.28})
        out.sort(key=lambda w: w["start"])
    return out


CLIPS = [
    # 1) flashback teaser + ustte manset
    {"name": "second_choice", "src": 2, "headline": "BEN WANTED *JEN GARNER* FOR HER ROLE",
     "teaser": [261.9, 265.3], "segments": [(244.3, 276.3), (281.3, 298.3)]},
    # 2) dogrudan dalis: manset yok, espri anlarinda zoom vuruslari
    {"name": "casey_college", "src": 1, "headline": None,
     "segments": [(71.4, 112.9)], "music": Path("assets/music/sneaky_spelunking.mp3"), "music_volume": 0.3, "punch_src": [(89.3, 0.9), (105.6, 1.0)], "tighten": True},
    # 3) soru karti acilisi
    {"name": "matt_friends", "src": 4, "headline": "DOES BEN AFFLECK HAVE *ANY FRIENDS* BESIDES MATT?",
     "headline_style": "question", "tighten": True, "music": Path("assets/music/banjo_doops.mp3"), "music_volume": 0.3, "segments": [(193.6, 216.6), (285.8, 302.6)]},
    # 4) B-roll (kosede pencere) + ustte manset
    {"name": "jen_bakes", "src": 5, "headline": "JEN GARNER & KERRY *BAKE FOR THE CREW*",
     "segments": [(161.9, 190.4)], "tighten": True, "music": Path("assets/music/banjo_doops.mp3"), "music_volume": 0.3,
     "broll": [{"at": 170.0, "query": "film set crew", "dur": 2.0, "mode": "full"},
               {"at": 186.5, "query": "donuts box", "dur": 1.8, "mode": "full"},
               {"at": 188.5, "query": "halloween muffins", "dur": 1.8, "mode": "full"}]},
    # 5) motivasyon 2: tam ekran B-roll + piyano
    {"name": "not_famous_gift", "src": 5, "headline": "WHY BEN AFFLECK CALLS NOT BEING FAMOUS *A GIFT*",
     "segments": [(131.4, 157.9), (215.5, 221.5), (268.1, 274.4)], "tighten": True,
     "music": Path("assets/music/recollections.mp3"), "music_volume": 0.3,
     "broll": [{"at": 149.0, "query": "kids playing street", "dur": 2.0, "mode": "full"},
               {"at": 219.9, "query": "empty theater stage", "dur": 1.8, "mode": "full"},
               {"at": 270.8, "query": "film set clapperboard", "dur": 1.8, "mode": "full"}]},
    # 6) LOOP: en carpici cumle sondan kesilip basa konur; hikaye tam o cumleden once biter -> kesintisiz dongu
    {"name": "matt_loop", "loop": True, "src": 4, "headline": "KERRY ROASTS BEN ABOUT *MATT DAMON*",
     "teaser": [211.1, 214.65], "segments": [(193.6, 210.75)], "tighten": True,
     "speakers": [[211.1, 212.45, "right"], [212.45, 214.65, "left"]],
     "music": Path("assets/music/banjo_doops.mp3"), "music_volume": 0.3},
    # 7-10) KISA LOOP serisi (15-20 sn, punchline basta, hikaye punchline'dan hemen once biter) - 1.2K tavanini kirma denemesi
    {"name": "loop_lead", "loop": True, "src": 5, "headline": "BEN WAS THE LEAD, KERRY WAS *CHEERLEADER #3*",
     "teaser": [244.55, 249.45], "segments": [(230.0, 244.5)], "tighten": True,
     "speakers": [[244.55, 249.2, "right"]],
     "music": Path("assets/music/banjo_doops.mp3"), "music_volume": 0.3},
    {"name": "loop_boss", "loop": True, "src": 5, "headline": "DOES BEN AFFLECK DIRECT TO *BE THE BOSS?*",
     "teaser": [281.15, 285.7], "segments": [(268.15, 281.1)], "tighten": True,
     "speakers": [[281.15, 282.4, "left"], [282.4, 283.5, "right"], [283.5, 285.7, "left"]],
     "music": Path("assets/music/vibe_check.mp3"), "music_volume": 0.3},
    {"name": "loop_tall", "loop": True, "src": 4, "headline": "MATT DAMON ROASTED BEN'S *GROWTH SPURT*",
     "teaser": [295.7, 302.45], "segments": [(285.8, 295.65)], "tighten": True,
     "speakers": [[295.7, 299.0, "right"], [299.0, 299.6, "left"], [299.6, 302.45, "right"]],
     "music": Path("assets/music/cutscene_crush.mp3"), "music_volume": 0.3},
    # v2: manset ilk cumleyle ayni (isim + laf sokma), laf sokma anina zoom + punchline'a vurus.
    # "I remember Matt" bitisik soyleniyor, "Matt"tan kesmek ismi bozuyor -> dogal duraklamadan (295.70) basla
    {"name": "loop_tall2", "loop": True, "src": 4, "headline": "MATT DAMON CALLED BEN AFFLECK *UNCOORDINATED*",
     "teaser": [295.70, 302.45], "segments": [(285.8, 295.65)], "tighten": True,
     "speakers": [[295.7, 299.0, "right"], [299.0, 299.6, "left"], [299.6, 302.45, "right"]],
     "punch_src": [(297.28, 0.6)], "sfx_src": [(302.03, "hit")],
     "music": Path("assets/music/cutscene_crush.mp3"), "music_volume": 0.3},
    {"name": "loop_nolan", "loop": True, "src": 2, "headline": "WHY BEN WANTED TO THANK *CHRISTOPHER NOLAN*",
     "teaser": [294.35, 298.15], "segments": [(281.25, 294.3)], "tighten": True,
     "speakers": [[294.35, 298.15, "right"]],
     "music": Path("assets/music/conspiracy_theory.mp3"), "music_volume": 0.3},
]

only = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT.mkdir(parents=True, exist_ok=True)
for clip in CLIPS:
    if only and clip["name"] not in only:
        continue
    final = OUT / f"affleck_{clip['name']}.mp4"
    if final.exists():
        continue
    print(f"\n== {clip['name']}", flush=True)
    render_smart_clip(SRC / f"dl{clip['src']}.mp4", words_for(clip["src"]), clip, final,
                      Path("work/campaigns/affleck/tmp") / clip["name"])
    print(f"  OK -> {final}", flush=True)
print("\nDONE")
