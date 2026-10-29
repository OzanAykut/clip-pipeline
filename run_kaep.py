"""Evangelist x Street You Grew Up On (Kerry Washington) - Colin Kaepernick bolumu.
Kampanya kurali: siyasi icerik yok -> diz cokme / irkcilik bolumleri (e5, e1 basi) kullanilmaz.
Her klip farkli stil + farkli muzik; loop'lar kesintisiz (loop=True: statik manset + capraz gecisli muzik)."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from smart_render import render_smart_clip

SRC = Path("work/campaigns/evang/src")
OUT = Path("output/campaigns/kaepernick")
M = Path("assets/music")
FIX = {"Child": "child", "Willedium": "Willennium", "Sirloin.": "Turlock.", "horse": "HORSE"}


# konuma bagli duzeltmeler: (kaynak, kelime baslangici) -> yeni kelime
FIX_AT = {(5, 178.48): "have a", (5, 181.04): "A.I."}


def words_for(i: int) -> list[dict]:
    tr = json.load(open(f"work/campaigns/evang/tr{i}/transcript.json", encoding="utf-8"))
    out = []
    for s in tr["segments"]:
        for w in s.get("words", []):
            t = w["word"].strip()
            t = next((v for (k, at), v in FIX_AT.items() if k == i and abs(at - w["start"]) < 0.03), FIX.get(t, t))
            out.append({"word": t, "start": w["start"], "end": w["end"]})
    return out


CLIPS = [
    # A) punchline basta + motivasyon hikayesi; gorsel (zoom) + isitsel (hit/whoosh) hook
    {"name": "cry_or_shoot", "src": 1, "headline": "KAEPERNICK'S DAD: *CRY OR SHOOT?*",
     "teaser": [275.1, 279.3], "hook_zoom": True, "tighten": True,
     "segments": [(223.9, 235.65), (236.7, 248.2), (261.4, 271.0), (281.65, 285.6), (291.7, 296.2)],
     "sfx_src": [(278.35, "hit")], "sfx": [(4.15, "whoosh")],
     "music": M / "recollections.mp3", "music_volume": 0.3},
    # B) kesintisiz loop: hikaye "burn it to the DVD" ile biter -> "Burned it to 119 DVDs..."
    {"name": "dvds_loop", "src": 2, "loop": True, "headline": "KAEPERNICK SENT HIS TAPE TO *119 COLLEGES*",
     "teaser": [157.45, 162.85], "segments": [(137.25, 155.75)], "tighten": True,
     "music": M / "after_sunset.mp3", "music_start": 20.0, "music_volume": 0.3},
    # C) kesintisiz loop: "...in this music" -> "And it's my mom singing to us... I need some different music"
    {"name": "phantom_loop", "src": 2, "loop": True, "headline": "KAEPERNICK'S MOM'S CAR MUSIC: *PHANTOM OF THE OPERA*",
     "teaser": [270.15, 275.2], "segments": [(229.3, 242.3), (250.1, 268.7)], "tighten": True,
     "music": M / "the_theme.mp3", "music_start": 12.0, "music_volume": 0.3},
    # D) soru karti acilisi, cevap ("Big Willie Style") sonda + pop efekti
    {"name": "first_album", "src": 2, "headline": "WHAT WAS COLIN KAEPERNICK'S *FIRST ALBUM?*",
     "headline_style": "question", "tighten": True,
     "segments": [(290.95, 300.0), (306.75, 312.0), (326.1, 340.2), (344.5, 351.45)],
     "sfx_src": [(350.5, "pop")], "music": M / "cutscene_crush.mp3", "music_volume": 0.3},
    # E) kesintisiz loop: Kerry'nin sorusu -> "Well, I love winning."
    {"name": "winning_loop", "src": 1, "loop": True, "headline": "COLIN KAEPERNICK ON *WINNING VS COMPETING*",
     "teaser": [184.15, 191.4], "segments": [(167.5, 182.45)], "tighten": True,
     "music": M / "ancient_civilisations.mp3", "music_start": 10.0, "music_volume": 0.3},
    # F) itiraf, kronolojik: Kerry'nin "tek evlatlik + tek siyah cocuk" tespiti hook -> boyama -> "farkli oldugumu anladim"
    #    kesimler ses tabanli (audio_cuts), loop yok (kullanici loop'u kendisi ayarliyor)
    {"name": "adopted", "src": 2, "headline": "COLIN KAEPERNICK WAS THE ONLY *ADOPTED* AND ONLY *BLACK* CHILD IN HIS FAMILY",
     "segments": [(6.02, 12.20), (44.68, 51.42), (57.54, 66.80), (67.80, 75.05)], "tighten": True, "hook_zoom": True,
     "music": M / "recollections.mp3", "music_volume": 0.3},
    # G) gorus + fikir ayriligi, loop: cevap basta; Kerry'nin "kazan ya da kaybet zevk aliyor musun?" sorusu -> basa
    #    hook sinirlari sese gore (whisper "don't"u 208.35'te bitmis sanıyordu, ses 208.70'te bitiyor)
    {"name": "hate_losing", "src": 1, "loop": True,
     "headline": "COLIN KAEPERNICK: THE MOST COMPETITIVE PEOPLE *DON'T LIKE LOSING*",
     #    Kerry'nin "I don't like losing at all" tekrari (204.4-206.6) atildi: hook = cevap + "the most competitive people don't"
     "teaser": [202.34, 204.15], "segments": [(206.66, 208.85), (180.31, 191.70), (194.33, 200.98)], "tighten": True,
     "music": M / "ancient_civilisations.mp3", "music_start": 10.0, "music_volume": 0.3},
    # H) kliplenmemis an (2026-10-12 pazar taramasi: 229 Short'ta yok): Kerry'nin annesi Allen Iverson hayrani.
    #    unlu isim + komik itiraf, kronolojik (ilk cumle hook). "privilege" kismindan once biter (siyaset yok)
    {"name": "iverson", "src": 5, "headline": "KERRY WASHINGTON'S MOM LOVED *ALLEN IVERSON*",
     "segments": [(171.54, 181.45), (181.90, 190.14)], "tighten": True, "hook_zoom": True,
     "music": M / "vibe_check.mp3", "music_volume": 0.3},
]

only = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT.mkdir(parents=True, exist_ok=True)
for clip in CLIPS:
    if only and clip["name"] not in only:
        continue
    final = OUT / f"kaep_{clip['name']}.mp4"
    if final.exists():
        continue
    print(f"\n== {clip['name']}", flush=True)
    render_smart_clip(SRC / f"e{clip['src']}.mp4", words_for(clip["src"]), clip, final,
                      Path("work/campaigns/evang/tmp") / clip["name"])
    print(f"  OK -> {final}", flush=True)
print("\nDONE")
