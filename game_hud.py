"""Oyun arayuzu tarzi HUD katmani: segmentli kalkan bari, ikonlu stat satirlari, kayan derinlik cetveli,
kritik hasar uyarisi + kirmizi vinyet. Kare kare PIL ile cizilir, alfa kanalli video olarak disa verilir."""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
FPS = 15
MONO = "C:/Windows/Fonts/consolab.ttf"
BLACK = "assets/fonts/Montserrat-Black.ttf"

CYAN = (0, 225, 255)
PANEL = (4, 14, 30, 170)
PX, PY, PW, PH = 36, 300, 640, 400  # sol ust panel
RX, RY0, RY1 = 1000, 520, 1240  # sag derinlik cetveli


def _lerp(a: float, b: float, f: float) -> float:
    if a > 0 and b > 0 and max(a, b) / min(a, b) > 20:
        return a * (b / a) ** f
    return a + (b - a) * f


def _level_color(p: float) -> tuple[int, int, int]:
    if p >= 60:
        return (40, 255, 120)
    if p >= 30:
        return (255, 200, 0)
    return (255, 40, 40)


def _cut_panel(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, c: int, fill, outline) -> None:
    pts = [(x + c, y), (x + w, y), (x + w, y + h - c), (x + w - c, y + h), (x, y + h), (x, y + c)]
    d.polygon(pts, fill=fill)
    d.line(pts + [pts[0]], fill=outline, width=3)


def _icon(d: ImageDraw.ImageDraw, kind: str, x: int, y: int, col) -> None:
    if kind == "depth":  # asagi ok
        d.polygon([(x, y + 6), (x + 28, y + 6), (x + 14, y + 30)], fill=col)
        d.rectangle((x + 10, y - 6, x + 18, y + 8), fill=col)
    elif kind == "temp":  # termometre
        d.rounded_rectangle((x + 9, y - 6, x + 19, y + 20), 5, outline=col, width=3)
        d.ellipse((x + 4, y + 16, x + 24, y + 34), fill=col)
    else:  # basinc gostergesi
        d.arc((x, y - 2, x + 30, y + 28), 180, 360, fill=col, width=4)
        d.line((x + 15, y + 13, x + 26, y + 2), fill=col, width=4)
        d.ellipse((x + 11, y + 9, x + 19, y + 17), fill=col)


def _norm(v: float, lo: float, hi: float) -> float:
    """lo..hi araligini log olcekte 0-1'e esler (negatif degerler icin kaydirilir)."""
    v2, hi2 = max(v, lo) - lo + 1, hi - lo + 1
    return max(0.0, min(1.0, math.log(v2) / math.log(hi2)))


def _fmt(v: float, unit: str) -> str:
    if unit == "°C":
        return f"{round(v):+,} °C"
    if unit == "x":
        return f"×{v:,.1f}" if v < 10 else f"×{round(v):,}"
    if abs(v) < 10:
        return f"{v:.1f} {unit}"
    return f"{round(v):,} {unit}"


# satir: (anahtar, etiket, birim, ikon, bar_alt, bar_ust)
DEFAULT_ROWS = [("depth", "DEPTH", "km", "depth", 1, 20000),
                ("temp", "TEMP", "°C", "temp", -150, 10000),
                ("pressure", "PRESSURE", "atm", "pres", 0.1, 2_000_000)]


def draw_frame(t: float, vals: dict, rows: list[tuple], t_start: float, fonts: dict) -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    integ = vals["integrity"]
    crit = integ < 30
    # kritik: kenarlarda nabiz gibi atan kirmizi vinyet
    if crit:
        pulse = 0.5 + 0.5 * math.sin(t * 2 * math.pi * 1.6)
        vig = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        vd = ImageDraw.Draw(vig)
        a = int(60 + 90 * pulse)
        for k in range(10):
            vd.rectangle((k * 14, k * 14, W - k * 14, H - k * 14), outline=(255, 0, 0, max(0, a - k * 9)), width=16)
        img = Image.alpha_composite(img, vig.filter(ImageFilter.GaussianBlur(18)))

    # acilis: panel soldan kayarak girer
    slide = min(1.0, max(0.0, (t - t_start) / 0.45))
    ox = int(-(PW + 60) * (1 - slide) ** 2)
    d = ImageDraw.Draw(img)
    col = _level_color(integ)
    edge = (255, 60, 60, 230) if crit and int(t * 4) % 2 == 0 else (*CYAN, 220)
    _cut_panel(d, PX + ox, PY, PW, PH, 26, PANEL, edge)

    # kalkan bari
    d.text((PX + ox + 26, PY + 18), "SUIT INTEGRITY", font=fonts["mono_s"], fill=(*CYAN, 255))
    segs, sw, sh, gap = 20, 19, 40, 4
    filled = math.ceil(integ / 5 - 1e-6)
    bx, by = PX + ox + 26, PY + 58
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for k in range(segs):
        x0 = bx + k * (sw + gap)
        box = (x0, by, x0 + sw, by + sh)
        if k < filled:
            d.rectangle(box, fill=(*col, 255))
            gd.rectangle(box, fill=(*col, 160))
        else:
            d.rectangle(box, outline=(*CYAN, 90), width=2)
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(8)))
    d = ImageDraw.Draw(img)
    d.text((bx + segs * (sw + gap) + 14, by - 6), f"{round(integ)}%", font=fonts["black"], fill=(*col, 255))

    # stat satirlari (videoya gore ozellestirilebilir)
    for r, (key, label, unit, kind, lo, hi) in enumerate(rows):
        if r == 0 and vals.get("label"):
            label = vals["label"]
        v = vals[key]
        value, fill = _fmt(v, unit), _norm(v, lo, hi)
        y = PY + 128 + r * 88
        c = (255, 80, 80) if crit else CYAN
        _icon(d, kind, PX + ox + 26, y + 4, (*c, 255))
        d.text((PX + ox + 72, y), label, font=fonts["mono_s"], fill=(*c, 255))
        tw = d.textlength(value, font=fonts["mono"])
        d.text((PX + ox + PW - 30 - tw, y - 6), value, font=fonts["mono"], fill=(255, 255, 255, 255))
        bar_y = y + 44
        d.rectangle((PX + ox + 72, bar_y, PX + ox + PW - 30, bar_y + 8), fill=(255, 255, 255, 40))
        bw = int((PW - 102) * fill)
        if bw > 0:
            bar_col = (255, int(200 * (1 - fill)), 40) if kind == "temp" else c
            d.rectangle((PX + ox + 72, bar_y, PX + ox + 72 + bw, bar_y + 8), fill=(*bar_col, 255))

    # sag kenar: kayan cetvel (ilk satirin degeri)
    depth = vals[rows[0][0]]
    scroll = math.log10(max(depth, 1)) * 400
    d.line((RX, RY0, RX, RY1), fill=(*CYAN, 160), width=3)
    step = 40
    first = -((scroll % step))
    y = RY0 + first
    k = int(scroll // step)
    while y < RY1:
        if y >= RY0:
            long = (k % 5 == 0)
            d.line((RX - (34 if long else 18), y, RX, y), fill=(*CYAN, 200 if long else 120), width=3)
        y += step
        k += 1
    mid = (RY0 + RY1) // 2
    d.polygon([(RX - 44, mid), (RX - 64, mid - 14), (RX - 64, mid + 14)], fill=(*col, 255))
    label = _fmt(depth, rows[0][2])
    lw = d.textlength(label, font=fonts["mono_s"])
    d.text((RX - 72 - lw, mid - 18), label, font=fonts["mono_s"], fill=(255, 255, 255, 255),
           stroke_width=3, stroke_fill=(0, 0, 0, 255))

    # kritik hasar uyarisi
    if crit and int(t * 3) % 2 == 0:
        msg = "CRITICAL DAMAGE"
        bw_ = 620
        x0, y0 = (W - bw_) // 2, 760
        _cut_panel(d, x0, y0, bw_, 92, 20, (120, 0, 0, 190), (255, 60, 60, 255))
        mw = d.textlength(msg, font=fonts["black_s"])
        d.text(((W - mw) // 2, y0 + 16), msg, font=fonts["black_s"], fill=(255, 255, 255, 255))
    return img


def render_game_hud(scenes: list[dict], starts: list[float], total: float, t0: float, out: Path, tmp: Path,
                    rows_spec: list[tuple] | None = None) -> None:
    fonts = {
        "mono": ImageFont.truetype(MONO, 46),
        "mono_s": ImageFont.truetype(MONO, 32),
        "black": ImageFont.truetype(BLACK, 54),
        "black_s": ImageFont.truetype(BLACK, 54),
    }
    frames_dir = tmp / "hud_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for f in frames_dir.glob("*.png"):
        f.unlink()
    n = int(total * FPS)
    blank = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for fi in range(n):
        t = fi / FPS
        i = max(k for k in range(len(scenes)) if starts[k] <= t + 1e-9)
        hud = scenes[i].get("hud")
        if t < t0 or not hud:
            blank.save(frames_dir / f"{fi:05d}.png")
            continue
        end = starts[i + 1] if i + 1 < len(scenes) else total
        f = (t - starts[i]) / max(1e-6, end - starts[i])
        rows = rows_spec or DEFAULT_ROWS
        vals = {r[0]: _lerp(*hud[r[0]], f) for r in rows}
        vals["integrity"] = max(0.0, _lerp(*hud["integrity"], f))
        vals["label"] = hud.get("label")
        draw_frame(t, vals, rows, t0, fonts).save(frames_dir / f"{fi:05d}.png")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS), "-i", str(frames_dir / "%05d.png"),
                    "-c:v", "qtrle", "-pix_fmt", "argb", str(out)], check=True)
