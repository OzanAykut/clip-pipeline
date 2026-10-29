"""What-if kanali: 'What if you fell into Jupiter?' - POV dusus + canli HUD formati."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from whatif_render import render_whatif

d = Path("work/whatif_jupiter/flow")
AMB = 0.55  # Veo'nun ruzgar/ugultu sesleri bu formatta onemli
spec = {
    "title": "WHAT IF YOU FELL INTO *JUPITER?*",
    "hud_style": "game",
    "music": Path("assets/music/conspiracy_theory.mp3"),
    "music_volume": 0.3,
    "sfx": [
        {"type": "heartbeat", "scene": 3, "offset": 1.0, "volume": 0.55},
        {"type": "alarm", "scene": 4, "offset": 1.5, "volume": 0.35},
    ],
    "scenes": [
        {"src": d / "1_space.mp4", "amb_volume": AMB,
         "style": "Intriguing question with rising intonation, then a slightly ominous tone.",
         "tag": "intriguing, curious question, then ominous",
         "say": "What if you fell into Jupiter? Here's how long you'd last.",
         "hud": {"label": "ALTITUDE", "depth": (20000, 50), "temp": (-150, -150), "pressure": (0, 0),
                 "integrity": (100, 100)}},
        {"src": d / "2_entry.mp4", "transition": "fade", "amb_volume": AMB,
         "style": "Intense and fast.",
         "tag": "intense, urgent",
         "say": "You'd hit the atmosphere at nearly sixty kilometers per second.",
         "hud": {"depth": (0, 50), "temp": (-150, -145), "pressure": (0.1, 0.5), "integrity": (100, 92)}},
        {"src": d / "3_ammonia.mp4", "transition": "fade", "amb_volume": AMB,
         "style": "Cold and awed.",
         "tag": "cold, awed",
         "say": "Minus one hundred forty-five degrees. Clouds of frozen ammonia.",
         "hud": {"depth": (50, 90), "temp": (-145, -100), "pressure": (0.5, 2), "integrity": (92, 85)}},
        {"src": d / "4_storm.mp4", "transition": "fade", "amb_volume": AMB,
         "style": "Tense and dramatic.",
         "tag": "tense, dramatic",
         "say": "Then the storms hit. Giant bolts of lightning, all around you.",
         "hud": {"depth": (90, 130), "temp": (-100, 20), "pressure": (2, 8), "integrity": (85, 55)}},
        {"src": d / "5_probe.mp4", "transition": "fade", "amb_volume": AMB,
         "style": "Grim and serious, slow down on 'went silent'.",
         "tag": "grim, serious",
         "say": "About a hundred and fifty kilometers down, NASA's Galileo probe went silent. You keep falling.",
         "hud": {"depth": (130, 1000), "temp": (20, 2000), "pressure": (8, 2000), "integrity": (55, 15)}},
        {"src": d / "6_ocean.mp4", "transition": "fade", "amb_volume": AMB,
         "style": "Ominous build-up, then a dramatic pause before the final twist, delivered quietly.",
         "tag": "ominous build-up, dramatic pause, quiet final twist",
         "say": "Deeper still, hydrogen turns into liquid metal. And you never hit the ground... because Jupiter doesn't have one.",
         "hud": {"depth": (1000, 20000), "temp": (2000, 10000), "pressure": (2000, 2000000),
                 "integrity": (15, 0)}},
    ],
}

out = Path("output/whatif")
out.mkdir(parents=True, exist_ok=True)
render_whatif(spec, out / "whatif_jupiter_v4.mp4", Path("work/whatif_jupiter/tmp"))
print("DONE")
