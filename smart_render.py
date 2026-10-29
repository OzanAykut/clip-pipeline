"""Kisi sayisina gore bolunmus layout + dinamik altyazi + kart manset + flash-forward (cold open).

Klip tanimi:
    {
      "name": "airplane",
      "headline": "FAT SUIT VS *HANGING OFF A PLANE*",   # *...* vurgu rengi
      "teaser": [2821.0, 2826.0],                        # opsiyonel: en carpici an basa
      "segments": [[2793.4, 2828.5]],                    # asil akis (sirali)
      "speakers": [[2796.8, 2801.4, "center"], ...],     # opsiyonel: genis cekimde kim konusuyor
      "broll": [{"at": 2812.5, "query": "vintage airplane", "mode": "full", "dur": 1.8}],
    }
Opsiyonel: "music": Path (platformun kendi kutuphanesinden), "music_volume": 0.35,
"split_people": False (cok kisili cekimleri bolme), "noface": "center" (yuzsuz cekimde tam ekran).
B-roll modlari: full = tam ekran kesit, pip = kosede kucuk kart. Altyazi her zaman ustte kalir.
Teaser varsa: teaser -> geri sarma gecisi -> asil akis.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from broll import fetch_broll, prepare_full, prepare_pip
from smart_layout import LayoutSeg, analyze_range, describe, plan_layout
from utils import console, ffmpeg_path_escape

W, H, FPS = 1080, 1920, 30
FONT_DIR = Path("assets") / "fonts"
FONT_BLACK = FONT_DIR / "Montserrat-Black.ttf"
CAPTION_FONT_NAME = "Montserrat Thin"  # fontsource dosyasindaki aile adi boyle; kalinligi Bold bayragi secer
LETTERBOX_BLUR = 25
REWIND_SECONDS = 1.0
MUSIC_VOLUME = 0.35  # konusmanin altinda; sidechain ile konusma aninda ayrica kisilir
MUSIC_FADE_OUT = 1.5


def _run(cmd: list[str], what: str) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg {what} basarisiz\n{r.stderr[-2500:]}")


# ---------------- Layout parcasi render ----------------


def _panel(label_in: str, rect: tuple, pw: int, ph: int, label_out: str) -> str:
    x, y, w, h = rect
    return f"[{label_in}]crop={w}:{h}:{x}:{y},scale={pw}:{ph}:flags=lanczos,setsar=1[{label_out}]"


def _segment_filter(seg: LayoutSeg) -> str:
    if seg.kind == "fill":
        return _panel("0:v", seg.rects[0], W, H, "v")
    if seg.kind == "split":
        return (
            "[0:v]split=2[a][b];"
            + _panel("a", seg.rects[0], W, H // 2, "p0") + ";"
            + _panel("b", seg.rects[1], W, H // 2, "p1") + ";"
            "[p0][p1]vstack=2[v]"
        )
    if seg.kind == "three":
        return (
            "[0:v]split=3[a][b][c];"
            + _panel("a", seg.rects[0], W, H // 2, "p0") + ";"
            + _panel("b", seg.rects[1], W // 2, H // 2, "p1") + ";"
            + _panel("c", seg.rects[2], W // 2, H // 2, "p2") + ";"
            "[p1][p2]hstack=2[bot];[p0][bot]vstack=2[v]"
        )
    # letterbox: tam kare + bulanik dolgu
    return (
        "[0:v]split=2[bg][fg];"
        f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma={LETTERBOX_BLUR}[bgb];"
        f"[fg]scale={W}:{H}:force_original_aspect_ratio=decrease[fgf];"
        "[bgb][fgf]overlay=(W-w)/2:(H-h)/2,setsar=1[v]"
    )


def render_range(source: Path, start: float, end: float, words: list[dict], out_path: Path,
                 tmp: Path, speakers: list | None = None, split_people: bool = True,
                 noface: str = "letterbox") -> list[tuple[float, float, str]]:
    """[start,end] araligini layout planina gore 1080x1920/30fps video+ses olarak render eder.
    Donen: parca-relative (t0, t1, kind) layout zaman cizelgesi (altyazi konumu icin)."""
    tmp.mkdir(parents=True, exist_ok=True)
    words_rel = [{**w, "start": w["start"] - start, "end": w["end"] - start}
                 for w in words if w["end"] > start and w["start"] < end]
    shots, src = analyze_range(source, start, end)
    hints = [(a - start, b - start, pos) for a, b, pos in (speakers or []) if b > start and a < end]
    plan = plan_layout(shots, src, words_rel, hints, split_people, noface)
    console.print(f"  plan: {describe(plan)}")

    total = round((end - start) * FPS)
    frame_edges = [round(s.t0 * FPS) for s in plan] + [total]
    frame_edges[0] = 0
    parts = []
    timeline = []
    for i, seg in enumerate(plan):
        n0, n1 = frame_edges[i], frame_edges[i + 1]
        if n1 <= n0:
            continue
        part = tmp / f"{out_path.stem}_p{i:02d}.mp4"
        _run([
            "ffmpeg", "-y", "-ss", f"{start + n0 / FPS:.4f}", "-i", str(source),
            "-filter_complex", _segment_filter(seg) + f";[v]fps={FPS}[vo]", "-map", "[vo]",
            "-frames:v", str(n1 - n0), "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p",
            str(part),
        ], f"layout parca {i}")
        parts.append(part)
        timeline.append((n0 / FPS, n1 / FPS, seg.kind))

    list_file = tmp / f"{out_path.stem}_list.txt"
    list_file.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts), encoding="utf-8")
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-ss", f"{start:.4f}", "-t", f"{total / FPS:.4f}", "-i", str(source),
        "-map", "0:v", "-map", "1:a", "-c:v", "copy",
        # parca kenarlarinda 15-20 ms yumusatma: jump cut birlesimlerinde "tik" olmasin
        "-af", f"aresample=48000,afade=t=in:d=0.015,afade=t=out:st={max(0.0, total / FPS - 0.02):.3f}:d=0.02",
        "-ac", "2", "-c:a", "aac", "-b:a", "192k", "-shortest",
        str(out_path),
    ], "layout birlestirme")
    for p in parts:
        p.unlink(missing_ok=True)
    list_file.unlink(missing_ok=True)
    return timeline


# ---------------- Flash-forward gecisi ----------------


def make_rewind(teaser_path: Path, out_path: Path) -> None:
    """Teaser'i hizla geri sardirir: ters oynatma + desature + grain + renk kaymasi, sesi de ters/hizli."""
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(teaser_path)],
        capture_output=True, text=True).stdout.strip())
    speed = max(1.0, dur / REWIND_SECONDS)
    # atempo tek seferde en fazla 2x; zincirle
    tempos, s = [], speed
    while s > 2.0:
        tempos.append("atempo=2.0")
        s /= 2.0
    tempos.append(f"atempo={s:.4f}")
    _run([
        "ffmpeg", "-y", "-i", str(teaser_path),
        "-filter_complex",
        f"[0:v]reverse,setpts=PTS/{speed:.4f},fps={FPS},eq=saturation=0.25:contrast=1.15,"
        f"rgbashift=rh=-12:bh=12,noise=alls=30:allf=t,"
        f"drawbox=y=ih*0.62:w=iw:h=6:color=white@0.35:t=fill[v];"
        f"[0:a]areverse,{','.join(tempos)},volume=0.45[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        str(out_path),
    ], "rewind")


# ---------------- Dinamik altyazi (ASS) ----------------

CAPTION_ASS_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{CAPTION_FONT_NAME},92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,1,0,1,7,5,5,90,90,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

ACTIVE_COLORS = ["&H3CFF3C&", "&H00E5FF&"]  # yesil, sari (BGR) - gruplar arasinda donusumlu
MAX_GROUP_WORDS = 3
MAX_GROUP_CHARS = 16
GROUP_PAUSE = 0.35


def _ts(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _clean(word: str) -> str:
    return word.replace("{", "").replace("}", "").replace("\\", "").strip().upper()


def _group_words(words: list[dict]) -> list[list[dict]]:
    groups: list[list[dict]] = []
    for w in words:
        text = _clean(w["word"])
        if not text:
            continue
        w = {**w, "word": text}
        g = groups[-1] if groups else None
        if (g is None or len(g) >= MAX_GROUP_WORDS
                or len(" ".join(x["word"] for x in g) + " " + text) > MAX_GROUP_CHARS
                or w["start"] - g[-1]["end"] > GROUP_PAUSE
                or g[-1]["word"][-1:] in ".?!,"):
            groups.append([w])
        else:
            g.append(w)
    return groups


def _caption_y(t: float, layout: list[tuple[float, float, str]]) -> int:
    kind = next((k for a, b, k in layout if a <= t < b), "fill")
    return H // 2 if kind in ("split", "three") else int(H * 0.70)


def write_captions(words: list[dict], layout: list[tuple[float, float, str]], out_path: Path) -> None:
    """words: cikti zaman cizelgesinde. Grup ekrana 'pop' ile girer, konusulan kelime renkli ve buyuk."""
    lines = [CAPTION_ASS_HEADER]
    for gi, g in enumerate(_group_words(words)):
        color = ACTIVE_COLORS[gi % len(ACTIVE_COLORS)]
        g_end = max(g[-1]["end"], g[0]["start"] + 0.25)
        y = _caption_y(g[0]["start"], layout)
        for wi, w in enumerate(g):
            a = w["start"] if wi else g[0]["start"]
            b = g[wi + 1]["start"] if wi + 1 < len(g) else g_end
            if b <= a:
                continue
            parts = []
            for xj, x in enumerate(g):
                if xj == wi:
                    parts.append(r"{\c" + color + r"\fscx112\fscy112}" + x["word"] + r"{\c&HFFFFFF&\fscx100\fscy100}")
                else:
                    parts.append(x["word"])
            pop = r"{\fscx70\fscy70\t(0,90,\fscx108\fscy108)\t(90,160,\fscx100\fscy100)}" if wi == 0 else ""
            lines.append(f"Dialogue: 0,{_ts(a)},{_ts(b)},Cap,,0,0,0,,{{\\an5\\pos({W // 2},{y})}}{pop}{' '.join(parts)}")
    out_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------- Manset karti (PIL) ----------------

ACCENT = (229, 57, 53)


def make_headline_card(headline: str, out_path: Path) -> tuple[int, int]:
    """Beyaz yuvarlatilmis kart + golge, siyah Montserrat Black. *kelime* vurgu renginde."""
    font = ImageFont.truetype(str(FONT_BLACK), 62)
    max_w = 860
    tokens = []  # (kelime, vurgu mu)
    accent = False
    for raw in headline.split():
        starts, ends = raw.startswith("*"), raw.endswith("*")
        if starts:
            accent = True
        tokens.append((raw.strip("*"), accent))
        if ends:
            accent = False

    lines: list[list[tuple[str, bool]]] = [[]]
    space = font.getlength(" ")
    for tok in tokens:
        test = lines[-1] + [tok]
        width = sum(font.getlength(t) for t, _ in test) + space * (len(test) - 1)
        if lines[-1] and width > max_w:
            lines.append([tok])
        else:
            lines[-1] = test

    asc, desc = font.getmetrics()
    line_h = asc + desc + 6
    text_w = max(sum(font.getlength(t) for t, _ in ln) + space * (len(ln) - 1) for ln in lines)
    pad_x, pad_y, shadow = 44, 30, 18
    card_w, card_h = int(text_w + pad_x * 2), int(line_h * len(lines) + pad_y * 2)
    img = Image.new("RGBA", (card_w + shadow * 2, card_h + shadow * 2), (0, 0, 0, 0))

    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((shadow, shadow + 8, shadow + card_w, shadow + card_h + 8), 30, fill=(0, 0, 0, 150))
    img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(12)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((shadow, shadow, shadow + card_w, shadow + card_h), 30, fill=(255, 255, 255, 255))

    y = shadow + pad_y
    for ln in lines:
        lw = sum(font.getlength(t) for t, _ in ln) + space * (len(ln) - 1)
        x = shadow + (card_w - lw) / 2
        for t, acc in ln:
            d.text((x, y), t, font=font, fill=ACCENT if acc else (15, 15, 15))
            x += font.getlength(t) + space
        y += line_h
    img.save(out_path)
    return img.size


# ---------------- Ana akis ----------------


def render_smart_clip(source: Path, words: list[dict], clip: dict[str, Any], out_path: Path, tmp: Path,
                      headline_seconds: float = 3.0) -> None:
    tmp.mkdir(parents=True, exist_ok=True)
    name = clip["name"]
    pieces: list[Path] = []
    layout: list[tuple[float, float, str]] = []
    out_words: list[dict] = []
    offset = 0.0

    ranges = []
    range_map: list[tuple[str, float, float, float]] = []  # (rol, kaynak_bas, kaynak_son, cikti_offset)
    if clip.get("teaser"):
        ranges.append(("teaser", *clip["teaser"]))
    segments = clip["segments"]
    if clip.get("tighten"):
        # jump cut: konusmadaki uzun boslugu kes (6-25 sn arasi yavas erime dersi, 2026-10-07)
        # kesim noktalari ses enerjisindeki sessizliklere oturur (whisper zamanlari ±100 ms kayik, kopuk duyuluyordu)
        if clip.get("tighten_mode", "audio") == "audio":
            from audio_cuts import smart_tighten
            segments = smart_tighten(source, segments, float(clip.get("max_gap", 0.35)), words=words)
        else:
            segments = tighten_segments(segments, words, float(clip.get("max_gap", 0.35)))
        console.print(f"  tighten: {len(clip['segments'])} parca -> {len(segments)} parca, "
                      f"{sum(e - s for s, e in clip['segments']):.1f}s -> {sum(e - s for s, e in segments):.1f}s")
    ranges += [("main", s, e) for s, e in segments]

    for idx, (role, s, e) in enumerate(ranges):
        console.print(f"  [{role}] {s:.1f}-{e:.1f}")
        part = tmp / f"{name}_r{idx}.mp4"
        tl = render_range(source, s, e, words, part, tmp, clip.get("speakers"),
                          clip.get("split_people", True), clip.get("noface", "letterbox"))
        dur = round((e - s) * FPS) / FPS
        pieces.append(part)
        range_map.append((role, s, e, offset))
        layout += [(offset + a, offset + b, k) for a, b, k in tl]
        out_words += [{"word": w["word"], "start": max(0.0, w["start"] - s) + offset,
                       "end": min(e - s, w["end"] - s) + offset}
                      # kesim sinirina birkac ms tasan kelime (sesi duyulmayan "When") altyaziya girmesin
                      for w in words if min(e, w["end"]) - max(s, w["start"]) >= min(0.12, 0.5 * (w["end"] - w["start"]))]
        offset += dur
        # geri sarma efekti varsayilan KAPALI: Affleck klibinde izleyicinin ~%40'i tam bu gecisde kaydirdi (2026-10-07)
        if role == "teaser" and clip.get("rewind", False):
            rw = tmp / f"{name}_rewind.mp4"
            make_rewind(part, rw)
            pieces.append(rw)
            layout.append((offset, offset + REWIND_SECONDS, "rewind"))
            offset += REWIND_SECONDS

    joined = tmp / f"{name}_joined.mp4"
    if len(pieces) == 1:
        pieces[0].replace(joined)
    else:
        inputs = []
        for p in pieces:
            inputs += ["-i", str(p)]
        streams = "".join(f"[{i}:v][{i}:a]" for i in range(len(pieces)))
        _run(["ffmpeg", "-y", *inputs, "-filter_complex", f"{streams}concat=n={len(pieces)}:v=1:a=1[v][a]",
              "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
              "-c:a", "aac", "-b:a", "192k", str(joined)], "parca birlestirme")

    # konusma sesini yayin seviyesine getir (-16 LUFS): kisik kaynaklarda (Kaepernick ~-44 dB) muzik konusmayi bastiriyordu
    normed = tmp / f"{name}_joined_n.mp4"
    _run(["ffmpeg", "-y", "-i", str(joined), "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
          "-ar", "48000", "-c:a", "aac", "-b:a", "192k", str(normed)], "konusma normalizasyonu")
    normed.replace(joined)

    ass = tmp / f"{name}.ass"
    write_captions(out_words, layout, ass)
    # manset stili: "top" (ustte kart), "question" (ilk saniyeler karartilmis kare + ortada soru karti), "none"
    loop = bool(clip.get("loop"))
    style = clip.get("headline_style", "top") if clip.get("headline") else "none"
    if loop and style == "top":
        style = "static"  # loop'ta kart her basta kayarak girerse dikis belli olur: baştan sona sabit dursun
    card = tmp / f"{name}_card.png"
    cw, ch = make_headline_card(clip.get("headline") or " ", card)
    cx = (W - cw) // 2
    hs = offset if style == "static" else (headline_seconds if style != "none" else 0.05)

    broll_inputs, broll_chain = _prepare_brolls(clip.get("broll", []), range_map, layout, hs, tmp, name)
    # zoom vuruslari: [(cikti_sn, sure)] araliginda kadraj %14 yakinlasir (altyazidan once, yazilar sabit kalir).
    # "punch_src" kaynak saniyesiyle verilir (jump cut sonrasi kaymaz)
    punch = list(clip.get("punch", []))
    for t, d in clip.get("punch_src", []):
        ot = _source_to_output(t, range_map)
        if ot is not None:
            punch.append((ot, d))
    hook_zoom = bool(clip.get("hook_zoom")) and not loop  # loop'ta ilk kare zoom'lu olursa dikis belli olur
    if punch or hook_zoom:
        z = "1"
        if punch:
            cond = "+".join(f"between(it\\,{a:.2f}\\,{a + d:.2f})" for a, d in punch)
            z = f"if({cond}\\,1.14\\,1)"
        if hook_zoom:  # gorsel hook: ilk 0.5 sn yakindan normale acilan hizli zoom
            z = f"if(lt(it\\,0.5)\\,1.28-0.28*it/0.5\\,{z})"
        broll_chain += (f"[bv]zoompan=z='{z}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                        f":s={W}x{H}:fps={FPS}[bz];")
        base = "bz"
    else:
        base = "bv"
    fc = broll_chain + f"[{base}]subtitles='{ffmpeg_path_escape(ass)}':fontsdir='{ffmpeg_path_escape(FONT_DIR)}'[s];"
    if style == "none":
        fc += "[s]null[v]"
    elif style == "question":
        fc += (
            f"[s]drawbox=x=0:y=0:w=iw:h=ih:color=black@0.6:t=fill:enable='lt(t,{hs:.2f})'[sd];"
            f"[1:v]format=rgba,scale=iw*1.25:-1,fade=t=in:st=0:d=0.15:alpha=1,"
            f"fade=t=out:st={hs - 0.2:.2f}:d=0.2:alpha=1[c];"
            f"[sd][c]overlay=x=(W-w)/2:y='(H-h)/2-60*max(0\\,1-t/0.25)':enable='lt(t,{hs:.2f})'[v]"
        )
    elif style == "static":
        fc += f"[1:v]format=rgba[c];[s][c]overlay=x={cx}:y=70[v]"
    else:
        fc += (
            f"[1:v]format=rgba,fade=t=in:st=0:d=0.2:alpha=1,fade=t=out:st={hs - 0.25:.2f}:d=0.25:alpha=1[c];"
            f"[s][c]overlay=x={cx}:y='70+40*max(0\\,1-t/0.22)':enable='lt(t,{hs:.2f})'[v]"
        )
    music_inputs: list[str] = []
    audio_map, audio_codec = ["-map", "0:a"], ["-c:a", "copy"]
    sfx = list(clip.get("sfx", []))  # [(cikti_sn, tur)] ; "sfx_src" kaynak saniyesiyle
    for t, kind in clip.get("sfx_src", []):
        ot = _source_to_output(t, range_map)
        if ot is not None:
            sfx.append((ot, kind))
    if loop and clip.get("music"):
        # kesintisiz dongu: muzik videonun tamaminda calar; son 0.6 sn'de baslangic noktasinin hemen oncesine
        # capraz gecer, boylece video basa dondugunde muzik de kaldigi yerden devam eder
        bed = tmp / f"{name}_loopbed.wav"
        _loop_music_bed(Path(clip["music"]), float(clip.get("music_start", 6.0)), offset, bed)
        idx = 2 + len(broll_inputs) // 2
        music_inputs = ["-i", str(bed)]
        vol = clip.get("music_volume", MUSIC_VOLUME)
        fc += (
            f";[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,volume={vol}[m];"
            "[0:a]asplit=2[speech][sc];"
            "[m][sc]sidechaincompress=threshold=0.03:ratio=3:attack=20:release=400[md];"
            "[speech][md]amix=inputs=2:duration=first:normalize=0[aout]"
        )
        audio_map, audio_codec = ["-map", "[aout]"], ["-c:a", "aac", "-b:a", "192k"]
    elif clip.get("music"):
        # muzik hikaye basladiginda (teaser + geri sarmadan sonra) girer, konusmada kisilir, sonda soner
        start = next((off for role, _, _, off in range_map if role == "main"), 0.0)
        length = offset - start
        idx = 2 + len(broll_inputs) // 2
        music_inputs = ["-i", str(clip["music"])]
        vol = clip.get("music_volume", MUSIC_VOLUME)
        fc += (
            f";[{idx}:a]atrim=0:{length:.3f},aresample=48000,aformat=channel_layouts=stereo,volume={vol},"
            f"afade=t=in:d=0.6,afade=t=out:st={max(0.0, length - MUSIC_FADE_OUT):.3f}:d={MUSIC_FADE_OUT},"
            f"adelay={round(start * 1000)}:all=1[m];"
            "[0:a]asplit=2[speech][sc];"
            "[m][sc]sidechaincompress=threshold=0.03:ratio=3:attack=20:release=400[md];"
            "[speech][md]amix=inputs=2:duration=first:normalize=0[aout]"
        )
        audio_map, audio_codec = ["-map", "[aout]"], ["-c:a", "aac", "-b:a", "192k"]
    sfx_inputs: list[str] = []
    if sfx:
        # isitsel hook'lar: sentetik whoosh / hit / pop, muzigin ustune (kisilmadan) eklenir
        first = 2 + len(broll_inputs) // 2 + len(music_inputs) // 2
        src_audio = "[aout]" if audio_map == ["-map", "[aout]"] else "[0:a]"
        if src_audio == "[aout]":
            fc = fc.replace("normalize=0[aout]", "normalize=0[apre]")
            src_audio = "[apre]"
        labels = []
        for k, (t, kind) in enumerate(sfx):
            sfx_inputs += ["-i", str(make_sfx(kind))]
            fc += f";[{first + k}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={round(t * 1000)}:all=1[x{k}]"
            labels.append(f"[x{k}]")
        fc += f";{src_audio}{''.join(labels)}amix=inputs={1 + len(labels)}:duration=first:normalize=0[aout]"
        audio_map, audio_codec = ["-map", "[aout]"], ["-c:a", "aac", "-b:a", "192k"]
    _run([
        "ffmpeg", "-y", "-i", str(joined), "-loop", "1", "-t", f"{hs:.2f}", "-i", str(card), *broll_inputs,
        *music_inputs, *sfx_inputs,
        "-filter_complex", fc, "-map", "[v]", *audio_map,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        *audio_codec, "-movflags", "+faststart", str(out_path),
    ], "altyazi + manset + broll + muzik")
    for p in pieces + [joined]:
        p.unlink(missing_ok=True)


SFX_DIR = Path("assets/sfx")
_SFX_RECIPES = {
    # sentetik, telifsiz: ffmpeg lavfi ile uretilir
    "whoosh": "anoisesrc=d=0.45:c=pink:a=0.6,highpass=f=300,lowpass=f=4000,"
              "afade=t=in:d=0.3:curve=exp,afade=t=out:st=0.3:d=0.15",
    "hit": "sine=f=55:d=0.35,volume=2.2,afade=t=out:st=0.05:d=0.3:curve=exp",
    "pop": "sine=f=900:d=0.08,afade=t=out:st=0.01:d=0.07",
    "riser": "anoisesrc=d=1.2:c=white:a=0.35,highpass=f=800,afade=t=in:d=1.15:curve=exp,afade=t=out:st=1.15:d=0.05",
}


def make_sfx(kind: str) -> Path:
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    out = SFX_DIR / f"{kind}.wav"
    if not out.exists():
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i", _SFX_RECIPES[kind], "-ar", "48000", "-ac", "2", str(out)],
             f"sfx {kind}")
    return out


def _loop_music_bed(music: Path, start: float, length: float, out: Path, xf: float = 0.6) -> None:
    """Uzunlugu `length` olan muzik yatagi: M(start..start+length); son xf saniyede M(start-xf..start)'a capraz
    gecer. Video basa sardiginda muzik M(start)'tan devam ettigi icin dongu dikisi duyulmaz."""
    import numpy as np
    sr = 48000
    a0 = max(0.0, start - xf)
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a0:.3f}", "-i", str(music), "-t", f"{length + xf + 0.1:.3f}",
                        "-f", "s16le", "-ac", "2", "-ar", str(sr), "-"], capture_output=True)
    pcm = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32).reshape(-1, 2)
    pre = int(round((start - a0) * sr))          # M(start) ornegi
    n, x = int(round(length * sr)), int(round(xf * sr))
    body = pcm[pre:pre + n].copy()
    if len(body) < n:                            # parca kisa kaldiysa basa sarmali doldur
        body = np.concatenate([body, np.tile(body, (n // max(1, len(body)) + 1, 1))])[:n]
    if pre >= x:
        tail = pcm[pre - x:pre]                  # M(start-xf..start)
        ramp = np.linspace(0, 1, x, dtype=np.float32)[:, None]
        body[n - x:] = body[n - x:] * (1 - ramp) + tail * ramp
    import wave
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(np.clip(body, -32768, 32767).astype(np.int16).tobytes())


def tighten_segments(segments: list[tuple[float, float]], words: list[dict], max_gap: float = 0.35,
                     pad: float = 0.08, min_piece: float = 0.8) -> list[tuple[float, float]]:
    """Her segmenti, kelimeler arasi bosluk max_gap'i astigi yerlerden boler (bosluk atilir).
    Kelime basina/sonuna pad kadar pay birakir; min_piece'ten kisa parcalar oncekine eklenir."""
    out: list[tuple[float, float]] = []
    for s, e in segments:
        ws = [w for w in words if w["start"] >= s - 0.05 and w["end"] <= e + 0.05]
        if not ws:
            out.append((s, e))
            continue
        pieces: list[tuple[float, float]] = []  # yalniz bu segmentin parcalari (segmentler arasi birlesme olmasin)
        cur_start = s
        for a, b in zip(ws, ws[1:]):
            if b["start"] - a["end"] > max_gap:
                end = min(e, a["end"] + pad)
                if end - cur_start >= min_piece or not pieces:
                    pieces.append((cur_start, end))
                else:  # cok kisa: ayni segmentteki onceki parcaya kat
                    ps, _ = pieces.pop()
                    pieces.append((ps, end))
                cur_start = max(s, b["start"] - pad)
        pieces.append((cur_start, e))
        out += pieces
    return out


def _source_to_output(t: float, range_map: list[tuple[str, float, float, float]]) -> float | None:
    # ayni an hem teaser'da hem ana akista olabilir; ana akisi tercih et
    for role, s, e, off in sorted(range_map, key=lambda r: r[0] != "main"):
        if s <= t < e:
            return off + (t - s)
    return None


def _prepare_brolls(items: list[dict], range_map, layout, headline_seconds: float, tmp: Path, name: str
                    ) -> tuple[list[str], str]:
    """Donen: (ek ffmpeg girdileri, [0:v]'den [bv]'ye giden overlay zinciri). Girdiler 2'den baslar."""
    inputs: list[str] = []
    chain = "[0:v]null[b0];"
    last = "b0"
    for i, item in enumerate(items):
        at = _source_to_output(item["at"], range_map)
        src = fetch_broll(item["query"])
        if at is None or src is None:
            console.print(f"  broll atlandi: {item['query']}")
            continue
        dur = float(item.get("dur", 1.8))
        mode = item.get("mode", "full")
        clip_path = tmp / f"{name}_broll{i}.{'mov' if mode == 'pip' else 'mp4'}"
        if mode == "pip":
            prepare_pip(src, dur, clip_path, tmp)
            kind = next((k for a, b, k in layout if a <= at < b), "fill")
            x, y = 14, (40 if kind in ("split", "three") else 280)
            if at < headline_seconds:
                y = max(y, 330)
        else:
            prepare_full(src, dur, clip_path)
            x, y = 0, 0
        idx = 2 + len(inputs) // 2
        inputs += ["-i", str(clip_path)]
        nxt = f"b{i + 1}"
        chain += (
            f"[{idx}:v]setpts=PTS-STARTPTS+{at:.3f}/TB[r{i}];"
            f"[{last}][r{i}]overlay=x={x}:y={y}:eof_action=pass:enable='between(t,{at:.3f},{at + dur:.3f})'[{nxt}];"
        )
        last = nxt
        console.print(f"  broll {mode} @ {at:.1f}s: {item['query']} ({src.suffix})")
    chain += f"[{last}]null[bv];"
    return inputs, chain
