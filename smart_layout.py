"""Cekim (shot) tespiti, kisi sayimi, aktif konusmaci tespiti ve kisi sayisina gore layout plani.

Akis: kaynak araligini kucultulmus cozunurlukte tek seferde okur ->
  - her karede histogram farkiyla kamera kesimlerini bulur,
  - ~6 fps'te YuNet ile yuzleri bulur, cekim icinde x konumuna gore kisilere (slot) kumeler,
  - cok kisili cekimlerde kimin konustugunu klip tanimindaki ipuclarindan (yoksa agiz
    bolgesi hareketinden) bulur,
  - her cekimi fill / split / three / letterbox parcalarina boler. Cok kisili uzun cekimlerde
    konusmaci degistikce ve belli araliklarla layout degistirilir (pattern interrupt).
Tum kirpma dikdortgenleri sabit (dinamik ifade yok), boylece "random yere zoom" kaymasi olmaz.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from utils import console, ffprobe_resolution

YUNET_PATH = Path("models") / "face_detection_yunet_2023mar.onnx"

ANALYSIS_W = 1280  # analiz icin kucultulmus genislik
FACE_EVERY = 4  # her N karede bir yuz tespiti (~6 fps @ 24fps kaynak)
JAW_EVERY = 2  # cok kisili cekimlerde her N karede bir agiz acikligi
CUT_THRESHOLD = 0.55  # HSV histogram korelasyonu bunun altina duserse kamera kesimi
CUT_DIFF = 18.0  # 64x36 gri karede ortalama piksel farki (kesimlerde ~40-50, normalde ~1-3)
MIN_SHOT = 0.4  # bundan kisa cekimleri komsusuna kat
SLOT_PRESENCE = 0.35  # bir kisinin cekimde "var" sayilmasi icin gorunme orani
MIN_FACE_REL_H = 0.06  # kare yuksekligine gore bundan kucuk yuzler (arka plan, poster) yok sayilir

# Layout degisim ritmi (referans Short ~3.4 sn/kesim)
MIN_LAYOUT_SEG = 1.2
MAX_LAYOUT_SEG = 3.6
SPEAKER_HOLD = 0.9  # konusmaci en az bu kadar surmeden degismis sayilmaz


@dataclass
class Slot:
    cx: float
    cy: float
    fw: float  # yuz genisligi (kaynak px)
    fh: float
    jaw: list[tuple[float, float]] = field(default_factory=list)  # (t, agiz hareketi)


@dataclass
class Shot:
    t0: float
    t1: float
    slots: list[Slot]


@dataclass
class LayoutSeg:
    t0: float
    t1: float
    kind: str  # fill | split | three | letterbox
    rects: list[tuple[int, int, int, int]]  # kaynak px (x, y, w, h), panel sirasiyla
    shot: int = -1


# ---------------- Okuma ----------------


def _read_frames(source: Path, start: float, end: float, out_w: int, out_h: int):
    cmd = [
        "ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", str(source), "-t", f"{end - start:.3f}",
        "-vf", f"scale={out_w}:{out_h}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    frame_bytes = out_w * out_h * 3
    try:
        while True:
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            yield np.frombuffer(buf, np.uint8).reshape(out_h, out_w, 3)
    finally:
        proc.stdout.close()
        proc.wait()


def _source_fps(source: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
         "-of", "csv=p=0", str(source)], capture_output=True, text=True,
    )
    num, den = r.stdout.strip().split("/")
    return float(num) / float(den)


# ---------------- Analiz ----------------


def _hist(frame) -> np.ndarray:
    import cv2

    small = cv2.resize(frame, (160, 90))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
    return cv2.normalize(h, h).flatten()


def _cluster_slots(dets: list[tuple[float, float, float, float, float]], n_frames: int, frame_w: int) -> list[Slot]:
    """dets: (t, cx, cy, fw, fh). x merkezine gore bosluk tabanli 1B kumeleme."""
    if not dets or n_frames == 0:
        return []
    dets = sorted(dets, key=lambda d: d[1])
    gap = frame_w * 0.07
    clusters: list[list] = [[dets[0]]]
    for d in dets[1:]:
        if d[1] - clusters[-1][-1][1] > gap:
            clusters.append([d])
        else:
            clusters[-1].append(d)
    slots = []
    for c in clusters:
        frames_seen = len({round(d[0], 3) for d in c})
        if frames_seen / n_frames < SLOT_PRESENCE:
            continue
        arr = np.array([d[1:] for d in c])
        med = np.median(arr, axis=0)
        slots.append(Slot(cx=float(med[0]), cy=float(med[1]), fw=float(med[2]), fh=float(med[3])))
    # arka plandaki poster / plak kapagi yuzleri: en buyuk yuzun yarisindan kucukse kisi sayilmaz
    # (Kaepernick bolumu: raftaki Aretha plagi Kerry'nin tek cekimini "split"e ceviriyordu, 2026-10-10)
    if slots:
        big = max(s.fw for s in slots)
        slots = [s for s in slots if s.fw >= 0.45 * big]
    return sorted(slots, key=lambda s: s.cx)


def analyze_range(source: Path, start: float, end: float) -> tuple[list[Shot], tuple[int, int]]:
    import cv2

    src_w, src_h = ffprobe_resolution(source)
    aw = ANALYSIS_W
    ah = round(src_h * aw / src_w / 2) * 2
    scale = src_w / aw
    fps = _source_fps(source)

    detector = cv2.FaceDetectorYN.create(str(YUNET_PATH), "", (aw, ah), 0.7, 0.3, 50)
    mw, mh = aw // 2, ah // 2  # agiz hareketi icin yarim cozunurluk gri kareler
    mscale = src_w / mw

    # 1. gecis: kesimler + yuzler + cok kisili karelerde gri kareler (agiz hareketi icin)
    cuts = [0.0]
    prev_hist = None
    prev_gray = None
    face_samples: list[tuple[float, list[tuple[float, float, float, float]]]] = []
    motion_frames: list[tuple[float, np.ndarray]] = []
    for i, frame in enumerate(_read_frames(source, start, end, aw, ah)):
        t = i / fps
        h = _hist(frame)
        gray = cv2.cvtColor(cv2.resize(frame, (64, 36)), cv2.COLOR_BGR2GRAY).astype(np.float32)
        if prev_hist is not None:
            corr = cv2.compareHist(prev_hist, h, cv2.HISTCMP_CORREL)
            diff = float(np.mean(np.abs(gray - prev_gray)))
            # ayni odada farkli kameralar renk olarak benzer; piksel farki kesimi daha iyi yakaliyor
            if (diff > CUT_DIFF or corr < CUT_THRESHOLD) and t - cuts[-1] >= MIN_SHOT:
                cuts.append(t)
        prev_hist = h
        prev_gray = gray

        if i % FACE_EVERY == 0:
            _, faces = detector.detect(frame)
            found = []
            if faces is not None:
                for f in faces:
                    x, y, w, hh = f[:4]
                    if hh / ah < MIN_FACE_REL_H:
                        continue
                    found.append(((x + w / 2) * scale, (y + hh / 2) * scale, w * scale, hh * scale))
            face_samples.append((t, found))
        if i % JAW_EVERY == 0 and face_samples and len(face_samples[-1][1]) >= 2:
            small = cv2.cvtColor(cv2.resize(frame, (mw, mh)), cv2.COLOR_BGR2GRAY)
            motion_frames.append((t, cv2.GaussianBlur(small, (3, 3), 0).astype(np.int16)))
    duration = end - start
    cuts.append(duration)

    shots: list[Shot] = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        samples = [s for s in face_samples if a <= s[0] < b]
        dets = [(t, *f) for t, fs in samples for f in fs]
        slots = _cluster_slots(dets, len(samples), src_w)
        shots.append(Shot(t0=a, t1=b, slots=slots))

    # 2. adim: cok kisili cekimlerde agiz bolgesi hareketi - bas hareketi (profilde de calisir;
    # jawOpen modeli yandan konusan yuzleri okuyamiyordu)
    def box(slot: Slot, y0f: float, y1f: float, wf: float):
        x0 = int(max(0, (slot.cx - slot.fw * wf) / mscale))
        x1 = int(min(mw, (slot.cx + slot.fw * wf) / mscale))
        y0 = int(max(0, (slot.cy + slot.fh * y0f) / mscale))
        y1 = int(min(mh, (slot.cy + slot.fh * y1f) / mscale))
        return slice(y0, max(y0 + 1, y1)), slice(x0, max(x0 + 1, x1))

    for shot in shots:
        if len(shot.slots) < 2:
            continue
        frames = [(t, g) for t, g in motion_frames if shot.t0 <= t < shot.t1]
        boxes = [(box(s, 0.1, 0.7, 0.45), box(s, -0.55, -0.05, 0.45)) for s in shot.slots]
        for (t0, g0), (t1, g1) in zip(frames[:-1], frames[1:]):
            if t1 - t0 > 0.15:
                continue
            d = np.abs(g1 - g0)
            for slot, (mouth, upper) in zip(shot.slots, boxes):
                m = float(d[mouth].mean())
                u = float(d[upper].mean())
                slot.jaw.append((t1, max(0.0, m - 0.8 * u)))
    return shots, (src_w, src_h)


# ---------------- Konusmaci ----------------


def _activity(slot: Slot, t0: float, t1: float) -> float:
    vals = [v for t, v in slot.jaw if t0 <= t < t1]
    if len(vals) < 3:
        return 0.0
    return float(np.mean(vals))


POSITIONS = {"left": 0, "center": 1, "right": -1}


def _hinted_slot(shot: Shot, hints: list[tuple[float, float, str]], t: float) -> int | None:
    """Ipucu: (t0, t1, 'left'|'center'|'right') - kisiler soldan saga siralidir."""
    n = len(shot.slots)
    for a, b, pos in hints:
        if a <= t < b:
            idx = POSITIONS[pos]
            if pos == "center" and n < 3:
                return None
            return idx % n
    return None


def _speaker_timeline(shot: Shot, words: list[dict], hints: list[tuple[float, float, str]]
                      ) -> list[tuple[float, float, int | None]]:
    """Cekim icinde (t0, t1, konusan_slot_index) parcalari. Once klip tanimindaki konusmaci
    ipuclari, yoksa agiz hareketi (sadece belirgin baskinsa). Belirsizse None."""
    step = 0.5
    raw: list[tuple[float, int | None]] = []
    t = shot.t0
    while t < shot.t1:
        hinted = _hinted_slot(shot, hints, t + step / 2)
        if hinted is not None:
            raw.append((t, hinted))
            t += step
            continue
        w0, w1 = t - 0.4, t + step + 0.4
        speaking = any(w["end"] > t and w["start"] < t + step for w in words)
        acts = [_activity(s, w0, w1) for s in shot.slots]
        best = int(np.argmax(acts)) if acts else None
        ranked = sorted(acts, reverse=True)
        if not speaking or best is None or ranked[0] < 0.5 or (len(ranked) > 1 and ranked[0] < ranked[1] * 1.6):
            raw.append((t, None))
        else:
            raw.append((t, best))
        t += step

    # histerezis: yeni konusmaci en az SPEAKER_HOLD boyunca surmeli
    segs: list[list] = []
    cur = None
    for i, (t, spk) in enumerate(raw):
        if spk is None:
            spk = cur
        if spk != cur:
            hold_steps = int(SPEAKER_HOLD / step)
            ahead = [s for _, s in raw[i : i + hold_steps]]
            if cur is not None and ahead.count(spk) < max(1, hold_steps - 1):
                spk = cur
        if not segs or segs[-1][2] != spk:
            segs.append([t, min(t + step, shot.t1), spk])
        else:
            segs[-1][1] = min(t + step, shot.t1)
        cur = spk
    if segs:
        segs[0][0] = shot.t0
        segs[-1][1] = shot.t1
    return [tuple(s) for s in segs]


# ---------------- Kirpma dikdortgenleri ----------------


def _rect_for(slot: Slot, aspect: float, face_frac: float, face_y: float, src: tuple[int, int],
              min_h_frac: float) -> tuple[int, int, int, int]:
    """aspect = w/h. face_frac: yuzun panel yuksekligindeki orani. face_y: yuz merkezinin panelde dikey konumu."""
    sw, sh = src
    h = slot.fh / face_frac
    h = max(h, sh * min_h_frac)
    h = min(h, sh, sw / aspect)
    w = h * aspect
    x = slot.cx - w / 2
    y = slot.cy - h * face_y
    x = max(0, min(x, sw - w))
    y = max(0, min(y, sh - h))
    return (int(x) // 2 * 2, int(y) // 2 * 2, int(w) // 2 * 2, int(h) // 2 * 2)


FILL_ASPECT = 1080 / 1920
SPLIT_ASPECT = 1080 / 960
THREE_BOTTOM_ASPECT = 540 / 960


def _fill_rect(slot: Slot, src) -> tuple:
    # tek kisilik cekimde (yakin plan) yuz zaten buyuk -> tam yukseklik; genis cekimde biraz yaklas
    return _rect_for(slot, FILL_ASPECT, face_frac=0.20, face_y=0.36, src=src, min_h_frac=0.62)


def _split_rect(slot: Slot, src) -> tuple:
    return _rect_for(slot, SPLIT_ASPECT, face_frac=0.34, face_y=0.42, src=src, min_h_frac=0.34)


def _three_bottom_rect(slot: Slot, src) -> tuple:
    return _rect_for(slot, THREE_BOTTOM_ASPECT, face_frac=0.22, face_y=0.38, src=src, min_h_frac=0.34)


def _layout_for(kind: str, order: list[Slot], src) -> LayoutSeg:
    if kind == "fill":
        rects = [_fill_rect(order[0], src)]
    elif kind == "split":
        rects = [_split_rect(order[0], src), _split_rect(order[1], src)]
    else:  # three
        rects = [_split_rect(order[0], src), _three_bottom_rect(order[1], src), _three_bottom_rect(order[2], src)]
    return LayoutSeg(0, 0, kind, rects)


# ---------------- Plan ----------------


def _center_fill(src: tuple[int, int]) -> tuple[int, int, int, int]:
    sw, sh = src
    w = int(sh * FILL_ASPECT) // 2 * 2
    return ((sw - w) // 2 // 2 * 2, 0, w, sh)


def plan_layout(shots: list[Shot], src: tuple[int, int], words_rel: list[dict],
                hints: list[tuple[float, float, str]] | None = None,
                split_people: bool = True, noface: str = "letterbox") -> list[LayoutSeg]:
    """words_rel ve hints: aralik-relative zamanlar.
    split_people=False: cok kisili cekimler bolunmez, tam kare gosterilir (kimse tek basina one cikmaz).
    noface: yuz olmayan cekimlerde 'letterbox' (grafik/ekran icin) ya da 'center' (manzara icin tam ekran)."""
    out: list[LayoutSeg] = []
    toggle = 0
    for si, shot in enumerate(shots):
        n = len(shot.slots)
        if n == 0 and noface == "center":
            out.append(LayoutSeg(shot.t0, shot.t1, "fill", [_center_fill(src)], si))
            continue
        if n == 0 or (n >= 2 and not split_people):
            out.append(LayoutSeg(shot.t0, shot.t1, "letterbox", [], si))
            continue
        if n == 1:
            seg = _layout_for("fill", shot.slots, src)
            seg.t0, seg.t1, seg.shot = shot.t0, shot.t1, si
            out.append(seg)
            continue

        for s0, s1, spk in _speaker_timeline(shot, words_rel, hints or []):
            # uzun konusmaci parcalarini MAX_LAYOUT_SEG'lik ritimlere bol
            pieces = max(1, round((s1 - s0) / MAX_LAYOUT_SEG))
            edges = np.linspace(s0, s1, pieces + 1)
            for a, b in zip(edges[:-1], edges[1:]):
                speaker = shot.slots[spk] if spk is not None else None
                others = [s for s in shot.slots if s is not speaker]
                if speaker is None:
                    # kimse net konusmuyor -> herkesi goster (tepki anlari)
                    kind = "three" if n >= 3 else "split"
                    order = shot.slots[:3]
                else:
                    multi = "three" if n >= 3 else "split"
                    kind = "fill" if toggle % 2 == 0 else multi
                    if kind == "split" and n >= 3:
                        # en hareketli diger kisiyi alta koy
                        others.sort(key=lambda s: _activity(s, a, b), reverse=True)
                    order = [speaker] + others
                    toggle += 1
                seg = _layout_for(kind, order, src)
                seg.t0, seg.t1, seg.shot = float(a), float(b), si
                out.append(seg)

    # cok kisa parcalari bir oncekine kat
    merged: list[LayoutSeg] = []
    for seg in out:
        if merged and (seg.t1 - seg.t0) < MIN_LAYOUT_SEG and merged[-1].shot == seg.shot:
            merged[-1].t1 = seg.t1
        else:
            merged.append(seg)
    return merged


def describe(plan: list[LayoutSeg]) -> str:
    return "  ".join(f"[{s.t0:.1f}-{s.t1:.1f} {s.kind}]" for s in plan)
