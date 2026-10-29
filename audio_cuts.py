"""Ses enerjisine dayali kesim noktalari.

Whisper kelime zamanlari ±100 ms kayik oldugu icin onlarla yapilan jump cut'lar kelime kuyrugunu / nefesi yiyor ve
kopuk duyuluyordu (2026-10-09). Burada kesimler gercek sessizlik vadilerine oturtulur ve duraklama tamamen silinmez,
dogal kisa bir es birakilir.

envelope(path, a, b)    -> 10 ms adimli RMS dB dizisi
silences(env)           -> [(s, e)] sessiz araliklar (env'e gore saniye)
snap_start / snap_end   -> segment kenarini en yakin sessizlige kaydirir (kelime ortasinda kesmez)
smart_tighten(...)      -> tighten_segments'in sese dayali hali: uzun eslerin ortasini cikarir, kenarlarda es birakir
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

HOP = 0.01   # 10 ms
SR = 16000


def envelope(path: Path, a: float = 0.0, b: float | None = None) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{max(0.0, a):.3f}"]
    if b is not None:
        cmd += ["-t", f"{b - a:.3f}"]
    cmd += ["-i", str(path), "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    x = np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, np.int16).astype(np.float32) / 32768
    hop, win = int(SR * HOP), int(SR * 0.02)
    n = max(0, (len(x) - win) // hop + 1)
    if n == 0:
        return np.full(1, -90.0)
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    rms = np.sqrt((x[idx] ** 2).mean(axis=1)) + 1e-6
    return 20 * np.log10(rms)


def threshold(env: np.ndarray) -> float:
    """Sessizlik esigi: gurultu tabani ile konusma seviyesi arasinin %40'i (en az taban +6 dB).
    Kisik kayitta (Kaepernick: konusma ~-37, bosluk ~-50..-57 dB) sabit +10 dB esigi hic sessizlik bulamiyordu."""
    floor, speech = np.percentile(env, 10), np.percentile(env, 80)
    return float(floor + max(6.0, 0.4 * (speech - floor)))


def silences(env: np.ndarray, min_len: float = 0.08, thr: float | None = None) -> list[tuple[float, float]]:
    thr = threshold(env) if thr is None else thr
    quiet = env < thr
    out, start = [], None
    for i, q in enumerate(np.append(quiet, False)):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if (i - start) * HOP >= min_len:
                out.append((start * HOP, i * HOP))
            start = None
    return out


def _in_silence(t: float, sil: list[tuple[float, float]]) -> tuple[float, float] | None:
    return next(((s, e) for s, e in sil if s <= t <= e), None)


def snap_start(t: float, sil: list[tuple[float, float]], head: float = 0.06, reach: float = 0.25) -> float:
    """Baslangic: sessizligin icindeyse konusmanin hemen oncesine (head kadar es), konusma ortasindaysa geriye
    dogru en yakin sessizligin sonuna."""
    hit = _in_silence(t, sil)
    if hit:
        return max(hit[0], hit[1] - head)
    prev = [e for s, e in sil if e <= t and t - e <= reach]
    return max(prev[-1] - head, 0.0) if prev else t


def snap_end(t: float, sil: list[tuple[float, float]], tail: float = 0.12, reach: float = 0.3) -> float:
    """Bitis: konusma ortasindaysa ileriye dogru en yakin sessizligin basina (+tail: kelime kuyrugu/sonumleme)."""
    hit = _in_silence(t, sil)
    if hit:
        return min(hit[1], hit[0] + tail)
    nxt = [s for s, e in sil if s >= t and s - t <= reach]
    return nxt[0] + tail if nxt else t


def _minus_words(sil: list[tuple[float, float]], words: list[dict] | None,
                 margin: float = 0.03) -> list[tuple[float, float]]:
    """Kelime iceren kisimlari sessizlikten cikarir (her sessizlikten kelimesiz en uzun parca kalir).
    Kisik konusan (Kerry'nin fisildar gibi "child"i) sessizlik sanilip kesiliyordu: kesim icin ses de sessiz olmali,
    transkript de bos olmali."""
    if not words:
        return sil
    out = []
    for x, y in sil:
        free = [(x, y)]
        for w in words:
            ws, we = w["start"] - margin, w["end"] + margin
            if we <= x or ws >= y:
                continue
            nxt = []
            for a, b in free:
                if we <= a or ws >= b:
                    nxt.append((a, b))
                    continue
                if ws > a:
                    nxt.append((a, ws))
                if we < b:
                    nxt.append((we, b))
            free = nxt
        if free:
            out.append(max(free, key=lambda r: r[1] - r[0]))
    return [r for r in out if r[1] - r[0] > 0.03]


def smart_tighten(source: Path, segments: list[tuple[float, float]], max_gap: float = 0.35, keep: float = 0.2,
                  min_piece: float = 0.8, words: list[dict] | None = None) -> list[tuple[float, float]]:
    """Her segmenti ses enerjisine gore budar: kenarlar sessizlige oturur; max_gap'ten uzun her esin ortasi atilir,
    geriye 'keep' kadar dogal es kalir (yaklasik 2/3'u onceki kelimenin sonunda, 1/3'u sonrakinin basinda)."""
    out: list[tuple[float, float]] = []
    for s, e in segments:
        a, b = max(0.0, s - 0.5), e + 0.5
        env = envelope(source, a, b)
        sil = _minus_words([(x + a, y + a) for x, y in silences(env)], words)
        s2, e2 = snap_start(s, sil), snap_end(e, sil)
        if words:  # kenar kaydirma segmentin ilk/son kelimesini kesmesin
            inside = [w for w in words if w["start"] >= s - 0.05 and w["end"] <= e + 0.05]
            if inside:
                s2 = min(s2, inside[0]["start"] - 0.02)
                e2 = max(e2, inside[-1]["end"] + 0.05)
        pieces: list[list[float]] = [[s2, e2]]
        for x, y in sil:
            if y - x <= max_gap or x <= s2 or y >= e2:
                continue
            cut_a, cut_b = x + keep * 0.65, y - keep * 0.35
            last = pieces[-1]
            if cut_a - last[0] < min_piece:  # cok kisa parca birakma: bu esi kesme
                continue
            pieces[-1] = [last[0], cut_a]
            pieces.append([cut_b, e2])
        out += [(round(p, 3), round(q, 3)) for p, q in pieces if q - p > 0.05]
    return out


def silence_map(path: Path, pps: int = 50) -> dict:
    """Studio icin: dalga formu (log olcek, 0-1) + sessiz araliklar. pps = saniye basina nokta."""
    env = envelope(path)
    thr = threshold(env)
    step = max(1, int(round(1 / (HOP * pps))))
    n = len(env) // step
    peaks = env[: n * step].reshape(n, step).max(axis=1) if n else env
    lo, hi = thr - 6, float(np.percentile(env, 99))
    norm = np.clip((peaks - lo) / max(1.0, hi - lo), 0, 1)
    return {"pps": pps, "peaks": [round(float(v), 3) for v in norm],
            "silences": [(round(s, 3), round(e, 3)) for s, e in silences(env, min_len=0.1, thr=thr)]}
