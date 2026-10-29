"""Kronometre HUD'u: ustte buyuk, rakamlari akan 'T+ zaman' sayaci + altinda enerji bari.
Sahne basina spec: "hud": {"timer": (bas, son) saniye, "energy": (bas, son)}. Buyuk olcek farklari
logaritmik akar (0.00001 s -> 0.001 s), izleyici bir sonraki ani beklesin diye rakamlar surekli doner."""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
FPS = 30
MONO = "C:/Windows/Fonts/consolab.ttf"
BLACK = "assets/fonts/Montserrat-Black.ttf"

CYAN = (0, 225, 255)
YELLOW = (255, 214, 0)
ORANGE = (255, 120, 20)
TOP = 190  # sayacin ust kenari


def _lerp(a: float, b: float, f: float) -> float:
    if a > 0 and b > 0 and max(a, b) / min(a, b) > 20:
        return a * (b / a) ** f
    return a + (b - a) * f


def _fmt_time(v: float) -> str:
    """Kucuk degerlerde sabit genislikte ondalik: rakamlar akarken yazi zipla(ma)sin."""
    if v < 0.001:
        return f"{v:.6f}"
    if v < 1:
        return f"{v:.4f}"
    return f"{v:05.2f}"


def draw_frame(t: float, timer: float, energy: float, energy_max: float, t_start: float,
               fonts: dict, energy_label: str) -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    appear = min(1.0, max(0.0, (t - t_start) / 0.3))
    if appear <= 0:
        return img
    d = ImageDraw.Draw(img)
    # ust etiket
    label = "TIME SINCE IMPACT"
    lw = d.textlength(label, font=fonts["mono_s"])
    d.text(((W - lw) / 2, TOP), label, font=fonts["mono_s"], fill=(*CYAN, int(255 * appear)))
    # buyuk sayac: "T+" sari, rakamlar beyaz, "s" soluk
    pre, num, unit = "T+", _fmt_time(timer), " s"
    fb = fonts["big"]
    wp, wn, wu = d.textlength(pre, font=fb), d.textlength(num, font=fb), d.textlength(unit, font=fonts["mid"])
    x = (W - (wp + wn + wu)) / 2
    y = TOP + 44
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.text((x, y), pre + num, font=fb, fill=(255, 255, 255, int(150 * appear)))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(img)
    a = int(255 * appear)
    d.text((x, y), pre, font=fb, fill=(*YELLOW, a), stroke_width=4, stroke_fill=(0, 0, 0, a))
    d.text((x + wp, y), num, font=fb, fill=(255, 255, 255, a), stroke_width=4, stroke_fill=(0, 0, 0, a))
    d.text((x + wp + wn, y + 44), unit, font=fonts["mid"], fill=(220, 220, 220, a),
           stroke_width=3, stroke_fill=(0, 0, 0, a))

    # enerji bari
    bw, bh = 620, 22
    bx, by = (W - bw) // 2, y + 170
    frac = 0.0 if energy_max <= 0 else min(1.0, energy / energy_max)
    d.rounded_rectangle((bx, by, bx + bw, by + bh), 11, fill=(0, 0, 0, int(150 * appear)),
                        outline=(*ORANGE, int(200 * appear)), width=3)
    fill_w = int((bw - 8) * frac)
    if fill_w > 6:
        hot = (255, int(200 - 150 * frac), 30, a)
        d.rounded_rectangle((bx + 4, by + 4, bx + 4 + fill_w, by + bh - 4), 7, fill=hot)
    txt = f"ENERGY  {round(energy):,}\u00d7 {energy_label}"
    tw = d.textlength(txt, font=fonts["mono_s"])
    d.text(((W - tw) / 2, by + bh + 12), txt, font=fonts["mono_s"], fill=(*ORANGE, a),
           stroke_width=3, stroke_fill=(0, 0, 0, a))
    return img


def render_timer_hud(scenes: list[dict], starts: list[float], total: float, t0: float, out: Path, tmp: Path,
                     energy_label: str = "HIROSHIMA") -> None:
    fonts = {
        "big": ImageFont.truetype(BLACK, 112),
        "mid": ImageFont.truetype(BLACK, 56),
        "mono_s": ImageFont.truetype(MONO, 36),
    }
    energy_max = max((sc["hud"]["energy"][1] for sc in scenes if sc.get("hud")), default=1)
    frames_dir = tmp / "timer_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for f in frames_dir.glob("*.png"):
        f.unlink()
    blank = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for fi in range(int(total * FPS)):
        t = fi / FPS
        i = max(k for k in range(len(scenes)) if starts[k] <= t + 1e-9)
        hud = scenes[i].get("hud")
        if t < t0 or not hud:
            blank.save(frames_dir / f"{fi:05d}.png")
            continue
        end = starts[i + 1] if i + 1 < len(scenes) else total
        f = (t - starts[i]) / max(1e-6, end - starts[i])
        timer = _lerp(*hud["timer"], f)
        energy = _lerp(*hud["energy"], f) if hud["energy"][0] > 0 else hud["energy"][1] * f ** 2
        draw_frame(t, timer, energy, energy_max, t0, fonts, energy_label).save(frames_dir / f"{fi:05d}.png")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS), "-i", str(frames_dir / "%05d.png"),
                    "-c:v", "qtrle", "-pix_fmt", "argb", str(out)], check=True)
