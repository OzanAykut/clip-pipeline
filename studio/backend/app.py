"""Klip Studio backend: proje deposu, medya, canli guncelleme (WebSocket), is kuyrugu, disa aktarma.

Calistirma (klip-pipeline kokunden):  venv/Scripts/python -m uvicorn studio.backend.app:app --port 8765
project.json tek gercek kaynaktir; UI, MCP (Claude) ve AI araclari ayni dosyayi duzenler. Dosya diskten
degisirse (or. Claude dogrudan yazdiysa) izleyici farki gorur ve tum acik arayuzlere yeni surumu iter.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from studio.backend import jobs
from studio.backend.store import PROJECTS, STUDIO, list_projects, load, new_project, probe, register_media, save

app = FastAPI(title="Klip Studio")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

from studio.backend.analysis import router as analysis_router  # noqa: E402

app.include_router(analysis_router)

_sockets: dict[str, set[WebSocket]] = {}
_mtimes: dict[str, float] = {}


async def broadcast(pid: str, msg: dict) -> None:
    dead = []
    for ws in _sockets.get(pid, set()):
        try:
            await ws.send_json(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _sockets[pid].discard(ws)


jobs.set_broadcaster(broadcast)


@app.on_event("startup")
async def _watch():
    """Disaridan (Claude/MCP, elle) yapilan project.json degisikliklerini arayuze iter."""
    async def loop():
        while True:
            for pid in list(_sockets):
                f = PROJECTS / pid / "project.json"
                if f.exists():
                    m = f.stat().st_mtime
                    if pid in _mtimes and m != _mtimes[pid]:
                        await broadcast(pid, {"type": "project", "project": load(pid)})
                    _mtimes[pid] = m
            await asyncio.sleep(0.7)
    asyncio.create_task(loop())
    jobs.start_worker()


# ---------------- projeler ----------------

class NewProject(BaseModel):
    name: str = "Yeni proje"


@app.get("/api/projects")
def api_list():
    return list_projects()


@app.post("/api/projects")
def api_new(body: NewProject):
    return new_project(body.name)


@app.get("/api/projects/{pid}")
def api_get(pid: str):
    try:
        return load(pid)
    except FileNotFoundError:
        raise HTTPException(404, "proje yok")


@app.put("/api/projects/{pid}")
async def api_save(pid: str, project: dict, client: str = ""):
    p = save(pid, project)
    _mtimes[pid] = (PROJECTS / pid / "project.json").stat().st_mtime  # kendi yazdigimizi tekrar yayinlama
    # diger arayuzler/Claude yeni hali hemen gorsun; kaydi yapan istemci kendi mesajini yok sayar
    await broadcast(pid, {"type": "project", "project": p, "origin": client})
    return {"version": p["version"]}


@app.delete("/api/projects/{pid}")
def api_delete(pid: str):
    d = PROJECTS / pid
    if not d.exists():
        raise HTTPException(404)
    shutil.move(str(d), str(STUDIO / "trash" / f"{pid}_{int(time.time())}"))  # kalici silme yok: cop kutusu
    return {"ok": True}


# ---------------- medya ----------------

@app.post("/api/projects/{pid}/media")
async def api_upload(pid: str, file: UploadFile = File(...)):
    mdir = PROJECTS / pid / "media"
    mdir.mkdir(parents=True, exist_ok=True)
    name = Path(file.filename).name
    dst = mdir / name
    i = 1
    while dst.exists():
        dst = mdir / f"{Path(name).stem}_{i}{Path(name).suffix}"
        i += 1
    with dst.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return _register(pid, dst)


class LinkMedia(BaseModel):
    path: str  # diskteki bir dosya (or. output/whatif/x.mp4) -> projeye kopyalanir


@app.post("/api/projects/{pid}/media/link")
def api_link(pid: str, body: LinkMedia):
    src = Path(body.path)
    if not src.exists():
        raise HTTPException(404, f"dosya yok: {src}")
    mdir = PROJECTS / pid / "media"
    mdir.mkdir(parents=True, exist_ok=True)
    dst = mdir / src.name
    if not dst.exists():
        shutil.copy2(src, dst)
    return _register(pid, dst)


def _register(pid: str, path: Path) -> dict:
    return register_media(pid, path)


@app.get("/media/{pid}/{name}")
def media(pid: str, name: str):
    f = PROJECTS / pid / "media" / name
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f)


@app.get("/library/{kind}/{name}")
def library(kind: str, name: str):
    """Ortak kutuphane: assets/music, assets/sfx, assets/fonts."""
    if kind not in ("music", "sfx", "fonts"):
        raise HTTPException(404)
    f = Path("assets") / kind / name
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f)


@app.get("/api/library")
def api_library():
    out = {}
    for kind in ("music", "sfx"):
        d = Path("assets") / kind
        out[kind] = [probe(f, url=f"/library/{kind}/{f.name}") for f in sorted(d.glob("*"))
                     if f.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg")]
    return out


@app.get("/api/projects/{pid}/media/{name}/waveform")
def waveform(pid: str, name: str, points: int = 400):
    """Ses dalga formu (0-1 tepe degerleri) - timeline'da cizilir. Onbellekli."""
    f = PROJECTS / pid / "media" / name
    cache = PROJECTS / pid / "cache" / f"{name}.wave{points}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                         capture_output=True).stdout
    x = np.abs(np.frombuffer(raw, dtype=np.int16).astype(np.float32)) / 32768
    if len(x) == 0:
        peaks = [0.0] * points
    else:
        peaks = [float(c.max()) if len(c) else 0.0 for c in np.array_split(x, points)]
    cache.parent.mkdir(exist_ok=True)
    cache.write_text(json.dumps(peaks))
    return peaks


@app.get("/api/projects/{pid}/media/{name}/audiomap")
def audiomap(pid: str, name: str, pps: int = 50):
    """Ince dalga formu (log olcek 0-1, saniyede pps nokta) + sessiz araliklar: timeline'da bosluklar gorunur,
    kenar surukleme sessizlige yapisir. Onbellekli."""
    from audio_cuts import silence_map
    f = PROJECTS / pid / "media" / name
    cache = PROJECTS / pid / "cache" / f"{name}.amap{pps}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    m = silence_map(f, pps)
    cache.parent.mkdir(exist_ok=True)
    cache.write_text(json.dumps(m))
    return m


@app.get("/api/projects/{pid}/media/{name}/thumb")
def thumb(pid: str, name: str, t: float = 0.5):
    f = PROJECTS / pid / "media" / name
    out = PROJECTS / pid / "cache" / f"{name}.{t:.1f}.jpg"
    if not out.exists():
        out.parent.mkdir(exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(f), "-frames:v", "1",
                        "-vf", "scale=160:-1", str(out)])
    if not out.exists():
        raise HTTPException(404)
    return FileResponse(out)


# ---------------- isler ----------------

@app.post("/api/projects/{pid}/export")
def api_export(pid: str):
    return jobs.submit(pid, "export", {})


class ToolCall(BaseModel):
    tool: str
    args: dict = {}


@app.post("/api/projects/{pid}/tools")
def api_tool(pid: str, body: ToolCall):
    return jobs.submit(pid, body.tool, body.args)


@app.get("/api/jobs")
def api_jobs(pid: str | None = None):
    return jobs.list_jobs(pid)


@app.get("/api/exports/{pid}/{name}")
def export_file(pid: str, name: str):
    f = PROJECTS / pid / "exports" / name
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f, filename=name)


# ---------------- canli baglanti ----------------

@app.websocket("/ws/{pid}")
async def ws(websocket: WebSocket, pid: str):
    await websocket.accept()
    _sockets.setdefault(pid, set()).add(websocket)
    try:
        while True:
            await websocket.receive_text()  # istemci ping
    except WebSocketDisconnect:
        _sockets[pid].discard(websocket)


# ---------------- uygulama ici Claude ----------------

class ClaudeAsk(BaseModel):
    message: str
    session: str | None = None
    context: dict = {}


@app.post("/api/projects/{pid}/claude")
async def api_claude(pid: str, body: ClaudeAsk):
    from studio.backend import claude_bridge
    loop = asyncio.get_running_loop()

    def emit(ev: dict):
        asyncio.run_coroutine_threadsafe(broadcast(pid, {"type": "claude", **ev}), loop)

    claude_bridge.ask(pid, body.message, body.session, body.context, emit)
    return {"ok": True}


@app.post("/api/projects/{pid}/claude/stop")
def api_claude_stop(pid: str):
    from studio.backend import claude_bridge
    return {"stopped": claude_bridge.stop(pid)}


@app.get("/api/claude/status")
def api_claude_status():
    from studio.backend import claude_bridge
    cli = claude_bridge.find_cli()
    if not cli:
        return {"cli": None, "loggedIn": False}
    r = subprocess.run([str(cli), "auth", "status"], capture_output=True, text=True, timeout=30)
    try:
        st = json.loads(r.stdout)
    except Exception:
        st = {}
    return {"cli": str(cli), "loggedIn": bool(st.get("loggedIn")), "auth": st.get("authMethod")}


@app.get("/api/health")
def health():
    return {"ok": True, "id": str(uuid.uuid4())[:4]}
