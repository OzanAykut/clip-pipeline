"""Gizmo'nun sesi: Gemini TTS (Puck, yetiskin, tizlestirme yok) ile replik uretir ve temizler.

Temizlik: etiket okunduysa ilk beklenen kelimeden baslatir, son kelimeden +0.22 sn sonra keser (TTS'in
sondaki cizirtisi/nefesi gider), kisa fade, hafif gurultu azaltma, hizlandirma. Cikti 48 kHz mono wav.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import whatif_render as wr

VOICE = "Puck"
SPEED = 1.1
BASE_STYLE = ("You are voicing Gizmo, a cartoon scientist in a comedy short. Act it like a professional "
              "voice actor: big emotions, fast energetic pace, strong pitch changes, never monotone.")

_whisper = None


def _words(path: Path) -> list:
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel("small", device="cpu", compute_type="int8")
    return [w for s in _whisper.transcribe(str(path), language="en", word_timestamps=True)[0] for w in s.words]


def _speech_end(raw: Path, last_word_end: float, floor_db: float = -40.0) -> float:
    """Son kelimeden sonra sesin -40 dB'in altina indigi an. Whisper uzun cigliklarin sonunu erken bitiriyor,
    TTS ise sonda alcak seviyeli cizirti birakiyor: ikisini enerjiden ayiririz."""
    import wave

    import numpy as np
    with wave.open(str(raw)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(float) / 32768
    hop = int(sr * 0.02)
    t = last_word_end
    while int(t * sr) + hop < len(x):
        seg = x[int(t * sr):int(t * sr) + hop]
        if 20 * np.log10(np.sqrt((seg ** 2).mean()) + 1e-9) < floor_db:
            return t
        t += 0.02
    return t


def make_line(text: str, style: str, tag: str, out: Path) -> Path:
    """Repligi uretir (onbellekli: ham wav varsa tekrar istemez) ve temiz/hizli halini out'a yazar."""
    raw = out.with_name(out.stem + "_raw.wav")
    if not raw.exists():
        wr.TTS_VOICE = VOICE
        wr.TTS_BASE_STYLE = BASE_STYLE
        wr.gemini_tts(text, style, raw, tag)
    ws = _words(raw)
    first = text.split()[0].lower().strip("!,.?")
    i = next((k for k, w in enumerate(ws) if w.word.strip().lower().strip("!,.?").startswith(first)), 0)
    a = max(0.0, ws[i].start - 0.05)
    b = _speech_end(raw, ws[-1].end) + 0.08
    d = b - a
    af = (f"atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,highpass=f=70,afftdn=nf=-25,"
          f"afade=t=out:st={max(0, d - 0.12):.3f}:d=0.12,atempo={SPEED},aresample=48000")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", af, "-ac", "1", str(out)], check=True)
    return out
