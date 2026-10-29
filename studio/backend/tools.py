"""Is kuyrugu handler'lari: disa aktarma + AI araclari (mevcut pipeline fonksiyonlarini sarar)."""
from __future__ import annotations

import json
import re
import subprocess
import time
import uuid
from pathlib import Path

from studio.backend.jobs import handler, progress
from studio.backend.store import PROJECTS, load, save

WEB = Path("studio/web")
BACKEND_URL = "http://127.0.0.1:8765"


def _media_path(pid: str, src: str | None) -> Path | None:
    if not src or not src.startswith(f"/media/{pid}/"):
        return None
    f = PROJECTS / pid / "media" / src.split("/")[-1]
    return f if f.exists() else None


@handler("captions")
def captions(job: dict) -> dict:
    """Otomatik altyazi: timeline'daki sesli ogeleri Whisper ile yaziya doker, kelimeleri kirpma/hiz/konuma gore
    timeline zamanina tasir ve altyazi kanalini doldurur (elle eklenmis altyazilar korunur).
    Hem video hem seslendirme ayni anda konusuyorsa seslendirme kanali onceliklidir."""
    from transcribe import transcribe_video

    pid = job["pid"]
    lang = job["args"].get("language", "auto")
    gap = float(job["args"].get("gap", 1.2))
    p = load(pid)
    sources = []  # (oncelik, item)
    for t in p["tracks"]:
        if t["kind"] in ("video", "voice") and not t.get("muted"):
            for it in t["items"]:
                if it["type"] in ("video", "audio") and _media_path(pid, it.get("src")):
                    sources.append((0 if t["kind"] == "voice" else 1, it))
    if not sources:
        raise RuntimeError("altyazi icin sesli video/seslendirme yok")
    cache: dict[str, list] = {}
    words: list[dict] = []
    for i, (prio, it) in enumerate(sorted(sources, key=lambda s: s[0])):
        f = _media_path(pid, it["src"])
        progress(job, i / len(sources), f"yazıya dökülüyor: {f.name}")
        if f.name not in cache:
            wd = PROJECTS / pid / "cache" / f"tr_{f.stem}"
            wd.mkdir(parents=True, exist_ok=True)
            tr = transcribe_video(f, wd, model_size="small", language=lang)
            cache[f.name] = [w for s in tr["segments"] for w in s.get("words", [])]
        sp = it.get("speed", 1) or 1
        for w in cache[f.name]:
            if it["in"] - 0.05 <= w["start"] < it["out"]:
                s = it["start"] + (w["start"] - it["in"]) / sp
                e = it["start"] + (min(w["end"], it["out"]) - it["in"]) / sp
                if any(not (e <= x["s"] or s >= x["e"]) for x in words if x["prio"] < prio):
                    continue  # oncelikli kaynakla cakisiyor
                words.append({"w": w["word"].strip(), "s": round(s, 3), "e": round(max(e, s + 0.05), 3), "prio": prio})
    words = sorted([w for w in words if w["w"]], key=lambda w: w["s"])
    blocks: list[list[dict]] = []
    for w in words:
        if not blocks or w["s"] - blocks[-1][-1]["e"] > gap:
            blocks.append([w])
        else:
            blocks[-1].append(w)
    p = load(pid)  # isleme surerken kullanici duzenlemis olabilir: en guncel hali uzerine yaz
    style = p.get("captionStyle", "pop")
    cap = next(t for t in p["tracks"] if t["kind"] == "caption")
    cap["items"] = [i for i in cap["items"] if not i.get("props", {}).get("auto")]
    for b in blocks:
        st = max(0.0, b[0]["s"] - 0.05)
        cap["items"].append({
            "id": uuid.uuid4().hex[:8], "type": "caption", "start": st, "in": 0, "out": round(b[-1]["e"] + 0.2 - st, 3),
            "speed": 1, "volume": 1, "fadeIn": 0, "fadeOut": 0, "transition": None,
            "props": {"auto": True, "style": style,
                      "words": [{"w": w["w"], "s": round(w["s"] - st, 3), "e": round(w["e"] - st, 3)} for w in b]}})
    cap["items"].sort(key=lambda i: i["start"])
    save(pid, p)
    return {"words": len(words), "blocks": len(blocks)}


@handler("export")
def export(job: dict) -> dict:
    """Remotion ile project.json -> MP4. Onizlemeyle ayni kompozisyon kullanilir (WYSIWYG)."""
    pid = job["pid"]
    p = load(pid)
    out_dir = PROJECTS / pid / "exports"
    out_dir.mkdir(exist_ok=True)
    name = f"{re.sub(r'[^A-Za-z0-9_-]+', '_', p['name'])[:40]}_{time.strftime('%H%M%S')}.mp4"
    out = (out_dir / name).resolve()
    props = (PROJECTS / pid / "cache" / "render_props.json")
    props.parent.mkdir(exist_ok=True)
    props.write_text(json.dumps({"project": p, "mediaBase": BACKEND_URL}), encoding="utf-8")
    cmd = ["node", "scripts/render.mjs", str(props.resolve()), str(out)]
    tail = []
    for attempt in range(2):  # gecici zaman asimlarinda (makine mesgul) bir kez daha dene
        proc = subprocess.Popen(cmd, cwd=WEB, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", shell=False)
        tail = []
        for line in proc.stdout:
            line = line.strip()
            tail = (tail + [line])[-20:]
            m = re.match(r"PROGRESS (\d+(?:\.\d+)?)", line)
            if m:
                progress(job, float(m.group(1)), f"render %{float(m.group(1)) * 100:.0f}")
        if proc.wait() == 0 and out.exists():
            break
        progress(job, 0.0, "render hatası, yeniden deneniyor")
    else:
        raise RuntimeError("render basarisiz: " + " | ".join(tail[-6:]))
    return {"file": name, "url": f"/api/exports/{pid}/{name}"}


# ek arac modulleri (handler kayitlari import ile olur)
from studio.backend import ai_tools, recipes  # noqa: E402,F401
