"""What-if kanali: 'What if a needle hit Earth at light speed?' - Leo karakteri ('sen'), kronometre HUD'u, loop.
Fizik: 1 g, %99.99 c -> gamma ~70.7, E ~6.3e15 J ~1.5 Mt TNT ~100 Hiroshima (15 kt)."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import whatif_render as wr
from whatif_render import render_whatif

SEAM_TEXT = ("And you never even saw it coming. "
             "Just a single sewing needle, flying at your city at 99.99% the speed of light.")


def make_seam(out_dir: Path) -> dict:
    """Loop dikisi: son cumle + 'Just' + acilis cumlesi TEK kayitta okunur, sonra ucе bolunur.
    Boylece videonun sonu ('...Just') ile basi ('a single sewing needle...') ayni nefesin devami olur."""
    import subprocess

    from faster_whisper import WhisperModel

    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / "seam_raw.wav"
    parts = {k: out_dir / f"seam_{k}.wav" for k in ("end", "just", "open")}
    if all(p.exists() for p in parts.values()):
        return {k: str(v) for k, v in parts.items()}
    if not raw.exists():
        wr.TTS_VOICE = "Zubenelgenubi"
        wr.gemini_tts(SEAM_TEXT, "Intense and gripping, flowing straight from 'Just' into 'a single sewing needle' "
                      "with no pause, then punch '99.99%' hard.", raw, "intense, gripping, urgent")
    ws = [w for seg in WhisperModel("small", device="cpu", compute_type="int8").transcribe(
        str(raw), language="en", word_timestamps=True)[0] for w in seg.words]
    norm = [w.word.strip().lower().strip(".,!?") for w in ws]
    j = norm.index("just")
    a_end, j_start, j_end, o_start = ws[j - 1].end, ws[j].start, ws[j].end, ws[j + 1].start
    cut1 = (a_end + j_start) / 2
    # whisper kelime sinirlari ~0.2 sn kayabiliyor: 'Just' ile 'a' arasini enerjiden bul (en sessiz 20 ms)
    import wave

    import numpy as np
    with wave.open(str(raw)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(float)
    hop = int(sr * 0.02)
    lo, hi = j_start + 0.2, ws[j + 1].end + 0.15
    cands = [(np.sqrt((x[int(t * sr):int(t * sr) + hop] ** 2).mean()), t) for t in np.arange(lo, hi, 0.01)]
    cut2 = min(cands)[1] + 0.01
    for k, (t0, t1) in {"end": (0, cut1), "just": (cut1, cut2), "open": (cut2, None)}.items():
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-ss", f"{t0:.3f}"]
        if t1 is not None:
            cmd += ["-to", f"{t1:.3f}"]
        subprocess.run(cmd + [str(parts[k])], check=True)
    return {k: str(v) for k, v in parts.items()}


seam = make_seam(Path("work/whatif_needle/tmp/seam"))

d = Path("work/whatif_needle/flow")
AMB = 0.5
spec = {
    "title": "WHAT IF A NEEDLE HIT EARTH AT *LIGHT SPEED?*",
    "voice": "Zubenelgenubi",
    "speed": 1.25,
    "caption_words": 2,
    "gap_max": 0.06,     # cumle arasi bosluk yok: nefes almadan akan anlatim
    "narr_lead": 0.0,
    "narr_tail": 0.0,
    "loop": True,
    "hud_style": "timer",
    "energy_label": "HIROSHIMA",
    "music": Path("assets/music/conspiracy_theory.mp3"),
    "music_volume": 0.3,
    "sfx": [
        {"type": "heartbeat", "scene": 1, "offset": 0.3, "volume": 0.45, "until_next": True},
        {"type": "riser", "scene": 2, "offset": 0.0, "volume": 0.35, "until_next": True, "fade_out": 0.05},
        {"type": "boom", "scene": 3, "offset": 0.0, "volume": 0.9, "dur": 3.0},
        {"type": "boom", "scene": 4, "offset": 0.0, "volume": 0.6, "dur": 3.0},
        {"type": "rumble", "scene": 4, "offset": 0.2, "volume": 0.5, "until_next": True},
    ],
    "scenes": [
        {"src": d / "1_dive.mp4", "amb_volume": AMB,
         "wav": seam["open"],
         "say": "a single sewing needle, flying at your city at 99.99% the speed of light."},
        {"src": d / "2_rooftop.mp4", "transition": "fade", "amb_volume": AMB, "start": 0.3, "end": 4.4,
         "tag": "tense, building suspense",
         "style": "Tense and building, hit '100 Hiroshima bombs' hard.",
         "say": "It weighs just one gram. But at this speed, it hits with the energy of 100 Hiroshima bombs.",
         "hud": {"timer": (0.000001, 0.00005), "energy": (0, 100)}},
        {"src": d / "3_look_up.mp4", "transition": "fade", "amb_volume": AMB, "start": 4.4,
         "tag": "awed, intense",
         "style": "Awed and intense, slow down on 'like inside the Sun'.",
         "say": "The air in front of it gets hit so hard, the atoms fuse together, like inside the Sun.",
         "hud": {"timer": (0.00005, 0.001), "energy": (100, 100)}},
        {"src": d / "4_flash.mp4", "transition": "fade", "amb_volume": AMB,
         "tag": "urgent, dramatic",
         "style": "Urgent and dramatic.",
         "say": "A flash brighter than the Sun. If you looked up, you'd be blinded instantly.",
         "hud": {"timer": (0.001, 0.2), "energy": (100, 100)}},
        {"src": d / "5_shockwave.mp4", "transition": "fade", "amb_volume": 0.7,
         "tag": "urgent, intense",
         "style": "Urgent and intense.",
         "say": "Then the shockwave hits. Windows shatter for miles.",
         "hud": {"timer": (0.2, 4.0), "energy": (100, 100)}},
        {"src": d / "6_mushroom.mp4", "transition": "fade", "amb_volume": AMB,
         "wav": seam["end"],
         "say": "And you never even saw it coming.",
         "hud": {"timer": (4.0, 10.0), "energy": (100, 100)}},
        # loop kuyrugu: acilis klibinin hemen onceki kareleri + 'Just' (src render sirasinda atanir)
        {"loop_tail": True, "transition": "fade", "amb_volume": AMB, "tail": 0.0,
         "wav": seam["just"], "say": "Just"},
    ],
}

out = Path("output/whatif")
out.mkdir(parents=True, exist_ok=True)
render_whatif(spec, out / "whatif_needle_v1.mp4", Path("work/whatif_needle/tmp"))
print("DONE")
