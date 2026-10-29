"""What-if kanali - Gizmo formati: karakter kendi sesiyle (Veo diyalogu) konusur, anlatici/TTS yok.

Spec:
  {"clips": [{"src": ..., "speech": True, "lead": 0.12, "tail": 0.35}         # konusmaya gore kirp
             {"src": ..., "start": 0.6, "end": 3.4}                           # aksiyon klibi, sabit aralik
             {"wrong": True, "dur": 1.0}],                                    # onceki karede donup WRONG! damgasi
   "music": Path, "music_volume": 0.12}
Sahneler arasi kayma/zoom gecisleri + whoosh (klipte "trans": "cut" ile sert kesme), 1080x1920, kelime kelime altyazi (smart_render), muzik konusmanin altinda kisilir, loudnorm -14.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import smart_render as sr
from utils import ffmpeg_path_escape

W, H, FPS = 1080, 1920, 30
SR = 48000
XFADE_DUR = 0.35
HARD_CUT = 0.04          # xfade 0 sureye izin vermiyor: ~1 karelik "sert" kesme
WHOOSH_VOL = 0.35
TRANSITIONS = ["slideleft", "slideup", "circleopen", "slideright", "slidedown"]


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-2000:])


def _dur(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(p)],
                         capture_output=True, text=True).stdout
    return float(json.loads(out)["format"]["duration"])


_whisper = None


def _words(src: Path, cache: Path) -> list[dict]:
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel("small", device="cpu", compute_type="int8")
    segs, _ = _whisper.transcribe(str(src), language="en", word_timestamps=True, vad_filter=False)
    words = [{"word": w.word.strip(), "start": w.start, "end": w.end} for s in segs for w in s.words if w.word.strip()]
    cache.write_text(json.dumps(words), encoding="utf-8")
    return words


def _wrong_png(path: Path) -> None:
    """Cizgi roman damgasi: kirmizi 'WRONG!' beyaz konturlu, egik, arkasinda patlama sekli."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = W // 2, int(H * 0.42)
    import math
    pts = []
    for k in range(24):
        r = 430 if k % 2 == 0 else 300
        a = math.pi * 2 * k / 24
        pts.append((cx + r * math.cos(a), cy + r * 0.8 * math.sin(a)))
    d.polygon(pts, fill=(255, 214, 0, 255), outline=(0, 0, 0, 255), width=12)
    font = ImageFont.truetype(str(sr.FONT_BLACK), 210)
    txt = "WRONG!"
    tw = d.textlength(txt, font=font)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((cx - tw / 2, cy - 130), txt, font=font, fill=(230, 30, 30, 255),
                               stroke_width=16, stroke_fill=(255, 255, 255, 255))
    layer = layer.rotate(8, center=(cx, cy), resample=Image.BICUBIC)
    Image.alpha_composite(img, layer).save(path)


def _segment(clip: dict, i: int, tmp: Path, prev: Path | None) -> tuple[Path, list[dict]]:
    out = tmp / f"seg_{i:02d}.mp4"
    vf = f"scale={W}:{H}:flags=lanczos,fps={FPS},setsar=1"
    if clip.get("wrong"):
        dur = clip.get("dur", 1.0)
        still = tmp / f"still_{i:02d}.png"
        _run(["ffmpeg", "-y", "-v", "error", "-sseof", "-0.1", "-i", str(prev), "-frames:v", "1", "-update", "1",
              str(still)])
        stamp = tmp / "wrong.png"
        _wrong_png(stamp)
        # kare gri + hafif titreme, damga 0.12 sn'de buyuyerek girer; ses: buzzer (kare dalga) + bas vurus
        fc = (f"[0:v]scale={W}:{H},format=yuv420p,hue=s=0.15,eq=brightness=-0.08,"
              f"crop=iw-24:ih-24:12+8*sin(t*60):12+8*cos(t*53),scale={W}:{H}[bg];"
              f"[1:v]format=rgba,scale=w='iw*min(1,0.6+t/0.12*0.4)':h=-1:eval=frame[st];"
              f"[bg][st]overlay=x=(W-w)/2:y=(H-h)/2:eval=frame,fps={FPS},setsar=1[v]")
        buzz = (f"aevalsrc=0.35*sgn(sin(2*PI*130*t))*lt(t\\,0.55)+0.6*sin(2*PI*55*t)*exp(-6*t)"
                f":s={SR}:d={dur}")
        _run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-t", str(dur), "-i", str(still),
              "-loop", "1", "-t", str(dur), "-i", str(stamp), "-f", "lavfi", "-i", buzz,
              "-filter_complex", fc, "-map", "[v]", "-map", "2:a", "-t", str(dur),
              "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
              "-c:a", "aac", "-ar", str(SR), "-ac", "2", str(out)])
        return out, []

    src = Path(clip["src"])
    words = []
    if clip.get("voice"):
        return _voiced_segment(clip, src, out, vf, tmp)
    if clip.get("speech"):
        words = _words(src, tmp / f"words_{src.stem}.json")
        a = max(0.0, words[0]["start"] - clip.get("lead", 0.12)) if words else 0.0
        b = min(_dur(src), words[-1]["end"] + clip.get("tail", 0.35)) if words else _dur(src)
        a = clip.get("start", a)
        b = clip.get("end", b)
    else:
        a, b = clip.get("start", 0.0), clip.get("end", _dur(src))
    words = [{**w, "start": w["start"] - a, "end": w["end"] - a} for w in words if w["start"] >= a - 0.05 and w["end"] <= b + 0.1]
    # whisper duzeltmeleri: ses efektlerini at ("drop"), yanlis duyulani duzelt ("fix", bos -> sil)
    drop = {x.lower() for x in clip.get("drop", [])}
    fix = clip.get("fix", {})
    words = [{**w, "word": fix.get(w["word"], w["word"])} for w in words
             if w["word"].lower().strip(".,!?") not in drop]
    words = [w for w in words if w["word"]]
    _run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(src),
          "-vf", vf, "-af", f"aresample={SR},volume={clip.get('volume', 1.0)}",
          "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-ar", str(SR), "-ac", "2", str(out)])
    return out, words


SFX = {
    # sentetik efektler (aevalsrc): bas "bum" + gurultu patlamasi
    "boom": "0.9*sin(2*PI*(55-25*t)*t)*exp(-2.5*t)+0.5*(random(0)*2-1)*exp(-6*t)",
}


def _voiced_segment(clip: dict, src: Path, out: Path, vf: str, tmp: Path) -> tuple[Path, list[dict]]:
    """Dublaj: Veo'nun kendi sesi (eski Gizmo sesi) kisilir, yerine bizim TTS replik konur.
    voice_at: replik segmentin kacinci saniyesinde baslar; orig_volume: Veo sesinin seviyesi (0 = sessiz);
    orig_after: bu saniyeden sonra Veo sesi tam seviyeye doner (or. patlama efekti); sfx: [(sn, tip)]."""
    voice = Path(clip["voice"])
    at = clip.get("voice_at", 0.1)
    vd = _dur(voice)
    a = clip.get("start", 0.0)
    b = clip.get("end", a + at + vd + clip.get("tail", 0.3))
    seg_d = b - a
    vol = clip.get("orig_volume", 0.0)
    after = clip.get("orig_after")
    until = clip.get("orig_until")  # bu saniyeye kadar Veo sesi tam (eski Gizmo konusmaya baslamadan once)
    gain = f"{vol}"
    if after is not None:
        gain = f"if(gte(t\\,{after})\\,1\\,{gain})"
    if until is not None:
        gain = f"if(lt(t\\,{until})\\,1\\,{gain})"
    inputs = ["-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(src), "-i", str(voice)]
    ms = int(at * 1000)
    fc = [f"[0:a]aresample={SR},volume='{gain}':eval=frame[o]",
          f"[1:a]aresample={SR},aformat=channel_layouts=stereo,volume={clip.get('voice_volume', 1.0)},"
          f"adelay={ms}|{ms}[vo]"]
    mix = ["[o]", "[vo]"]
    for k, (ts, kind) in enumerate(clip.get("sfx", [])):
        inputs += ["-f", "lavfi", "-i", f"aevalsrc={SFX[kind]}:s={SR}:d=2.0"]
        d_ms = int(ts * 1000)
        fc.append(f"[{2 + k}:a]aformat=channel_layouts=stereo,volume=0.8,adelay={d_ms}|{d_ms}[s{k}]")
        mix.append(f"[s{k}]")
    fc.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0,atrim=0:{seg_d:.3f}[a]")
    _run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(fc),
          "-map", "0:v", "-map", "[a]", "-vf", vf,
          "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-ar", str(SR), "-ac", "2", "-t", f"{seg_d:.3f}", str(out)])
    words = _words(voice, tmp / f"words_{voice.parent.name}_{voice.stem}.json")
    fix = clip.get("fix", {})
    # fix: {"kelime": "yeni"} ya da {sira_no: "yeni"} (ayni kelime birden cok geciyorsa)
    words = [{**w, "word": fix.get(k, fix.get(w["word"], w["word"])), "start": w["start"] + at, "end": w["end"] + at}
             for k, w in enumerate(words)]
    return out, [w for w in words if w["word"]]


def render_gizmo(spec: dict, out_path: Path, tmp: Path) -> None:
    tmp.mkdir(parents=True, exist_ok=True)
    segs, all_words, t = [], [], 0.0
    prev = None
    trans_at = []  # (zaman, gecis tipi) - whoosh efekti icin
    xf_v, xf_a = [], []
    for i, clip in enumerate(spec["clips"]):
        seg, words = _segment(clip, i, tmp, prev)
        d = _dur(seg)
        if i:
            # sahne gecisi: cizgi roman paneli gibi kayma/zoom; "cut" = sert kesme (WRONG damgasi gibi)
            kind = clip.get("trans") or TRANSITIONS[(i - 1) % len(TRANSITIONS)]
            xd = HARD_CUT if kind == "cut" else XFADE_DUR
            t -= xd
            xf_v.append((kind if kind != "cut" else "fade", xd, t))
            if kind != "cut":
                trans_at.append(t)
        all_words += [{**w, "start": w["start"] + t, "end": w["end"] + t} for w in words]
        print(f"  seg {i}: {d:.2f} s @ {t:.2f}  {' '.join(w['word'] for w in words)}")
        t += d
        segs.append(seg)
        prev = seg
    total = t

    joined = tmp / "joined.mp4"
    inputs = []
    for s in segs:
        inputs += ["-i", str(s)]
    fc, vlast, alast = [], "[0:v]", "[0:a]"
    for k, (kind, xd, off) in enumerate(xf_v, start=1):
        fc.append(f"{vlast}[{k}:v]xfade=transition={kind}:duration={xd:.3f}:offset={off:.3f}[v{k}]")
        fc.append(f"{alast}[{k}:a]acrossfade=d={xd:.3f}:c1=tri:c2=tri[a{k}]")
        vlast, alast = f"[v{k}]", f"[a{k}]"
    # gecis whoosh'lari: filtrelenmis gurultu, kisa yukselip duser
    if trans_at:
        n = len(segs)
        for j, ta in enumerate(trans_at):
            inputs += ["-f", "lavfi", "-t", "0.45", "-i", f"anoisesrc=c=pink:r={SR}:a=0.5"]
            delay = int(max(0.0, ta - 0.12) * 1000)
            fc.append(f"[{n + j}:a]highpass=f=600,lowpass=f=5000,afade=t=in:d=0.2,afade=t=out:st=0.2:d=0.25,"
                      f"volume={WHOOSH_VOL},aformat=channel_layouts=stereo,adelay={delay}|{delay}[w{j}]")
        ws = "".join(f"[w{j}]" for j in range(len(trans_at)))
        fc.append(f"{alast}{ws}amix=inputs={1 + len(trans_at)}:duration=first:normalize=0[aout]")
        alast = "[aout]"
    _run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(fc), "-map", vlast, "-map", alast,
          "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-ar", str(SR), "-ac", "2", str(joined)])

    ass = tmp / "captions.ass"
    sr.write_captions(all_words, [(0, total + 1, "fill")], ass)

    fc = (f"[0:v]subtitles='{ffmpeg_path_escape(ass)}':fontsdir='{ffmpeg_path_escape(sr.FONT_DIR)}'[v];"
          f"[0:a]asplit=2[dlg][key]")
    inputs = ["-i", str(joined)]
    if spec.get("music"):
        inputs += ["-stream_loop", "-1", "-i", str(spec["music"])]
        fc += (f";[1:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,volume={spec.get('music_volume', 0.12)},"
               f"afade=t=out:st={max(0, total - 1.2):.3f}:d=1.2[bed];"
               f"[bed][key]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=300[duck];"
               f"[dlg][duck]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    else:
        fc += ";[dlg]loudnorm=I=-14:TP=-1.5:LRA=11[a];[key]anullsink"
    _run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
          "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "192k", "-ar", str(SR), "-movflags", "+faststart", str(out_path)])
    print(f"OK {out_path}  {total:.1f} s")
