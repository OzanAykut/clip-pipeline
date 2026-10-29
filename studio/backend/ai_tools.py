"""AI araclari: mevcut klip-pipeline fonksiyonlarini Klip Studio projesine uygulayan is handler'lari.

Hepsi is kuyrugunda tek tek calisir (pipeline modulleri global ayar degistirir). Projeyi degistiren araclar
en guncel project.json'u yukleyip uzerine yazar; arayuz WebSocket ile degisikligi canli gorur.
"""
from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path

from studio.backend.jobs import handler, progress
from studio.backend.store import PROJECTS, find_item, load, new_item, register_media, save, track


def media_path(pid: str, src: str | None) -> Path | None:
    if not src or not src.startswith(f"/media/{pid}/"):
        return None
    f = PROJECTS / pid / "media" / src.split("/")[-1]
    return f if f.exists() else None


def transcript(pid: str, f: Path, lang: str = "auto") -> dict:
    """Medya basina onbellekli Whisper transcript'i (kelime zamanli)."""
    from transcribe import transcribe_video
    wd = PROJECTS / pid / "cache" / f"tr_{f.stem}"
    wd.mkdir(parents=True, exist_ok=True)
    return transcribe_video(f, wd, model_size="small", language=lang)


def words_of(tr: dict) -> list[dict]:
    return [w for s in tr["segments"] for w in s.get("words", [])]


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s)[:40].strip("_") or "x"


# ---------------- uzun videodan an bulma ----------------

@handler("moments")
def moments(job: dict) -> dict:
    """Gemini ile uzun videodaki en guclu anlari bulur -> project['moments'] (arayuzde listelenir, tek tikla eklenir)."""
    from dotenv import load_dotenv

    from select_moments import select_moments
    load_dotenv(".env")
    pid, a = job["pid"], job["args"]
    f = PROJECTS / pid / "media" / a["media"]
    progress(job, 0.05, "yazıya dökülüyor (uzun videoda birkaç dakika sürer)")
    tr = transcript(pid, f, a.get("language", "auto"))
    progress(job, 0.5, "Gemini anları arıyor")
    found = select_moments(tr, os.environ["GEMINI_API_KEY"], num_clips=int(a.get("clips", 8)),
                           min_dur=int(a.get("min", 20)), max_dur=int(a.get("max", 60)))
    p = load(pid)
    url = f"/media/{pid}/{f.name}"
    p["moments"] = [m for m in p.get("moments", []) if m.get("src") != url] + [
        {"src": url, "start": round(m["start"], 2), "end": round(m["end"], 2), "title": m["title"],
         "hook": m.get("hook", ""), "score": m.get("score")} for m in found]
    save(pid, p)
    return {"moments": len(found)}


# ---------------- akilli 9:16 kadraj ----------------

@handler("reframe")
def reframe(job: dict) -> dict:
    """Secili klibi yuz takipli 9:16 duzenle (konusan kisi / bolunmus ekran / letterbox) render edip klibin
    yerine koyar. smart_render.render_range (podcast pipeline'imizin kadraj motoru) kullanilir."""
    from smart_render import render_range
    pid, a = job["pid"], job["args"]
    p = load(pid)
    _, it = find_item(p, a["item_id"])
    f = media_path(pid, it.get("src"))
    if not f:
        raise RuntimeError("kadraj icin proje medyasi olan bir video sec")
    progress(job, 0.05, "konuşmalar yazıya dökülüyor")
    words = words_of(transcript(pid, f))
    progress(job, 0.3, "yüzler ve kesimler analiz ediliyor, 9:16 render")
    out = PROJECTS / pid / "cache" / f"{f.stem}_9x16_{it['in']:.1f}-{it['out']:.1f}.mp4"
    render_range(f, it["in"], it["out"], words, out, PROJECTS / pid / "cache" / "reframe_tmp",
                 split_people=a.get("split_people", True), noface=a.get("noface", "letterbox"))
    info = register_media(pid, out, copy=False)
    p = load(pid)
    _, it = find_item(p, a["item_id"])
    it.update({"src": info["url"], "in": 0.0, "out": round(info["duration"], 3)})
    it["props"].update({"fit": "cover", "x": 0.5, "y": 0.5, "scale": 1, "reframed": True})
    save(pid, p)
    return {"media": info["name"]}


# ---------------- seslendirme ----------------

VOICES = ["Puck", "Fenrir", "Zubenelgenubi", "Charon", "Kore", "Aoede", "Leda", "Zephyr", "Sadachbia", "Achird"]


@handler("tts")
def tts(job: dict) -> dict:
    """Gemini TTS ile replik uretir (gizmo_voice: etiket kirpma, sondaki cizirtiyi kesme, hizlandirma) ve
    seslendirme kanalina oynatma kafasindan ekler."""
    import gizmo_voice
    pid, a = job["pid"], job["args"]
    text = a["text"].strip()
    gizmo_voice.VOICE = a.get("voice", "Puck")
    gizmo_voice.SPEED = float(a.get("speed", 1.1))
    progress(job, 0.1, f"{gizmo_voice.VOICE} sesi üretiliyor")
    out = PROJECTS / pid / "cache" / "tts" / f"{_slug(gizmo_voice.VOICE)}_{_slug(text)}_{int(time.time())}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    gizmo_voice.make_line(text, a.get("style", "Energetic, expressive, fast-paced."), a.get("tag", "expressive"), out)
    info = register_media(pid, out, copy=True)
    p = load(pid)
    track(p, "voice")["items"].append(new_item("audio", info["url"], float(a.get("at", 0)), 0, info["duration"],
                                               props={"text": text}))
    save(pid, p)
    return {"media": info["name"], "duration": info["duration"]}


# ---------------- sessizlik / duraklama kesme ----------------

@handler("silence_cut")
def silence_cut(job: dict) -> dict:
    """Secili klipteki kelimeler arasi uzun bosluklari keser: klip konusma parcalarina bolunur, ardisik
    dizilir; ayni kanalda sonra gelen ogeler kazanilan sure kadar sola kayar (ripple)."""
    pid, a = job["pid"], job["args"]
    gap = float(a.get("min_gap", 0.35))
    p = load(pid)
    tr_, it = find_item(p, a["item_id"])
    f = media_path(pid, it.get("src"))
    if not f:
        raise RuntimeError("proje medyasi olan bir klip sec")
    progress(job, 0.1, "sessizlikler bulunuyor")
    # kesimler ses enerjisine gore (kelime zamanlari ±100 ms kayik, kopuk duyuluyordu); es tamamen silinmez
    from audio_cuts import smart_tighten
    ws = words_of(transcript(pid, f))  # kisik konusma sessizlik sanilmasin: kelime olan yer kesilmez
    ranges = [list(r) for r in smart_tighten(f, [(it["in"], it["out"])], max_gap=gap, keep=float(a.get("keep", 0.2)),
                                             words=ws)]
    ranges[0][0], ranges[-1][1] = max(ranges[0][0], it["in"]), min(ranges[-1][1], it["out"])
    sp = it.get("speed", 1) or 1
    old_end = it["start"] + (it["out"] - it["in"]) / sp
    p = load(pid)
    tr_, it = find_item(p, a["item_id"])
    idx = tr_["items"].index(it)
    pieces, t = [], it["start"]
    for s, e in ranges:
        nit = {**it, "id": it["id"] if not pieces else f"{it['id'][:5]}{len(pieces):03d}", "start": round(t, 3),
               "in": round(s, 3), "out": round(e, 3), "transition": it.get("transition") if not pieces else None,
               "props": dict(it["props"])}
        pieces.append(nit)
        t += (e - s) / sp
    saved = old_end - t
    tr_["items"][idx:idx + 1] = pieces
    for o in tr_["items"]:
        if o not in pieces and o["start"] >= old_end - 0.01:
            o["start"] = round(o["start"] - saved, 3)
    save(pid, p)
    return {"pieces": len(pieces), "saved_sec": round(saved, 2)}


# ---------------- B-roll ----------------

@handler("broll")
def broll(job: dict) -> dict:
    """Pexels'ten dikey B-roll (video, yoksa foto) bulup Metin/Gorsel kanalina ekler: tam ekran ya da kose (pip)."""
    from dotenv import load_dotenv

    from broll import fetch_broll
    load_dotenv(".env")
    pid, a = job["pid"], job["args"]
    progress(job, 0.2, f"Pexels: {a['query']}")
    src = fetch_broll(a["query"])
    if not src:
        raise RuntimeError("B-roll bulunamadı (PEXELS_API_KEY var mı?)")
    dst = PROJECTS / pid / "cache" / f"broll_{_slug(a['query'])}{src.suffix}"
    shutil.copy2(src, dst)
    info = register_media(pid, dst)
    dur = float(a.get("dur", 2.5))
    pip = a.get("mode", "full") == "pip"
    props = {"fit": "cover", "x": 0.5, "y": 0.5, "scale": 1}
    if pip:
        props = {"fit": "cover", "x": 0.26, "y": 0.27, "scale": 0.42, "radius": 28, "border": True}
    typ = "image" if info["kind"] == "image" else "video"
    p = load(pid)
    track(p, "overlay")["items"].append(new_item(typ, info["url"], float(a.get("at", 0)), 0,
                                                 min(dur, info["duration"] or dur), fadeIn=0.15, fadeOut=0.15,
                                                 volume=0, props=props))
    save(pid, p)
    return {"media": info["name"]}
