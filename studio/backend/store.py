"""Proje deposu: studio/projects/<id>/project.json + media/. Sema (saniye cinsinden):

project = {id, name, version, fps, width, height, media:[{name, kind, duration, width, height, has_audio, url}],
           tracks:[{id, kind: video|overlay|caption|voice|music|sfx, name, muted, hidden, items:[item]}],
           captionStyle, created, updated}
item    = {id, type: video|audio|image|text|caption, src, start, in, out, speed, volume, fadeIn, fadeOut,
           transition: {type, dur} | null, props: {...}}
  sure (timeline) = (out - in) / speed ; volume dogrusal kazanc (1 = 0 dB)
"""
from __future__ import annotations

import json
import subprocess
import time
import uuid
from pathlib import Path

STUDIO = Path("studio")
PROJECTS = STUDIO / "projects"
(STUDIO / "trash").mkdir(parents=True, exist_ok=True)
PROJECTS.mkdir(parents=True, exist_ok=True)

DEFAULT_TRACKS = [
    {"kind": "caption", "name": "Altyazı"},
    {"kind": "overlay", "name": "Metin / Görsel"},
    {"kind": "video", "name": "Video"},
    {"kind": "voice", "name": "Ses / Seslendirme"},
    {"kind": "music", "name": "Müzik"},
    {"kind": "sfx", "name": "Efekt"},
]


def _id() -> str:
    return uuid.uuid4().hex[:8]


def new_project(name: str) -> dict:
    pid = f"{time.strftime('%m%d')}-{_id()}"
    p = {"id": pid, "name": name, "version": 0, "fps": 30, "width": 1080, "height": 1920, "media": [],
         "tracks": [{"id": _id(), "muted": False, "hidden": False, "items": [], **t} for t in DEFAULT_TRACKS],
         "captionStyle": "pop", "created": time.time(), "updated": time.time()}
    (PROJECTS / pid / "media").mkdir(parents=True, exist_ok=True)
    return save(pid, p)


def load(pid: str) -> dict:
    return json.loads((PROJECTS / pid / "project.json").read_text(encoding="utf-8"))


def save(pid: str, p: dict) -> dict:
    p["version"] = int(p.get("version", 0)) + 1
    p["updated"] = time.time()
    f = PROJECTS / pid / "project.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(p, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)  # yarim yazilmis dosyayi kimse okumasin
    return p


def list_projects() -> list[dict]:
    out = []
    for f in sorted(PROJECTS.glob("*/project.json"), key=lambda f: -f.stat().st_mtime):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
            out.append({"id": p["id"], "name": p["name"], "updated": p.get("updated"),
                        "media": len(p.get("media", []))})
        except Exception:
            pass
    return out


def register_media(pid: str, path: Path, copy: bool = True) -> dict:
    """Dosyayi projenin media/ klasorune alir (gerekirse kopyalar) ve proje medya listesine ekler."""
    import shutil
    mdir = PROJECTS / pid / "media"
    mdir.mkdir(parents=True, exist_ok=True)
    dst = mdir / path.name
    if path.resolve() != dst.resolve():
        if not dst.exists():
            shutil.copy2(path, dst) if copy else shutil.move(str(path), dst)
    info = probe(dst)
    p = load(pid)
    p["media"] = [m for m in p.get("media", []) if m["name"] != info["name"]] + [info]
    save(pid, p)
    return info


def new_item(type_: str, src: str | None, start: float, in_: float, out: float, **kw) -> dict:
    it = {"id": _id(), "type": type_, "src": src, "start": round(start, 3), "in": round(in_, 3), "out": round(out, 3),
          "speed": 1, "volume": 1, "fadeIn": 0, "fadeOut": 0, "transition": None, "props": {}}
    for k, v in kw.items():
        if k == "props":
            it["props"].update(v)
        else:
            it[k] = v
    return it


def track(p: dict, kind: str) -> dict:
    return next(t for t in p["tracks"] if t["kind"] == kind)


def find_item(p: dict, item_id: str) -> tuple[dict, dict]:
    for t in p["tracks"]:
        for it in t["items"]:
            if it["id"] == item_id:
                return t, it
    raise KeyError(f"oge yok: {item_id}")


def probe(path: Path, url: str | None = None) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
                        "-of", "json", str(path)], capture_output=True, text=True)
    info = json.loads(r.stdout or "{}")
    streams = info.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    ext = path.suffix.lower()
    kind = "image" if ext in (".png", ".jpg", ".jpeg", ".webp") else ("video" if v else "audio")
    return {"name": path.name, "kind": kind, "duration": float(info.get("format", {}).get("duration", 0) or 0),
            "width": v.get("width") if v else None, "height": v.get("height") if v else None,
            "has_audio": any(s.get("codec_type") == "audio" for s in streams),
            "url": url or f"/media/{path.parent.parent.name}/{path.name}"}
