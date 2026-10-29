"""Tarifler: birden cok araci zincirleyen tek tik akislar.

podcast_recipe : uzun video -> Gemini anlari -> her an icin ayri proje (9:16 kadraj + altyazi + manset)
story_recipe   : sahne listesi [{media, text}] -> her replik seslendirilir, klipler replik suresine gore dizilir,
                 gecisler + muzik (konusmada kisilir) + altyazi. Gizmo (Puck) ve What If (anlatici) formatlari icin.
"""
from __future__ import annotations

import shutil

from studio.backend import ai_tools
from studio.backend.jobs import handler, progress
from studio.backend.store import PROJECTS, load, new_item, new_project, register_media, save, track


class _Sub(dict):
    """Ana isin ilerlemesini alt adimlara bolmek icin sahte is kaydi."""


def _sub(job: dict, pid: str, args: dict, lo: float, hi: float) -> dict:
    s = _Sub(id=job["id"], pid=pid, kind=job["kind"], args=args, status="running", progress=0.0, message="")

    def relay(frac, msg=""):
        progress(job, lo + (hi - lo) * frac, msg)
    s["_relay"] = relay
    return s


# jobs.progress alt is kaydinda cagrildiginda ana ise aktar
_orig_progress = progress


def _patched(job, frac, message=""):
    if isinstance(job, _Sub):
        job["_relay"](frac, message)
    else:
        _orig_progress(job, frac, message)


ai_tools.progress = _patched  # ai_tools icindeki progress cagrilari alt is olarak calisabilsin


def _captions(job: dict, pid: str, lo: float, hi: float) -> None:
    from studio.backend import tools
    tools.progress = _patched
    tools.captions(_sub(job, pid, {"language": "auto"}, lo, hi))


@handler("podcast_recipe")
def podcast_recipe(job: dict) -> dict:
    pid, a = job["pid"], job["args"]
    src_file = PROJECTS / pid / "media" / a["media"]
    n = int(a.get("clips", 5))
    ai_tools.moments(_sub(job, pid, {"media": a["media"], "clips": n, "min": a.get("min", 20),
                                     "max": a.get("max", 50)}, 0.0, 0.35))
    p = load(pid)
    url = f"/media/{pid}/{src_file.name}"
    found = sorted([m for m in p.get("moments", []) if m["src"] == url], key=lambda m: -(m.get("score") or 0))[:n]
    created = []
    for i, m in enumerate(found):
        lo = 0.35 + 0.65 * i / max(1, len(found))
        hi = 0.35 + 0.65 * (i + 1) / max(1, len(found))
        q = new_project(f"{p['name']} · {m['title'][:40]}")
        qid = q["id"]
        info = register_media(qid, src_file)  # kaynak kopyalanir (projeler bagimsiz kalsin)
        # transcript onbellegini de tasi (tekrar Whisper calismasin)
        tc = PROJECTS / pid / "cache" / f"tr_{src_file.stem}"
        if tc.exists():
            shutil.copytree(tc, PROJECTS / qid / "cache" / f"tr_{src_file.stem}", dirs_exist_ok=True)
        q = load(qid)
        it = new_item("video", info["url"], 0, m["start"], m["end"], props={"fit": "cover"})
        track(q, "video")["items"].append(it)
        track(q, "overlay")["items"].append(new_item(
            "text", None, 0, 0, 3.0, fadeIn=0.1, fadeOut=0.2,
            props={"text": m["title"], "size": 72, "color": "#ffffff", "x": 0.5, "y": 0.16, "scale": 1, "card": True}))
        save(qid, q)
        ai_tools.reframe(_sub(job, qid, {"item_id": it["id"]}, lo, lo + (hi - lo) * 0.7))
        _captions(job, qid, lo + (hi - lo) * 0.7, hi)
        created.append({"id": qid, "title": m["title"]})
    return {"projects": created}


@handler("story_recipe")
def story_recipe(job: dict) -> dict:
    """args: scenes=[{media, text, style?}], voice='Puck', speed=1.1, transition='slide-left', music=<library mp3>"""
    pid, a = job["pid"], job["args"]
    scenes = a["scenes"]
    voice = a.get("voice", "Puck")
    t = 0.0
    p = load(pid)
    for k in ("video", "voice", "music"):
        track(p, k)["items"] = [] if a.get("replace", True) else track(p, k)["items"]
    save(p["id"], p)
    for i, sc in enumerate(scenes):
        lo, hi = 0.85 * i / len(scenes), 0.85 * (i + 1) / len(scenes)
        dur_voice = 0.0
        if sc.get("text"):
            r = ai_tools.tts(_sub(job, pid, {"text": sc["text"], "style": sc.get("style", "Energetic, expressive, fast."),
                                             "voice": voice, "speed": a.get("speed", 1.1), "at": t + 0.15}, lo, hi))
            dur_voice = r["duration"] + 0.35
        p = load(pid)
        m = next(x for x in p["media"] if x["name"] == sc["media"])
        clip_d = m["duration"] if m["kind"] == "video" else 3.0
        seg = max(dur_voice, float(sc.get("min", 2.0)))
        seg = min(seg, clip_d) if m["kind"] == "video" else seg
        it = new_item("image" if m["kind"] == "image" else "video", m["url"], t, 0, seg,
                      volume=0 if sc.get("text") else 1, props={"fit": "cover"})
        if i > 0 and a.get("transition", "slide-left"):
            it["transition"] = {"type": a.get("transition", "slide-left"), "dur": 0.35}
        track(p, "video")["items"].append(it)
        save(pid, p)
        t += seg
    if a.get("music"):
        p = load(pid)
        info = next((x for x in p["media"] if x["name"] == a["music"]), None)
        if info is None:
            from pathlib import Path
            info = register_media(pid, Path("assets/music") / a["music"])
            p = load(pid)
        track(p, "music")["items"].append(new_item("audio", info["url"], 0, 0, min(t, info["duration"]), volume=0.35,
                                                   fadeOut=1.0, props={"duck": True, "duckLevel": 0.25}))
        save(pid, p)
    _captions(job, pid, 0.88, 1.0)
    return {"duration": round(t, 2), "scenes": len(scenes)}
