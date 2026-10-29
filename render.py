"""Klip kesme, mediapipe ile yuz takipli 9:16 crop ve ASS altyazi gomme."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import random

from utils import (
    console,
    ffmpeg_path_escape,
    ffprobe_audio_samplerate,
    ffprobe_duration,
    ffprobe_resolution,
    run_subprocess,
)

TARGET_W = 1080
TARGET_H = 1920
TARGET_FPS = 30
FACE_SAMPLE_RATE = 2.0  # saniyede kac frame ornegi alinacak
SMOOTH_WINDOW = 5  # hareketli ortalama pencere boyutu (ornek sayisi)
MAX_CROP_POINTS = 20  # kayan kadraj icin nokta sayisi (yumusaklik/hiz dengesi)

FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
)
FACE_MODEL_PATH = Path("models") / "blaze_face_short_range.tflite"


def _ensure_face_model() -> Path:
    FACE_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not FACE_MODEL_PATH.exists():
        import urllib.request

        console.print("[cyan]Yuz tespit modeli indiriliyor (ilk calistirmada bir kez)...[/cyan]")
        urllib.request.urlretrieve(FACE_MODEL_URL, str(FACE_MODEL_PATH))
    return FACE_MODEL_PATH


@dataclass
class FacePoint:
    t: float  # klip-relative saniye
    x: float  # piksel, yatay merkez


def _track_face_centers(source_path: Path, start: float, end: float, frame_w: int, frame_h: int) -> list[FacePoint]:
    try:
        import cv2
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision
    except Exception as e:
        console.print(f"[yellow]mediapipe/opencv yuklenemedi, merkezden kirpilacak: {e}[/yellow]")
        return []

    try:
        model_path = _ensure_face_model()
    except Exception as e:
        console.print(f"[yellow]Yuz tespit modeli indirilemedi, merkezden kirpilacak: {e}[/yellow]")
        return []

    duration = end - start
    step = 1.0 / FACE_SAMPLE_RATE
    points: list[FacePoint] = []

    cap = cv2.VideoCapture(str(source_path))
    if not cap.isOpened():
        console.print("[yellow]Video acilamadi (opencv), merkezden kirpilacak.[/yellow]")
        return []

    base_options = mp_python.BaseOptions(model_asset_path=str(model_path))
    options = vision.FaceDetectorOptions(base_options=base_options, min_detection_confidence=0.5)

    try:
        with vision.FaceDetector.create_from_options(options) as detector:
            t_rel = 0.0
            while t_rel < duration:
                abs_ms = (start + t_rel) * 1000.0
                cap.set(cv2.CAP_PROP_POS_MSEC, abs_ms)
                ok, frame = cap.read()
                if ok and frame is not None:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    result = detector.detect(mp_image)
                    if result.detections:
                        best = max(
                            result.detections,
                            key=lambda d: d.bounding_box.width * d.bounding_box.height,
                        )
                        bbox = best.bounding_box
                        center_x = bbox.origin_x + bbox.width / 2
                        points.append(FacePoint(t=t_rel, x=center_x))
                t_rel += step
    finally:
        cap.release()

    return points


def _smooth_points(points: list[FacePoint]) -> list[FacePoint]:
    if len(points) <= 1:
        return points
    xs = [p.x for p in points]
    smoothed = []
    n = len(xs)
    half = SMOOTH_WINDOW // 2
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        avg = sum(xs[lo:hi]) / (hi - lo)
        smoothed.append(FacePoint(t=points[i].t, x=avg))
    return smoothed


def _downsample(points: list[FacePoint], max_points: int) -> list[FacePoint]:
    if len(points) <= max_points:
        return points
    step = len(points) / max_points
    result = []
    i = 0.0
    while int(i) < len(points):
        result.append(points[int(i)])
        i += step
    if result[-1].t != points[-1].t:
        result.append(points[-1])
    return result


def _build_crop_x_expr(points: list[FacePoint], crop_w: int, frame_w: int, duration: float) -> str:
    if not points:
        center = frame_w / 2
        x = max(0, min(center - crop_w / 2, frame_w - crop_w))
        return f"{x:.2f}"

    pts = list(points)
    if pts[0].t > 0:
        pts.insert(0, FacePoint(t=0.0, x=pts[0].x))
    if pts[-1].t < duration:
        pts.append(FacePoint(t=duration, x=pts[-1].x))

    def clamp_x(center: float) -> float:
        return max(0.0, min(center - crop_w / 2, frame_w - crop_w))

    last_x = clamp_x(pts[-1].x)
    expr = f"{last_x:.2f}"
    for i in range(len(pts) - 2, -1, -1):
        t_a, x_a = pts[i].t, clamp_x(pts[i].x)
        t_b, x_b = pts[i + 1].t, clamp_x(pts[i + 1].x)
        dt = t_b - t_a
        slope = (x_b - x_a) / dt if dt > 1e-6 else 0.0
        seg = f"({x_a:.2f}+({slope:.4f}*(t-{t_a:.3f})))"
        expr = f"if(lt(t,{t_b:.3f}),{seg},{expr})"
    return expr


FACE_GAP_MIN_DURATION = 1.5  # bu sureden kisa "yuz yok" araliklari yoksay (titremeyi onler)
FACE_GAP_PAD = 0.3  # letterbox'a gecisi biraz erken/gec yapip ani kesimi yumusatir


def _compute_noface_windows(raw_points: list[FacePoint], duration: float, step: float) -> list[tuple[float, float]]:
    """Yuz tespit edilemeyen (grafik/chart agirlikli) zaman araliklarini bulur; bu araliklarda
    siki yuz-takipli kirpma yerine tam genislik + bulanik dolgu (letterbox) kullanilacak."""
    detected_steps = {round(p.t / step) for p in raw_points}
    total_steps = int(duration // step) + 1

    raw_gaps: list[tuple[float, float]] = []
    run_start: float | None = None
    for i in range(total_steps):
        t = min(i * step, duration)
        if i not in detected_steps:
            if run_start is None:
                run_start = t
        elif run_start is not None:
            raw_gaps.append((run_start, t))
            run_start = None
    if run_start is not None:
        raw_gaps.append((run_start, duration))

    gaps = [(max(0.0, s - FACE_GAP_PAD), min(duration, e + FACE_GAP_PAD)) for s, e in raw_gaps]
    gaps = [(s, e) for s, e in gaps if e - s >= FACE_GAP_MIN_DURATION]

    merged: list[tuple[float, float]] = []
    for s, e in gaps:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def compute_crop_expression(
    source_path: Path, start: float, end: float, target_w: int = TARGET_W, target_h: int = TARGET_H
) -> tuple[str, int, int, list[tuple[float, float]]]:
    """Donen: (x_ifade, crop_w, crop_h, noface_windows). target_w/target_h istenen cikti
    oranini belirler (split-screen'de ust/alt yari icin 1080x960 gibi farkli bir oran gerekebilir).
    noface_windows: klip-relative (start,end) araliklari - bu araliklarda yuz bulunamadi, cagiran
    kod isterse bu kisimlarda kirpma yerine letterbox uygulayabilir."""
    frame_w, frame_h = ffprobe_resolution(source_path)
    crop_h = frame_h
    crop_w = min(round(frame_h * target_w / target_h / 2) * 2, frame_w)

    raw_points = _track_face_centers(source_path, start, end, frame_w, frame_h)
    duration = end - start
    noface_windows = _compute_noface_windows(raw_points, duration, 1.0 / FACE_SAMPLE_RATE)

    smoothed = _smooth_points(raw_points)
    smoothed = _downsample(smoothed, MAX_CROP_POINTS)
    x_expr = _build_crop_x_expr(smoothed, crop_w, frame_w, duration)
    return x_expr, crop_w, crop_h, noface_windows


# ---------------- ASS altyazi ----------------

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,84,&H00FFFFFF,&H0000FFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,7,0,2,60,60,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

HIGHLIGHT_COLOR = r"{\c&H00FFFF&}"
RESET_COLOR = r"{\c&HFFFFFF&}"


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 0
        s += 1
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _clean_word(word: str) -> str:
    return word.replace("{", "").replace("}", "").strip()


def generate_ass(
    words: list[dict[str, Any]], clip_start: float, clip_end: float, out_path: Path, margin_v: int = 260
) -> None:
    duration = clip_end - clip_start
    rel_words = []
    for w in words:
        ws, we = w["start"] - clip_start, w["end"] - clip_start
        if we <= 0 or ws >= duration:
            continue
        rel_words.append({"word": _clean_word(w["word"]), "start": max(0.0, ws), "end": min(duration, we)})

    lines = [ASS_HEADER.replace(",260,1", f",{margin_v},1")]
    group_size = 3
    for i in range(0, len(rel_words), group_size):
        group = rel_words[i : i + group_size]
        if not group:
            continue
        block_start = group[0]["start"]
        block_end = group[-1]["end"]
        base_text = " ".join(g["word"] for g in group)
        lines.append(
            f"Dialogue: 0,{_ass_time(block_start)},{_ass_time(block_end)},Default,,0,0,0,,{base_text}"
        )
        for w in group:
            parts = []
            for g in group:
                if g is w:
                    parts.append(f"{HIGHLIGHT_COLOR}{g['word']}{RESET_COLOR}")
                else:
                    parts.append(g["word"])
            hl_text = " ".join(parts)
            lines.append(
                f"Dialogue: 1,{_ass_time(w['start'])},{_ass_time(w['end'])},Default,,0,0,0,,{hl_text}"
            )

    out_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------- Hook kelimesi ses efekti ----------------

SFX_DIR = Path("assets") / "sfx"
SFX_DING_PATH = SFX_DIR / "ding.wav"
SFX_VOLUME = 0.35
SFX_MIN_GAP = 0.35  # ayni ana cok yakin efektleri birlestir (cakismasin)
SFX_MAX_COUNT = 4


def _ensure_sfx_assets() -> Path:
    """Kucuk bir 'ding' vurgu sesini ffmpeg lavfi ile sentezler (harici dosya indirmez)."""
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    if not SFX_DING_PATH.exists():
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=1800:duration=0.22",
            "-af", "afade=t=in:st=0:d=0.01,afade=t=out:st=0.08:d=0.14",
            "-ac", "2",
            str(SFX_DING_PATH),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RuntimeError(f"SFX olusturulamadi: {result.stderr[-1000:]}")
    return SFX_DING_PATH


def _norm_word(w: str) -> str:
    return re.sub(r"[^\w]", "", w, flags=re.UNICODE).lower()


def _find_hook_word_times(
    hook_words: list[str], words: list[dict[str, Any]], clip_start: float, clip_end: float
) -> list[float]:
    """hook_words listesindeki her kelimenin klip icinde ilk gectigi zamani (klip-relative) bulur."""
    # Gemini bazen tek kelime yerine ifade dondurebiliyor ("lost control of" gibi); boyle
    # durumlarda ifadeyi kelimelerine bolup icindeki ilk eslesen kelimeyi kullaniyoruz.
    targets: list[str] = []
    for hw in hook_words:
        whole = _norm_word(hw)
        if whole:
            targets.append(whole)
        for part in hw.split():
            norm_part = _norm_word(part)
            if norm_part and norm_part != whole:
                targets.append(norm_part)

    if not targets:
        return []

    duration = clip_end - clip_start
    used_starts: set[float] = set()
    times: list[float] = []
    for target in targets:
        for w in words:
            if w["start"] in used_starts or _norm_word(w["word"]) != target:
                continue
            t_rel = w["start"] - clip_start
            if 0.0 <= t_rel < duration:
                times.append(t_rel)
                used_starts.add(w["start"])
                break

    times.sort()
    deduped: list[float] = []
    for t in times:
        if not deduped or t - deduped[-1] > SFX_MIN_GAP:
            deduped.append(t)
    return deduped[:SFX_MAX_COUNT]


def _build_sfx_pass_cmd(
    input_video: Path, ass_escaped: str, sfx_times: list[float], sfx_path: Path, out_path: Path
) -> list[str]:
    """Altyazi + (varsa) hook kelimesi ses efektlerini tek pasoda uygulayan ffmpeg komutu."""
    inputs = ["-i", str(input_video)]

    if not sfx_times:
        cmd = [
            "ffmpeg", "-y", *inputs,
            "-vf", f"subtitles='{ass_escaped}'",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            str(out_path),
        ]
        return cmd

    filter_parts = [f"[0:v]subtitles='{ass_escaped}'[vout]"]
    sfx_labels = []
    for i, t in enumerate(sfx_times):
        inputs += ["-i", str(sfx_path)]
        delay_ms = max(0, round(t * 1000))
        label = f"sfx{i}"
        filter_parts.append(f"[{i + 1}:a]adelay=all=1:delays={delay_ms},volume={SFX_VOLUME}[{label}]")
        sfx_labels.append(f"[{label}]")

    mix_inputs = "[0:a]" + "".join(sfx_labels)
    filter_parts.append(
        f"{mix_inputs}amix=inputs={len(sfx_times) + 1}:duration=first:dropout_transition=0:normalize=0[aout]"
    )
    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    return cmd


LETTERBOX_BLUR_SIGMA = 25


def _build_pass1_filter(
    crop_w: int, crop_h: int, x_expr: str, noface_windows: list[tuple[float, float]]
) -> tuple[bool, str]:
    """Pass1 filtresini kurar. noface_windows bossa eski basit crop+scale zinciri (-vf ile)
    dondurulur. Doluysa, yuz bulunan araliklarda siki yuz-takipli kirpma, yuz bulunamayan
    (grafik/chart agirlikli) araliklarda ise hicbir sey kesilmeyen tam-genislik + bulanik
    dolgu (letterbox) gosteren bir filter_complex grafigi kurulur ve iki tretman zaman
    bazli overlay ile birbirine gecirilir. Donen: (filter_complex_mi, filtre_metni)."""
    crop_vf = f"crop=w={crop_w}:h={crop_h}:x='{x_expr}':y=0,scale={TARGET_W}:{TARGET_H},setsar=1,fps={TARGET_FPS}"
    if not noface_windows:
        return False, crop_vf

    enable_expr = "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in noface_windows)
    graph = (
        f"[0:v]split=2[base][letter_src];"
        f"[base]{crop_vf}[vA];"
        f"[letter_src]split=2[bg][fg];"
        f"[bg]scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,"
        f"crop={TARGET_W}:{TARGET_H},gblur=sigma={LETTERBOX_BLUR_SIGMA},setsar=1,fps={TARGET_FPS}[bgblur];"
        f"[fg]scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,setsar=1,fps={TARGET_FPS}[fgfit];"
        f"[bgblur][fgfit]overlay=(W-w)/2:(H-h)/2[vB];"
        f"[vA][vB]overlay=x=0:y=0:enable='{enable_expr}'[vout]"
    )
    return True, graph


# ---------------- Hook mansheti (ust banner, mevcut klibin uzerine ek pas) ----------------

HEADLINE_ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 1
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Headline,Arial,66,&H0000FFFF,&H0000FFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,3,18,0,8,50,50,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def generate_headline_ass(headline: str, duration: float, out_path: Path) -> None:
    text = headline.strip().replace("\n", "\\N")
    line = f"Dialogue: 0,{_ass_time(0.0)},{_ass_time(duration)},Headline,,0,0,0,,{text}"
    out_path.write_text(HEADLINE_ASS_HEADER + line, encoding="utf-8")


def add_headline_overlay(
    in_path: Path, headline: str, out_path: Path, tmp_dir: Path, display_seconds: float | None = None
) -> None:
    """Zaten render edilmis bir klibin uzerine ust kisma bir 'hook manseti'
    (siyah kutu + kalin sari yazi) yakan hizli tek gecis. display_seconds verilirse
    manset sadece o kadar sure gorunur, verilmezse klip boyunca kalir. Sesi
    degistirmeden kopyalar."""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    duration = ffprobe_duration(in_path)
    if display_seconds is not None:
        duration = min(duration, display_seconds)
    ass_path = tmp_dir / f"{out_path.stem}_headline.ass"
    generate_headline_ass(headline, duration, ass_path)
    ass_escaped = ffmpeg_path_escape(ass_path)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(in_path),
        "-vf", f"subtitles='{ass_escaped}'",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg hook manseti basarisiz: {out_path.name}\n{result.stderr[-2000:]}")


# ---------------- AI anlatim girisi (Chatterbox TTS, orijinallik icin gercek katma deger) ----------------

_CHATTERBOX_MODEL = None  # tembel-yuklenen tekil model (batch icinde tekrar tekrar yuklemeyi onler)

NARRATION_EXAGGERATION = 0.85
NARRATION_CFG_WEIGHT = 0.4

NARRATION_ASS_STYLE = (
    "Style: Narration,Arial,72,&H00FFFFFF,&H00FFFFFF,&H001818B2,&H001818B2,"
    "-1,0,0,0,100,100,0,0,3,20,0,5,60,60,0,1"
)


def _get_chatterbox_model():
    global _CHATTERBOX_MODEL
    if _CHATTERBOX_MODEL is None:
        from chatterbox.tts import ChatterboxTTS

        console.print("[cyan]Chatterbox TTS modeli yukleniyor (ilk klipte bir kez)...[/cyan]")
        _CHATTERBOX_MODEL = ChatterboxTTS.from_pretrained(device="cpu")
    return _CHATTERBOX_MODEL


def synthesize_narration(text: str, out_path: Path) -> float:
    """Chatterbox TTS ile kisa bir anlatim/giris sesi uretir. Suresini (saniye) dondurur."""
    import torchaudio as ta

    model = _get_chatterbox_model()
    wav = model.generate(text, exaggeration=NARRATION_EXAGGERATION, cfg_weight=NARRATION_CFG_WEIGHT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ta.save(str(out_path), wav, model.sr)
    return ffprobe_duration(out_path)


def add_headline_and_narration(
    in_path: Path,
    headline: str,
    narration_text: str,
    out_path: Path,
    tmp_dir: Path,
) -> None:
    """Zaten render edilmis bir klibin uzerine: (1) ust kisimda sabit hook manseti,
    (2) klip basinda Chatterbox TTS ile seslendirilen kisa bir 'anlatim' (orijinal klip
    sesi bu sure boyunca kisilir), (3) o anlatimi ekranda ortalanmis, konusma bitince
    kaybolan kirmizi kutulu bir altyazi olarak gosterir. Bu, sadece caption/crop
    eklemekten farkli olarak gercek bir 'katma deger' katmani sayilir (bkz. orijinallik
    arastirmasi) ve TTS destekli olmayan (orn. 'It's Personal' gibi) kampanyalarda
    KULLANILMAMALIDIR."""
    tmp_dir.mkdir(parents=True, exist_ok=True)

    narration_path = tmp_dir / f"{out_path.stem}_narration.wav"
    narr_duration = synthesize_narration(narration_text, narration_path)
    duck_end = narr_duration + 0.2
    # Manset de anlatimla birlikte kaybolur (klip boyunca degil) - anlatim bitince birkac
    # saniye daha kalip sonra kayboluyor, boylece "hook girisi" fazi net bir sekilde kapanir.
    headline_end = narr_duration + 1.5

    ass_path = tmp_dir / f"{out_path.stem}_headline.ass"
    narration_display = narration_text.strip().replace("\n", "\\N")
    headline_display = headline.strip().replace("\n", "\\N")
    # HEADLINE_ASS_HEADER zaten kendi [Events] basligini iceriyor; onu atip yeniden kuruyoruz
    # ki Narration stilini de [V4+ Styles] altina ekleyebilelim.
    header_no_events = HEADLINE_ASS_HEADER.split("[Events]")[0].rstrip()
    combined_ass = (
        header_no_events
        + "\n"
        + NARRATION_ASS_STYLE
        + "\n\n"
        + "[Events]\n"
        + "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        + f"Dialogue: 0,{_ass_time(0.0)},{_ass_time(headline_end)},Headline,,0,0,0,,{headline_display}\n"
        + f"Dialogue: 1,{_ass_time(0.0)},{_ass_time(narr_duration)},Narration,,0,0,0,,{narration_display}\n"
    )
    ass_path.write_text(combined_ass, encoding="utf-8")
    ass_escaped = ffmpeg_path_escape(ass_path)

    filter_complex = (
        f"[0:v]subtitles='{ass_escaped}'[vout];"
        f"[0:a]volume=0.12:enable='lt(t,{duck_end:.2f})'[origduck];"
        f"[1:a]aecho=0.8:0.7:40:0.25,acompressor=threshold=-18dB:ratio=3:attack=5:release=50,adelay=0|0[narr];"
        f"[origduck][narr]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(in_path),
        "-i", str(narration_path),
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg anlatim gecisi basarisiz: {out_path.name}\n{result.stderr[-2000:]}")


# ---------------- Sabit marka/avatar watermark ----------------

AVATAR_LOGO_PATH = Path("work") / "branding" / "avatar_logo_v1.png"
AVATAR_SIZE = 110
AVATAR_MARGIN = 28


def add_avatar_overlay(in_path: Path, out_path: Path, logo_path: Path = AVATAR_LOGO_PATH) -> None:
    """Klibin sol ust kosesine sabit boyutlu bir marka/avatar rozeti yakar (tum klip
    boyunca). Bu, sadece caption/crop degil sabit bir 'ozgun piksel imzasi' sayilan bir
    kurgu sablonu katmani ekler."""
    filter_complex = (
        f"[1:v]scale={AVATAR_SIZE}:{AVATAR_SIZE}[logo];"
        f"[0:v][logo]overlay={AVATAR_MARGIN}:{AVATAR_MARGIN}[vout]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(in_path),
        "-i", str(logo_path),
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "copy",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg avatar-overlay basarisiz: {out_path.name}\n{result.stderr[-2000:]}")


# ---------------- B-roll (konuyu destekleyen gorsel katman) ----------------

PEXELS_API_URL = "https://api.pexels.com/v1/search"


def fetch_pexels_photo(query: str, out_path: Path) -> bool:
    """Pexels'ten (gercek stok fotograf) ilgili sorguya en uygun fotografi indirir.
    Basarili olursa True, API key yoksa veya sonuc bulunamazsa False doner (cagiran
    taraf bu durumda AI-uretimine ya da broll'u atlamaya dusebilir)."""
    import os
    import requests
    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        console.print("[yellow]PEXELS_API_KEY bulunamadi, broll atlanacak.[/yellow]")
        return False

    try:
        resp = requests.get(
            PEXELS_API_URL,
            headers={"Authorization": api_key},
            params={"query": query, "per_page": 1, "orientation": "landscape"},
            timeout=15,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        if not photos:
            return False
        img_url = photos[0]["src"]["large"]
        img_resp = requests.get(img_url, timeout=20)
        img_resp.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(img_resp.content)
        return True
    except Exception as e:
        console.print(f"[yellow]Pexels indirme hatasi ({query}): {e}[/yellow]")
        return False


BROLL_WIDTH_RATIO = 0.78
BROLL_HEIGHT_RATIO = 0.32
BROLL_DURATION = 2.0
BROLL_Y_OFFSET_RATIO = 0.60  # ekranin ustunden bu oranda asagida baslar (govde hizasi, yuzu kapatmasin diye)


def compute_broll_insert_time(
    hook_words: list[str],
    words: list[dict[str, Any]],
    clip_start: float,
    clip_end: float,
) -> float:
    """B-roll'un gosterilecegi zamani hesaplar: hook kelimenin klip-ici zamanini bulur,
    ama kullanicinin istegi geregi B-roll'larin cogu klibin ilk yarisinda kalsin diye
    bu zamani klip suresinin %45'i ile sinirlar (kirpma). Hook kelime bulunamazsa
    klibin %25'inde sabit bir zaman doner."""
    duration = clip_end - clip_start
    cap = duration * 0.65  # sert sinir degil, sadece asiri uc bir deger olmasin diye
    floor = min(7.0, cap)  # anlatim (narration) penceresiyle cakismasin diye
    punch_times = _find_hook_word_times(hook_words, words, clip_start, clip_end)
    target = punch_times[0] if punch_times else duration * 0.25
    return max(floor, min(target, cap))


def add_broll_insert(in_path: Path, broll_image_path: Path, insert_time: float, out_path: Path) -> None:
    """Belirtilen zaman aninda, konusmaciyi tamamen kapatmadan, ekranin orta-ust
    bolgesine konuyla ilgili bir gorseli BROLL_DURATION saniye boyunca bindirir.
    Bu, tek kaynaktan kesintisiz goruntu yerine 'konuyu destekleyen ek gorsel'
    katmani ekleyerek dokumanin bahsettigi 'mini-belgesel' dogrulugunu saglar."""
    frame_w, frame_h = ffprobe_resolution(in_path)
    box_w = round(frame_w * BROLL_WIDTH_RATIO / 2) * 2
    box_h = round(box_w * BROLL_HEIGHT_RATIO / 2) * 2
    x = (frame_w - box_w) // 2
    y = round(frame_h * BROLL_Y_OFFSET_RATIO)
    end_time = insert_time + BROLL_DURATION

    filter_complex = (
        f"[1:v]scale={box_w}:{box_h}:force_original_aspect_ratio=increase,"
        f"crop={box_w}:{box_h},format=yuva420p,"
        f"drawbox=x=0:y=0:w={box_w}:h={box_h}:color=white:t=6[broll];"
        f"[0:v][broll]overlay=x={x}:y={y}:enable='between(t,{insert_time:.3f},{end_time:.3f})'[vout]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(in_path),
        "-i", str(broll_image_path),
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "copy",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg broll-insert basarisiz: {out_path.name}\n{result.stderr[-2000:]}")


# ---------------- Pattern-interrupt (hook kelimesinde zoom-punch) ----------------

PUNCH_ZOOM_FACTOR = 1.15
PUNCH_DURATION = 0.35  # zoom-punch ne kadar sureyle gorunur kalir (saniye)


def add_pattern_interrupts(
    in_path: Path,
    hook_words: list[str],
    words: list[dict[str, Any]],
    clip_start: float,
    clip_end: float,
    out_path: Path,
) -> None:
    """Hook kelimesi gectigi anlarda kisa bir zoom-punch (ani yakinlasma) ekler. Sabit
    cikti boyutunda iki sabit-boyutlu goruntuyu (normal/zoomlu) overlay+enable ile
    ANLIK olarak degistirerek calisir (dinamik crop/scale boyutu KULLANMAZ), bu yuzden
    render_clip'teki kayan yuz-takip kirpmasindan farkli olarak kirilgan degildir.
    Beyaz flash kullanici istegiyle kaldirildi. hook_words bossa ya da eslesme
    bulunamazsa video degismeden kopyalanir."""
    punch_times = _find_hook_word_times(hook_words, words, clip_start, clip_end)
    if not punch_times:
        cmd = ["ffmpeg", "-y", "-i", str(in_path), "-c", "copy", str(out_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg kopyalama basarisiz: {out_path.name}\n{result.stderr[-2000:]}")
        return

    frame_w, frame_h = ffprobe_resolution(in_path)
    zoom_w = round(frame_w * PUNCH_ZOOM_FACTOR / 2) * 2
    zoom_h = round(frame_h * PUNCH_ZOOM_FACTOR / 2) * 2
    crop_x = (zoom_w - frame_w) // 2
    crop_y = (zoom_h - frame_h) // 2

    zoom_expr = "+".join(f"between(t,{t:.3f},{t + PUNCH_DURATION:.3f})" for t in punch_times)

    filter_complex = (
        f"[0:v]split=2[base][zsrc];"
        f"[zsrc]scale={zoom_w}:{zoom_h},crop={frame_w}:{frame_h}:{crop_x}:{crop_y}[zoomed];"
        f"[base][zoomed]overlay=enable='{zoom_expr}'[vout]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(in_path),
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "copy",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg pattern-interrupt basarisiz: {out_path.name}\n{result.stderr[-2000:]}")


FINGERPRINT_SPEED_RANGE = (1.03, 1.05)
FINGERPRINT_GRAIN_RANGE = (2, 3)


def apply_fingerprint_break(in_path: Path, out_path: Path) -> None:
    """Video+sesi hafifce hizlandirip (perdeyi de dogal olarak kaydirarak) ve ince bir
    grain/renk katmani ekleyerek Instagram/TikTok'un piksel ve ses parmak izi eslestirmesini
    kirar. Her cagrida hiz ve grain miktari kucuk bir aralikta rastgele secilir ki klipler
    kendi aralarinda da ayni sabit imzayi tasimasin."""
    speed = random.uniform(*FINGERPRINT_SPEED_RANGE)
    grain = random.uniform(*FINGERPRINT_GRAIN_RANGE)
    sample_rate = ffprobe_audio_samplerate(in_path)

    filter_complex = (
        f"[0:v]setpts=PTS/{speed:.4f},eq=contrast=1.03:saturation=1.05,"
        f"noise=alls={grain:.1f}:allf=t[v];"
        f"[0:a]asetrate={sample_rate}*{speed:.4f},aresample={sample_rate}[a]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(in_path),
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-maxrate", "8M", "-bufsize", "16M",
        "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg fingerprint-break basarisiz: {out_path.name}\n{result.stderr[-2000:]}")


# ---------------- Ana render fonksiyonu ----------------


def render_clip(
    source_path: Path,
    clip: dict[str, Any],
    words: list[dict[str, Any]],
    out_path: Path,
    tmp_dir: Path,
) -> None:
    start, end = clip["start"], clip["end"]
    duration = end - start

    tmp_dir.mkdir(parents=True, exist_ok=True)
    ass_path = tmp_dir / f"{out_path.stem}.ass"
    generate_ass(words, start, end, ass_path)

    x_expr, crop_w, crop_h, noface_windows = compute_crop_expression(source_path, start, end)
    ass_escaped = ffmpeg_path_escape(ass_path)

    # Hizli+hassas seek: buyuk atlamayi -i'den once (keyframe'e yakin, hizli),
    # kalan kucuk farki -i'den sonra yapariz (-i sonrasi -ss tam ornek-dogru kirpar).
    # Sadece -i'den once -ss kullanmak (input seek) bazen kelimenin basini/sonunu
    # kirpiyordu; bu kombinasyon hem hizli hem tam zamanindan kesiyor.
    coarse_seek = max(0.0, start - 5.0)
    fine_seek = start - coarse_seek

    # IKI ASAMALI RENDER: crop'un x ifadesi 't' icerdiginde (kayan/yuz-takipli kirpma),
    # ayni filtre zincirinde hemen ardindan gelen subtitles filtresi bu ffmpeg
    # surumunde sessizce devre disi kaliyor (hata vermeden altyazi kayboluyor).
    # Bunu asmak icin once kirpma+olcekleme ayri bir gecişte "yakilir", sonra
    # ikinci gecişte (artik dinamik ifade yok) altyazi guvenle gomulur.
    interim_path = tmp_dir / f"{out_path.stem}_precrop.mp4"

    use_filter_complex, pass1_filter = _build_pass1_filter(crop_w, crop_h, x_expr, noface_windows)
    cmd_pass1 = [
        "ffmpeg", "-y",
        "-ss", f"{coarse_seek:.3f}",
        "-i", str(source_path),
        "-ss", f"{fine_seek:.3f}",
        "-t", f"{duration:.3f}",
    ]
    if use_filter_complex:
        cmd_pass1 += ["-filter_complex", pass1_filter, "-map", "[vout]", "-map", "0:a"]
    else:
        cmd_pass1 += ["-vf", pass1_filter]
    cmd_pass1 += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        str(interim_path),
    ]
    result1 = subprocess.run(cmd_pass1, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result1.returncode != 0:
        raise RuntimeError(f"ffmpeg crop gecisi basarisiz: {out_path.name}\n{result1.stderr[-2000:]}")

    sfx_times: list[float] = []  # ding efekti kullanicinin istegiyle kaldirildi
    cmd = _build_sfx_pass_cmd(interim_path, ass_escaped, sfx_times, SFX_DING_PATH, out_path)

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg render basarisiz: {out_path.name}\n{result.stderr[-2000:]}")

    interim_path.unlink(missing_ok=True)


# ---------------- Split-screen render (ust: klip, alt: gameplay) ----------------

SPLIT_HALF_H = TARGET_H // 2  # 960


def render_split_clip(
    source_path: Path,
    clip: dict[str, Any],
    words: list[dict[str, Any]],
    gameplay_path: Path,
    out_path: Path,
    tmp_dir: Path,
    gameplay_offset: float = 0.0,
) -> None:
    """Ust yaride yuz-takipli klip, alt yaride sessiz gameplay goruntusu (Subway Surfers vb.)."""
    start, end = clip["start"], clip["end"]
    duration = end - start

    tmp_dir.mkdir(parents=True, exist_ok=True)
    ass_path = tmp_dir / f"{out_path.stem}.ass"
    generate_ass(words, start, end, ass_path, margin_v=SPLIT_HALF_H + 80)
    ass_escaped = ffmpeg_path_escape(ass_path)

    x_expr, crop_w, crop_h, _noface_windows = compute_crop_expression(source_path, start, end, TARGET_W, SPLIT_HALF_H)

    coarse_seek = max(0.0, start - 5.0)
    fine_seek = start - coarse_seek

    top_path = tmp_dir / f"{out_path.stem}_top.mp4"
    bottom_path = tmp_dir / f"{out_path.stem}_bottom.mp4"
    stacked_path = tmp_dir / f"{out_path.stem}_stacked.mp4"

    # UST YARI: yuz-takipli kayan kirpma + 1080x960'a olcek (kendi tek pasinda,
    # ayni bilinen ffmpeg hatasindan kacinmak icin bunu tek basina isliyoruz).
    top_vf = f"crop=w={crop_w}:h={crop_h}:x='{x_expr}':y=0,scale={TARGET_W}:{SPLIT_HALF_H},setsar=1,fps={TARGET_FPS}"
    cmd_top = [
        "ffmpeg", "-y",
        "-ss", f"{coarse_seek:.3f}",
        "-i", str(source_path),
        "-ss", f"{fine_seek:.3f}",
        "-t", f"{duration:.3f}",
        "-vf", top_vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        str(top_path),
    ]
    r = subprocess.run(cmd_top, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg split ust yari basarisiz: {out_path.name}\n{r.stderr[-2000:]}")

    # ALT YARI: gameplay goruntusunden sabit merkez kirpma (dinamik degil, riskli degil),
    # ses kapali.
    gp_w, gp_h = ffprobe_resolution(gameplay_path)
    bottom_crop_w = min(round(gp_h * TARGET_W / SPLIT_HALF_H / 2) * 2, gp_w)
    bottom_x = (gp_w - bottom_crop_w) // 2
    bottom_vf = f"crop=w={bottom_crop_w}:h={gp_h}:x={bottom_x}:y=0,scale={TARGET_W}:{SPLIT_HALF_H},setsar=1,fps={TARGET_FPS}"
    cmd_bottom = [
        "ffmpeg", "-y",
        "-ss", f"{gameplay_offset:.3f}",
        "-i", str(gameplay_path),
        "-t", f"{duration:.3f}",
        "-an",
        "-vf", bottom_vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        str(bottom_path),
    ]
    r = subprocess.run(cmd_bottom, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg split alt yari basarisiz: {out_path.name}\n{r.stderr[-2000:]}")

    # BIRLESTIR: ust+alt vstack, ses sadece ustten.
    cmd_stack = [
        "ffmpeg", "-y",
        "-i", str(top_path),
        "-i", str(bottom_path),
        "-filter_complex", "[0:v][1:v]vstack=inputs=2[v]",
        "-map", "[v]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        str(stacked_path),
    ]
    r = subprocess.run(cmd_stack, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg split birlestirme basarisiz: {out_path.name}\n{r.stderr[-2000:]}")

    # ALTYAZI: son pasta, dinamik crop artik yok (guvenli). Ding efekti kaldirildi.
    sfx_times: list[float] = []
    cmd_sub = _build_sfx_pass_cmd(stacked_path, ass_escaped, sfx_times, SFX_DING_PATH, out_path)
    r = subprocess.run(cmd_sub, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg split altyazi basarisiz: {out_path.name}\n{r.stderr[-2000:]}")

    for p in (top_path, bottom_path, stacked_path):
        p.unlink(missing_ok=True)
