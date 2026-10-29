"""'What if' Short montaji: AI gorselleri (Ken Burns) + Veo klibi, sahne gecisleri, buyuk ortali ekran
yazilari (pop animasyonu), ust kart manset, muzik (yoksa sentetik ambiyans taban)."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from smart_render import FONT_DIR, make_headline_card, write_captions
from utils import ffmpeg_path_escape, ffprobe_duration

W, H, FPS = 1080, 1920, 30
XFADE = 0.35
TEXT_Y = 1430
NARR_LEAD = 0.15  # sahne basladiktan sonra anlatimin girdigi an (ilk sahnede 0: ses hemen baslar)
VIDEO_SKIP = 0.7
NARR_TAIL = 0.3  # anlatim bittikten sonra gecise kadar bosluk (goruntu nefes alsin)
TTS_SPEED = 1.15  # Gemini TTS dogal ama biraz yavas konusuyor

# ucretsiz katmanda her TTS modelinin ayri, kucuk gunluk kotasi var; biri dolunca siradakine gecilir
# 3.8 modelleri talimati sesli okuyor; onlara sadece [duygu etiketi] + cumle gonderilir
TTS_MODELS = ["gemini-3.8-flash-tts",
              "gemini-2.5-pro-preview-tts", "gemini-2.5-flash-preview-tts", "gemini-3.1-flash-tts-preview"]
TTS_VOICE = "Fenrir"
TTS_BASE_STYLE = ("You are a captivating documentary narrator for a science short. Speak at a natural, "
                  "confident storytelling pace (not slow), with clear emotion and emphasis on the key numbers.")


def gemini_tts(text: str, style: str, out: Path, tag: str = "captivating documentary narrator") -> float:
    """Gemini TTS: stil talimatini anlar (soru tonu, gerilim, vurgu). 24kHz mono wav yazar."""
    import os
    import wave

    from dotenv import load_dotenv
    from google import genai
    from google.genai import types

    load_dotenv(".env")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    prompt = f"{TTS_BASE_STYLE} {style} Say only this line: {text}"
    import time

    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE))))
    r = None
    for attempt in range(4):
        for model in TTS_MODELS:
            try:
                contents = f"[{tag}] {text}" if model.startswith("gemini-3.8") else prompt
                r = client.models.generate_content(model=model, contents=contents, config=config)
                break
            except Exception as e:
                if "RESOURCE_EXHAUSTED" not in str(e):
                    raise
                print(f"  {model} kota dolu, siradaki model deneniyor...", flush=True)
        if r is not None:
            break
        print("  tum TTS modelleri kota sinirinda, 45 sn bekleniyor...", flush=True)
        time.sleep(45)
    if r is None:
        raise RuntimeError("TTS kotasi doldu (tum modeller)")
    pcm = r.candidates[0].content.parts[0].inline_data.data
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)
    return len(pcm) / 48000


def _run(cmd: list[str], what: str) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg {what} basarisiz\n{r.stderr[-2500:]}")


def _crop_to_portrait(cx: float) -> str:
    """Kaynagi 9:16'ya kirpar; cx = yatay merkez (0-1)."""
    return (
        f"crop='min(iw,ih*9/16)':'min(ih,iw*16/9)':"
        f"'max(0,min(iw-min(iw,ih*9/16),iw*{cx}-min(iw,ih*9/16)/2))':'(ih-min(ih,iw*16/9))/2'"
    )


def render_scene(scene: dict, out: Path) -> None:
    dur = scene["dur"]
    frames = round(dur * FPS)
    cx = scene.get("cx", 0.5)
    src = Path(scene["src"])
    if src.suffix.lower() in (".mp4", ".mov"):
        # Veo klipleri ilk ~0.7 sn neredeyse duragan (goruntuden aciliyor): hareketin icinden basla
        clip_dur = ffprobe_duration(src)
        if "start" not in scene:
            scene["start"] = round(min(VIDEO_SKIP, max(0.0, clip_dur - dur)), 3)
        # anlatim klipten uzunsa klibi hafifce yavaslat; yoksa klip erken biter ve xfade zinciri donar
        avail = min(clip_dur, scene.get("end", clip_dur)) - scene["start"]
        slow = f"setpts=PTS*{dur / avail:.4f}," if avail < dur else ""
        punch = ""
        if scene.get("punch"):
            # ilk karede 'darbe': %12 yakindan baslayip 0.5 sn'de normale doner
            punch = (f",scale=w='trunc({W}*(1+0.12*max(0,1-t/0.5))/2)*2':h=-2:eval=frame,"
                     f"crop={W}:{H}")
        vf = (f"{slow}{_crop_to_portrait(cx)},scale={W}:{H}:flags=lanczos,fps={FPS}{punch},"
              f"eq=contrast=1.05:saturation=1.1,setsar=1,format=yuv420p")
        _run(["ffmpeg", "-y", "-ss", str(scene["start"]), "-i", str(src), "-vf", vf,
              "-frames:v", str(frames), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", str(out)],
             f"sahne {src.name}")
        return
    # Ken Burns: yavas yakinlasma (ya da zoom_out ile uzaklasma)
    z0, z1 = (1.12, 1.0) if scene.get("zoom_out") else (1.0, 1.12)
    zexpr = f"{z0}+({z1}-{z0})*on/{frames}"
    vf = (
        f"{_crop_to_portrait(cx)},scale={W * 2}:{H * 2}:flags=lanczos,"
        f"zoompan=z='{zexpr}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
        f"eq=contrast=1.05:saturation=1.1,setsar=1,format=yuv420p"
    )
    _run(["ffmpeg", "-y", "-loop", "1", "-i", str(src), "-vf", vf, "-frames:v", str(frames),
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", str(out)], f"sahne {src.name}")


ASS_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Big,Montserrat Thin,104,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,1,0,1,8,6,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ts(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _markup(text: str) -> str:
    """*vurgu* -> sari."""
    out, on = [], False
    for part in text.split("*"):
        if part:
            out.append((r"{\c&H00E5FF&}" if on else r"{\c&HFFFFFF&}") + part.upper())
        on = not on
    return "".join(out)


def write_texts(items: list[tuple[float, float, str]], path: Path) -> None:
    lines = [ASS_HEADER]
    for a, b, text in items:
        anim = (r"{\an5\pos(" + f"{W // 2},{TEXT_Y}" + r")\fscx60\fscy60\t(0,120,\fscx110\fscy110)"
                r"\t(120,200,\fscx100\fscy100)\fad(0,150)}")
        lines.append(f"Dialogue: 0,{_ts(a)},{_ts(b)},Big,,0,0,0,,{anim}{_markup(text)}")
    path.write_text("\n".join(lines), encoding="utf-8")


GAP_MAX: float | None = None  # ayarliysa kelimeler arasi bosluk bu kadara indirilir (nefessiz akis)


def _tighten(wav: Path, words: list[dict]) -> tuple[Path, list[dict]]:
    """Kelimeler arasi sessizlikleri (ve icindeki TTS hisirtisini) keser: konusma nefes almadan akar.
    Konusma bolgeleri whisper kelime zamanlarindan cikarilir, kenarlarda kisa fade ile tiklama olmaz."""
    if not words:
        return wav, words
    pad_a, pad_b = 0.03, 0.07
    regions: list[list[float]] = []
    for w in words:
        a, b = max(0.0, w["start"] - pad_a), w["end"] + pad_b
        if regions and a - regions[-1][1] <= GAP_MAX:
            regions[-1][1] = max(regions[-1][1], b)
        else:
            regions.append([a, b])
    total = ffprobe_duration(wav)
    regions[-1][1] = min(total, regions[-1][1] + 0.08)  # son kelime (uzayan 'Just...') kirpilmasin
    fc, labels, shift, new_words, t_out = "", [], [], [], 0.0
    for k, (a, b) in enumerate(regions):
        b = min(b, total)
        fc += (f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,"
               f"afade=t=in:d=0.01,afade=t=out:st={max(0.0, b - a - 0.03):.3f}:d=0.03[r{k}];")
        labels.append(f"[r{k}]")
        shift.append((a, b, t_out - a))
        t_out += b - a
    fc += f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1[o]"
    out = wav.with_name(wav.stem + f"_tight{GAP_MAX}.wav")
    _run(["ffmpeg", "-y", "-i", str(wav), "-filter_complex", fc, "-map", "[o]", str(out)], "bosluk kirp")
    for w in words:
        a, b, off = next((r for r in shift if r[0] <= w["start"] + 0.05 < r[1] + 0.05), shift[-1])
        new_words.append({**w, "start": max(0.0, w["start"] + off), "end": min(t_out, w["end"] + off)})
    return out, new_words


def _align_to_script(words: list[dict], text: str) -> list[dict]:
    """Whisper'in yanlis duydugu kelimeleri ('atoms' -> 'Adam's') senaryo metniyle degistirir;
    boylece altyazi konusmayla birebir ayni olur. Zamanlar whisper'dan gelir."""
    import difflib

    norm = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())
    script = text.split()
    sm = difflib.SequenceMatcher(a=[norm(w["word"]) for w in words], b=[norm(x) for x in script], autojunk=False)
    out: list[dict] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal" or (op == "replace" and i2 - i1 == j2 - j1):
            out += [{**words[i], "word": " " + script[j]} for i, j in zip(range(i1, i2), range(j1, j2))]
        elif op == "replace" and j2 - j1 == 1:
            # '99 .99 %' gibi parcalanmis tek kelimeyi birlestir
            out.append({"word": " " + script[j1], "start": words[i1]["start"], "end": words[i2 - 1]["end"]})
        elif op == "delete":
            continue
        elif op == "replace":
            out += words[i1:i2]
    return out


def _narrate(scenes: list[dict], tmp: Path, voice_fx: str = "") -> list[tuple[Path, float, list[dict]] | None]:
    """Her 'say' metni icin Chatterbox sesi (onbellekli) + kelime zamanlari (faster-whisper).
    Sahne suresini anlatim sigacak kadar uzatir."""
    import hashlib

    from faster_whisper import WhisperModel

    out: list[tuple[Path, float, list[dict]] | None] = []
    whisper = None
    for sc in scenes:
        text = sc.get("say")
        if not text:
            out.append(None)
            continue
        style = sc.get("style", "")
        key = hashlib.md5(f"{TTS_MODELS[0]}|{sc.get('tag', '')}|{TTS_VOICE}|{TTS_BASE_STYLE}|{style}|{text}".encode()).hexdigest()[:12]
        wav = Path(sc["wav"]) if sc.get("wav") else tmp / "narr" / f"{key}.wav"
        if not wav.exists():
            gemini_tts(text, style, wav, sc.get("tag", "captivating documentary narrator"))
        # bas/son sessizligi kirp + hafif hizlandir (ton bozulmadan)
        chain = voice_fx
        if GAP_MAX is not None:
            # enerji tabanli: -40 dB altindaki her duraklama (TTS hisirtisi dahil) GAP_MAX'a iner
            gap_fx = (f"silenceremove=stop_periods=-1:stop_duration={GAP_MAX + 0.04:.2f}:"
                      f"stop_threshold=-40dB:stop_silence={GAP_MAX:.2f}")
            chain = f"{gap_fx},{chain}" if chain else gap_fx
        voice_fx = chain
        fx_key = hashlib.md5(voice_fx.encode()).hexdigest()[:6] if voice_fx else ""
        fast = wav.with_name(wav.stem + f"_x{TTS_SPEED}{fx_key}.wav")
        if not fast.exists():
            # voice_fx: kanala ozel ses imzasi (pitch/formant + EQ), hazir TTS sesini ayirt edilir kilar
            _run(["ffmpeg", "-y", "-i", str(wav), "-af",
                  "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                  "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                  f"atempo={TTS_SPEED}" + (f",{voice_fx}" if voice_fx else ""), str(fast)], "tts kirp")
        wav = fast
        dur = ffprobe_duration(wav)
        if whisper is None:
            # kisa anlatim dosyalari icin CPU yeterli (bu makinede CUDA cublas eksik)
            whisper = WhisperModel("small", device="cpu", compute_type="int8")
        segs, _ = whisper.transcribe(str(wav), language="en", word_timestamps=True)
        words = [{"word": w.word, "start": w.start, "end": w.end} for seg in segs for w in seg.words]
        # bazi TTS modelleri [duygu etiketini] de sesli okuyor: cumlenin ilk kelimesinden oncesini kes
        first = re.sub(r"[^a-z]", "", text.split()[0].lower())
        idx = next((k for k, w in enumerate(words) if re.sub(r"[^a-z]", "", w["word"].lower()) == first), 0)
        if idx > 0:
            cut = max(0.0, words[idx]["start"] - 0.05)
            trimmed = wav.with_name(wav.stem + "_notag.wav")
            _run(["ffmpeg", "-y", "-ss", f"{cut:.3f}", "-i", str(wav), str(trimmed)], "etiket kirp")
            wav = trimmed
            dur = ffprobe_duration(wav)
            words = [{**w, "start": w["start"] - cut, "end": w["end"] - cut} for w in words[idx:]]
        words = _align_to_script(words, text)
        if GAP_MAX is not None:
            wav, words = _tighten(wav, words)
            dur = ffprobe_duration(wav)
        sc["dur"] = max(sc.get("dur", 0), sc.get("lead", NARR_LEAD) + dur + sc.get("tail", NARR_TAIL) + XFADE)
        out.append((wav, dur, words))
    return out


# ---------------- HUD (oyun gibi canli gosterge paneli) ----------------

HUD_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hud,Consolas,46,&H00FFFF00,&H00FFFF00,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,7,0,0,0,1
Style: Box,Consolas,20,&H00000000,&H00000000,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
HUD_X, HUD_Y = 44, 330
HUD_STEP = 0.1


def _lerp(a: float, b: float, f: float) -> float:
    # buyuk olcek farklarinda (basinc, derinlik) logaritmik gecis daha dogal akar
    if a > 0 and b > 0 and max(a, b) / min(a, b) > 20:
        return a * (b / a) ** f
    return a + (b - a) * f


def _fmt_num(v: float, unit: str) -> str:
    if abs(v) < 10 and unit == "atm":
        return f"{v:.1f} {unit}"
    return f"{round(v):,} {unit}"


def _hud_line(layer: int, st: str, e: str, style: str, tags: str, body: str) -> str:
    return f"Dialogue: {layer},{st},{e},{style},,0,0,0,,{{{tags}}}{body}"


def _rect(w: int, h: int) -> str:
    return f"m 0 0 l {w} 0 {w} {h} 0 {h}"


def write_hud(scenes: list[dict], starts: list[float], total: float, t0: float, path: Path) -> None:
    lines = [HUD_HEADER]
    lines.append(_hud_line(0, _ts(t0), _ts(total), "Box",
                           rf"\an7\pos({HUD_X - 18},{HUD_Y - 16})\p1\1c&H000000&\1a&H45&",
                           _rect(560, 300) + r"{\p0}"))
    bar_x, bar_y = HUD_X + 170, HUD_Y + 3 * 62 + 10
    for i, sc in enumerate(scenes):
        hud = sc.get("hud")
        if not hud:
            continue
        a = max(starts[i], t0)
        b = starts[i + 1] if i + 1 < len(scenes) else total
        t = a
        while t < b - 1e-6:
            f = (t - starts[i]) / max(1e-6, b - starts[i])
            depth = _lerp(*hud["depth"], f)
            temp = _lerp(*hud["temp"], f)
            pres = _lerp(*hud["pressure"], f)
            integ = max(0.0, _lerp(*hud["integrity"], f))
            label = hud.get("label", "DEPTH")
            warn = integ < 30
            blink = warn and int(t / 0.25) % 2 == 0
            col = r"\1c&H0000FF&" if warn else ""
            st, e = _ts(t), _ts(min(b, t + HUD_STEP))
            rows = [f"{label:<9}{_fmt_num(depth, 'km')}", f"{'TEMP':<9}{round(temp):+,} \u00b0C",
                    f"{'PRESSURE':<9}{_fmt_num(pres, 'atm')}", "SUIT"]
            for r_i, txt in enumerate(rows):
                lines.append(_hud_line(1, st, e, "Hud", rf"\pos({HUD_X},{HUD_Y + r_i * 62}){col}", txt))
            lines.append(_hud_line(1, st, e, "Box", rf"\an7\pos({bar_x},{bar_y})\p1\1c&HFFFFFF&\1a&HB0&",
                                   _rect(300, 34) + r"{\p0}"))
            bar_w = int(300 * integ / 100)
            if bar_w > 0:
                bar_col = "&H00FF00&" if integ >= 60 else ("&H00D7FF&" if integ >= 30 else "&H0000FF&")
                alpha = "&HFF&" if blink else "&H00&"
                lines.append(_hud_line(2, st, e, "Box", rf"\an7\pos({bar_x},{bar_y})\p1\1c{bar_col}\1a{alpha}",
                                       _rect(bar_w, 34) + r"{\p0}"))
            t += HUD_STEP
    path.write_text("\n".join(lines), encoding="utf-8")


SFX_EXPR = {
    # iki vurusluk kalp atisi (~75 bpm)
    "heartbeat": "0.9*sin(2*PI*52*t)*exp(-16*mod(t,0.8))+0.6*sin(2*PI*46*t)*exp(-16*mod(t+0.58,0.8))",
    # alarm bip'leri
    "alarm": "0.18*sin(2*PI*880*t)*lt(mod(t,0.5),0.12)",
    # yukselen gerilim: frekansi tirmanan ton + kabaran gurultu ({D} = efekt suresi)
    "riser": "0.5*pow(t/{D},2)*(0.35*sin(2*PI*(180+1400*pow(t/{D},2))*t)+0.65*(2*random(0)-1))",
    # sub-bass darbesi: 40-90 Hz arasi dusen ton + kisa gurultu patlamasi
    "boom": "0.95*sin(2*PI*(42+60*exp(-7*t))*t)*exp(-1.8*t)+0.45*(2*random(0)-1)*exp(-9*t)",
    # alcak gumburtu
    "rumble": "0.8*(2*random(0)-1)",
}
SFX_POST = {"riser": "highpass=f=250", "rumble": "lowpass=f=140,lowpass=f=140", "boom": "lowpass=f=900"}
SFX_FADE_IN = {"boom": 0.0, "riser": 0.05}


def render_whatif(spec: dict, out_path: Path, tmp: Path) -> None:
    tmp.mkdir(parents=True, exist_ok=True)
    scenes = spec["scenes"]
    scenes[0].setdefault("lead", 0.0)
    scenes[0].setdefault("punch", True)
    global TTS_VOICE, TTS_SPEED
    TTS_VOICE = spec.get("voice", TTS_VOICE)
    TTS_SPEED = spec.get("speed", TTS_SPEED)
    global GAP_MAX, NARR_LEAD, NARR_TAIL
    GAP_MAX = spec.get("gap_max", GAP_MAX)
    NARR_LEAD = spec.get("narr_lead", NARR_LEAD)
    NARR_TAIL = spec.get("narr_tail", NARR_TAIL)
    narr = _narrate(scenes, tmp, spec.get("voice_fx", ""))
    if spec.get("loop") and scenes[-1].get("loop_tail"):
        # dikissiz loop: son sahne, acilis klibinin ilk sahneden hemen onceki kareleri; video bitince
        # tam kaldigi kareden yeniden baslar. Acilistaki zoom darbesi de bu yuzden kapali.
        tail = scenes[-1]
        tail["src"] = scenes[0]["src"]
        scenes[0]["punch"] = False
        scenes[0]["start"] = max(VIDEO_SKIP, tail["dur"])
        tail["start"] = scenes[0]["start"] - tail["dur"]
    parts = []
    for i, sc in enumerate(scenes):
        p = tmp / f"scene{i}.mp4"
        render_scene(sc, p)
        parts.append(p)

    # xfade zinciri ve her sahnenin cikti baslangici
    starts = [0.0]
    total = scenes[0]["dur"]
    chain, last = "", "0:v"
    for i in range(1, len(scenes)):
        offset = total - XFADE
        starts.append(offset)
        trans = scenes[i].get("transition", "fade")
        chain += f"[{last}][{i}:v]xfade=transition={trans}:duration={XFADE}:offset={offset:.3f}[x{i}];"
        last = f"x{i}"
        total = offset + scenes[i]["dur"]

    ass = tmp / "texts.ass"
    if any(narr):
        # anlatimli: konusmayla kelime kelime senkron dinamik altyazi
        words = [{**w, "start": starts[i] + scenes[i].get("lead", NARR_LEAD) + w["start"],
                  "end": starts[i] + scenes[i].get("lead", NARR_LEAD) + w["end"]}
                 for i, n in enumerate(narr) if n for w in n[2]]
        import smart_render
        old = smart_render.MAX_GROUP_WORDS, smart_render.MAX_GROUP_CHARS
        if spec.get("caption_words"):
            smart_render.MAX_GROUP_WORDS, smart_render.MAX_GROUP_CHARS = spec["caption_words"], 14
        write_captions(words, [(0.0, total, "fill")], ass)
        smart_render.MAX_GROUP_WORDS, smart_render.MAX_GROUP_CHARS = old
    else:
        texts = []
        for i, sc in enumerate(scenes):
            if sc.get("text"):
                a = starts[i] + sc.get("text_delay", 0.15)
                b = (starts[i + 1] if i + 1 < len(scenes) else total) - 0.05
                texts.append((a, b, sc["text"]))
        write_texts(texts, ass)
    card = tmp / "card.png"
    cw, _ = make_headline_card(spec["title"], card)
    title_end = scenes[0]["dur"] - XFADE
    hud_filter = ""
    game_hud = None
    if any(sc.get("hud") for sc in scenes):
        hud_start = spec.get("hud_start", title_end)
        if spec.get("hud_style") == "timer":
            # kronometre: ustte akan T+ sayaci + enerji bari
            from timer_hud import render_timer_hud
            game_hud = tmp / "hud_timer.mov"
            render_timer_hud(scenes, starts, total, hud_start, game_hud, tmp, spec.get("energy_label", "HIROSHIMA"))
        elif spec.get("hud_style") == "game":
            # oyun arayuzu: kare kare cizilen alfa kanalli katman, altyazinin altinda kalir
            from game_hud import render_game_hud
            game_hud = tmp / "hud_game.mov"
            render_game_hud(scenes, starts, total, hud_start, game_hud, tmp, spec.get("hud_rows"))
        else:
            hud_ass = tmp / "hud.ass"
            write_hud(scenes, starts, total, hud_start, hud_ass)
            hud_filter = f",subtitles='{ffmpeg_path_escape(hud_ass)}'"

    inputs = []
    for p in parts:
        inputs += ["-i", str(p)]
    n = len(parts)
    inputs += ["-loop", "1", "-t", f"{title_end:.2f}", "-i", str(card)]
    base = f"[{last}]"
    pre = ""
    if game_hud:
        inputs += ["-i", str(game_hud)]
        pre = f"{base}[{n + 1}:v]overlay=0:0:format=auto[hv];"
        base = "[hv]"
    fc = (
        chain + pre
        + f"{base}subtitles='{ffmpeg_path_escape(ass)}':fontsdir='{ffmpeg_path_escape(FONT_DIR)}'{hud_filter}[s];"
        f"[{n}:v]format=rgba,fade=t=in:st=0.1:d=0.3:alpha=1,fade=t=out:st={title_end - 0.3:.2f}:d=0.3:alpha=1[c];"
        f"[s][c]overlay=x={(W - cw) // 2}:y='140+40*max(0\\,1-(t-0.1)/0.3)':enable='lt(t,{title_end:.2f})'[v]"
    )

    # ses: muzik varsa o (anlatimda kisilir); yoksa ve sahneler videoysa sadece kendi ortam sesleri,
    # hicbiri yoksa sentetik ambiyans taban
    mix: list[str] = []
    idx = n + 2 if game_hud else n + 1
    video_scenes = [i for i, sc in enumerate(scenes)
                    if Path(sc["src"]).suffix.lower() in (".mp4", ".mov") and sc.get("keep_audio", True)]
    if spec.get("music") or not video_scenes:
        if spec.get("music"):
            inputs += ["-i", str(spec["music"])]
            fc += f";[{idx}:a]atrim=0:{total:.3f},volume={spec.get('music_volume', 0.5)}[bed]"
        else:
            pad = ("aevalsrc='0.10*sin(2*PI*55*t)+0.06*sin(2*PI*82.4*t)+0.05*sin(2*PI*110*t)*(0.6+0.4*sin(2*PI*0.15*t))"
                   "+0.03*sin(2*PI*164.8*t)*(0.5+0.5*sin(2*PI*0.1*t))':s=48000:d=" + f"{total:.3f}")
            inputs += ["-f", "lavfi", "-i", pad]
            fc += f";[{idx}:a]aecho=0.8:0.8:120|300:0.35|0.25,lowpass=f=1800[bed]"
        bed_out = 0.05 if spec.get("loop") else 1.5
        bed_in = 0.05 if spec.get("loop") else 1.0
        fc += (f";[bed]aformat=channel_layouts=stereo,afade=t=in:d={bed_in},"
               f"afade=t=out:st={total - bed_out:.3f}:d={bed_out}[bedf]")
        mix.append("[bedf]")
        idx += 1
    # her video sahnesinin kendi ortam sesi (Veo: dalga, ruzgar, sehir), sahne araliginda yumusak gecisle
    for i in video_scenes:
        sc = scenes[i]
        amb_vol = sc.get("amb_volume", 0.45 if narr[i] else 0.9)
        amb_t = min(sc["dur"], sc["end"] - sc.get("start", 0)) if sc.get("end") else sc["dur"]
        inputs += ["-ss", str(sc.get("start", 0)), "-t", f"{amb_t:.3f}", "-i", str(sc["src"])]
        seam_in = spec.get("loop") and i == 0
        seam_out = spec.get("loop") and i == len(scenes) - 1
        fc += (f";[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,volume={amb_vol},"
               + ("" if seam_in else f"afade=t=in:d={XFADE},")
               + ("anull," if seam_out else f"afade=t=out:st={max(0.0, amb_t - XFADE):.3f}:d={XFADE},")
               + f"adelay={round(starts[i] * 1000)}:all=1[amb{i}]")
        mix.append(f"[amb{i}]")
        idx += 1
    for k, fx in enumerate(spec.get("sfx", [])):
        t_start = starts[fx["scene"]] + fx.get("offset", 0.0)
        # until_next: efekt sahnenin sonuna kadar surer (riser -> sonraki sahnedeki patlamaya baglanir)
        scene_end = starts[fx["scene"] + 1] if fx["scene"] + 1 < len(scenes) else total
        dur_fx = scene_end - t_start if fx.get("until_next") else min(total - t_start, fx.get("dur", total))
        expr = SFX_EXPR[fx["type"]].replace("{D}", f"{dur_fx:.3f}")
        post = SFX_POST.get(fx["type"], "")
        fade_in = fx.get("fade_in", SFX_FADE_IN.get(fx["type"], 0.8))
        fade_out = fx.get("fade_out", min(1.0, dur_fx / 2))
        inputs += ["-f", "lavfi", "-i", f"aevalsrc='{expr}':s=48000:d={dur_fx:.3f}"]
        fc += (f";[{idx}:a]{post + ',' if post else ''}aformat=channel_layouts=stereo,volume={fx.get('volume', 0.6)},"
               + (f"afade=t=in:d={fade_in}," if fade_in > 0 else "")
               + f"afade=t=out:st={max(0.0, dur_fx - fade_out):.3f}:d={fade_out},"
               f"adelay={round(t_start * 1000)}:all=1[fx{k}]")
        mix.append(f"[fx{k}]")
        idx += 1
    narr_labels = []
    for i, nr in enumerate(narr):
        if not nr:
            continue
        inputs += ["-i", str(nr[0])]
        fc += (f";[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,"
               f"adelay={round((starts[i] + scenes[i].get('lead', NARR_LEAD)) * 1000)}:all=1[n{i}]")
        narr_labels.append(f"[n{i}]")
        idx += 1
    if narr_labels:
        fc += (f";{''.join(narr_labels)}amix=inputs={len(narr_labels)}:duration=longest:normalize=0,"
               "acompressor=threshold=-20dB:ratio=3:attack=5:release=80,volume=1.4,asplit=2[voice][vsc]"
               )
        if "[bedf]" in mix:
            fc += ";[bedf][vsc]sidechaincompress=threshold=0.02:ratio=8:attack=10:release=400[bedd]"
            mix = ["[bedd]" if m == "[bedf]" else m for m in mix]
        else:
            fc += ";[vsc]anullsink"
        mix.append("[voice]")
    fc += (f";{''.join(mix)}amix=inputs={len(mix)}:duration=longest:normalize=0,atrim=0:{total:.3f},"
           "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")

    _run(["ffmpeg", "-y", *inputs, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
          "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out_path)], "montaj")
    for p in ([] if os.environ.get("KEEP_PARTS") else parts):
        p.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    d = Path("work/whatif_moon/flow")
    spec = {
        "title": "WHAT IF THE MOON WAS *2× CLOSER?*",
        "music": Path("assets/music/ancient_civilisations.mp3"),
        "music_volume": 0.35,
        "scenes": [
            {"src": d / "giant_moon.mp4", "amb_volume": 0.25,
             "style": "Ask it as a real, intriguing question with rising intonation and a short pause after 'Moon'.",
             "say": "What if the Moon... was suddenly twice as close?"},
            {"src": d / "normal_moon.mp4", "transition": "fadeblack", "amb_volume": 0.25,
             "say": "Right now, it's about three hundred eighty thousand kilometers away."},
            {"src": d / "giant_moon.mp4", "transition": "zoomin", "amb_volume": 0.25,
             "style": "Build wonder, emphasize 'twice as big'.",
             "say": "Cut that in half... and it looks twice as big."},
            {"src": d / "flood.mp4", "transition": "slideup", "amb_volume": 0.45,
             "style": "Start light, then turn ominous and tense on 'eight times stronger'.",
             "say": "Sounds beautiful? But the tides get eight times stronger, flooding coastal cities."},
            {"src": d / "farm.mp4", "transition": "fade", "amb_volume": 0.25,
             "style": "Calm and amazed.",
             "say": "Full moon nights? Four times brighter."},
            {"src": d / "eclipse.mp4", "transition": "fadeblack", "amb_volume": 0.25,
             "style": "Awe-struck.",
             "say": "And solar eclipses would last way longer."},
            {"src": d / "space.mp4", "transition": "slideup", "amb_volume": 0.25,
             "style": "Playful, direct question to the viewer, with a short pause after 'So'.",
             "say": "So... would you live under a Moon like that?"},
        ],
    }
    out = Path("output/whatif")
    out.mkdir(parents=True, exist_ok=True)
    render_whatif(spec, out / "whatif_moon_v6.mp4", Path("work/whatif_moon/tmp"))
    print("DONE")
