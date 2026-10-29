"""What-if kanali: 'What if you fell into a black hole?' - POV dusus + oyun HUD'u.
Yildiz kutleli (~10 gunes kutlesi) kara delik: olay ufku ~30 km, spagettilesme ufuktan once."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from whatif_render import render_whatif

d = Path("work/whatif_blackhole/flow")
AMB = 0.55
spec = {
    "title": "WHAT IF YOU FELL INTO A *BLACK HOLE?*",
    "hud_style": "game",
    # (anahtar, etiket, birim, ikon, bar_alt, bar_ust)
    "hud_rows": [("distance", "HORIZON", "km", "depth", 1, 100_000),
                 ("dilation", "TIME DILATION", "x", "pres", 1, 1000),
                 ("tidal", "TIDAL FORCE", "g", "temp", 0.01, 20_000_000)],
    "music": Path("assets/music/ancient_civilisations.mp3"),
    "music_volume": 0.3,
    "sfx": [
        {"type": "heartbeat", "scene": 3, "offset": 0.5, "volume": 0.55},
        {"type": "alarm", "scene": 4, "offset": 0.5, "volume": 0.3},
    ],
    "scenes": [
        {"src": d / "1_far.mp4", "amb_volume": AMB,
         "tag": "intriguing, curious question",
         "say": "What if you fell into a black hole?",
         "hud": {"distance": (100_000, 20_000), "dilation": (1.0, 1.0), "tidal": (0.01, 0.01),
                 "integrity": (100, 100)}},
        {"src": d / "2_close.mp4", "transition": "fade", "amb_volume": AMB,
         "tag": "awed",
         "say": "Its gravity bends light so much, you can see the stars behind it.",
         "hud": {"distance": (20_000, 5_000), "dilation": (1.0, 1.0), "tidal": (0.01, 4),
                 "integrity": (100, 95)}},
        {"src": d / "3_stars.mp4", "transition": "fade", "amb_volume": AMB,
         "tag": "eerie, slow",
         "say": "To anyone watching you, time slows down. You seem to freeze... and fade away.",
         "hud": {"distance": (5_000, 1_500), "dilation": (1.0, 1.01), "tidal": (4, 160),
                 "integrity": (95, 80)}},
        {"src": d / "4_spaghetti.mp4", "transition": "fade", "amb_volume": AMB,
         "tag": "tense, dramatic",
         "say": "But you keep falling. Gravity pulls your feet harder than your head, stretching you like spaghetti.",
         "hud": {"distance": (1_500, 100), "dilation": (1.01, 1.2), "tidal": (160, 540_000),
                 "integrity": (80, 20)}},
        {"src": d / "5_horizon.mp4", "transition": "fade", "amb_volume": AMB,
         "tag": "grim, ominous",
         "say": "Then you cross the event horizon. Not even light can escape.",
         "hud": {"distance": (100, 1), "dilation": (1.2, 1000), "tidal": (540_000, 20_000_000),
                 "integrity": (20, 5)}},
        {"src": d / "6_inside.mp4", "transition": "fade", "amb_volume": AMB,
         "tag": "quiet, mysterious, dramatic pause",
         "say": "Every direction now leads to one place... the center. And nobody knows what's there.",
         "hud": {"distance": (1, 1), "dilation": (1000, 1000), "tidal": (20_000_000, 20_000_000),
                 "integrity": (5, 0)}},
    ],
}

out = Path("output/whatif")
out.mkdir(parents=True, exist_ok=True)
render_whatif(spec, out / "whatif_blackhole_v1.mp4", Path("work/whatif_blackhole/tmp"))
print("DONE")
