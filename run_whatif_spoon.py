"""What-if kanali: 'What if you held a teaspoon of a neutron star?' - Gizmo.
Bilim: notron yildizi ~4e17 kg/m3 -> 5 ml ~1-6 milyar ton (insanligin toplami ~0.5 milyar ton).
Yildizin kutlecekimi olmadan madde patlayarak acilir; enerji dinozor asteroidinin (~1e23-4e23 J) binlerce kati.
v4: Gizmo'nun sesi Veo yerine Gemini TTS 'Puck' (yetiskin, gizmo_voice.py); Veo klipleri sadece goruntu,
~30 sn hedef. Replikler: work/whatif_spoon/voice/puck/*.wav"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from gizmo_render import render_gizmo

d = Path("work/whatif_spoon/flow")
v = Path("work/whatif_spoon/voice/puck")
spec = {
    "clips": [
        {"src": d / "1_hook_v3.mp4", "voice": v / "1_hook.wav", "voice_at": 0.0, "orig_volume": 0.0,
         "fix": {0: "Hey!", 1: "Help!", 2: "Help", 3: "me!", 4: "This", 12: "Earth...", 13: "COMBINED!"}},
        {"src": d / "2_scale_v2.mp4", "voice": v / "2_scale.wav", "voice_at": 0.35, "orig_volume": 0.0,
         "fix": {"squish": "squished"}},
        {"src": d / "3_drop_v2.mp4", "voice": v / "3_drop.wav", "start": 0.4, "voice_at": 0.6, "orig_volume": 0.0, "orig_until": 2.0,
         "fix": {"Oops,": "Oops!"}},
        {"src": d / "4_fall.mp4", "start": 1.0, "end": 3.0},
        {"wrong": True, "dur": 0.9, "trans": "cut"},
        {"src": d / "5_explode_v3.mp4", "voice": v / "5_explode.wav", "trans": "cut", "voice_at": 0.15,
         "end": 5.6, "orig_volume": 0.0, "orig_after": 3.6, "sfx": [(1.0, "boom")],
         "fix": {"-squeezing": "squeezing", "explodes!": "EXPLODES!"}},
        {"src": d / "6_earth.mp4", "start": 0.4, "end": 2.6},
        {"src": d / "7_outro_v2.mp4", "voice": v / "7_outro.wav", "voice_at": 0.2, "orig_volume": 0.0},
    ],
    "music": Path("assets/music/banjo_doops.mp3"),
    "music_volume": 0.10,
}

out = Path("output/whatif")
out.mkdir(parents=True, exist_ok=True)
render_gizmo(spec, out / "whatif_spoon_v4.mp4", Path("work/whatif_spoon/tmp"))
