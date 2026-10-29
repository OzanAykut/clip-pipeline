"""Klip Studio MCP sunucusu: Claude'un (bu Claude Code oturumu ya da uygulama ici sohbet) editoru yonetmesi icin.

Tum degisiklikler Klip Studio backend'i (http://127.0.0.1:8765) uzerinden yapilir; acik arayuzler degisikligi
WebSocket ile anlik gorur. Backend calismiyorsa araclar bunu soyler (KlipStudio.bat ile baslat).
Zamanlar saniye. Kanallar: video, overlay (metin/gorsel/B-roll), caption, voice, music, sfx.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP

B = "http://127.0.0.1:8765"
ROOT = Path(__file__).resolve().parents[2]  # klip-pipeline
CLIENT = "mcp-" + uuid.uuid4().hex[:6]
mcp = FastMCP("klip-studio", instructions=(
    "Klip Studio: kullanicinin yerel video editoru. Projeleri timeline (kanallar/ogeler) olarak duzenle, AI araclarini "
    "calistir, disa aktar. Once get_project ile durumu oku; ogeleri id ile duzenle. Sureler saniye. "
    "Ses seviyesi 'volume' dogrusal kazanc (1 = 0 dB, 0.5 = -6 dB)."))


def _req(method: str, path: str, body=None, timeout=60):
    url = B + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, method=method, data=data, headers={"Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(r, timeout=timeout).read())
    except urllib.error.URLError as e:
        raise RuntimeError(f"Klip Studio backend'ine ulasilamadi ({e}). KlipStudio.bat ile baslat.") from e


def _load(pid: str) -> dict:
    return _req("GET", f"/api/projects/{pid}")


def _save(p: dict) -> int:
    return _req("PUT", f"/api/projects/{p['id']}?client={CLIENT}", p)["version"]


def _dur(it: dict) -> float:
    return (it["out"] - it["in"]) / (it.get("speed") or 1)


def _summary(p: dict) -> dict:
    tracks = []
    for t in p["tracks"]:
        items = []
        for it in t["items"]:
            d = {"id": it["id"], "type": it["type"], "start": round(it["start"], 2), "dur": round(_dur(it), 2),
                 "in": round(it["in"], 2), "out": round(it["out"], 2)}
            if it.get("src"):
                d["src"] = it["src"].split("/")[-1]
            if it.get("speed", 1) != 1:
                d["speed"] = it["speed"]
            if it.get("volume", 1) != 1:
                d["volume"] = round(it["volume"], 3)
            if it.get("transition"):
                d["transition"] = it["transition"]
            pr = it.get("props", {})
            if pr.get("text"):
                d["text"] = pr["text"]
            if pr.get("words"):
                d["caption"] = " ".join(w["w"] for w in pr["words"])[:120]
            for k in ("style", "duck", "x", "y", "scale", "card", "radius"):
                if k in pr:
                    d[k] = pr[k]
            items.append(d)
        tracks.append({"kind": t["kind"], "muted": t.get("muted"), "hidden": t.get("hidden"), "items": items})
    end = max([i["start"] + i["dur"] for t in tracks for i in t["items"]] or [0])
    return {"id": p["id"], "name": p["name"], "duration": round(end, 2), "captionStyle": p.get("captionStyle"),
            "media": [{"name": m["name"], "kind": m["kind"], "duration": round(m["duration"], 2)} for m in p["media"]],
            "moments": p.get("moments", [])[:20], "tracks": tracks}


def _track(p: dict, kind: str) -> dict:
    t = next((t for t in p["tracks"] if t["kind"] == kind), None)
    if not t:
        raise ValueError(f"kanal yok: {kind} (video, overlay, caption, voice, music, sfx)")
    return t


def _find(p: dict, item_id: str):
    for t in p["tracks"]:
        for it in t["items"]:
            if it["id"] == item_id:
                return t, it
    raise ValueError(f"oge yok: {item_id}")


@mcp.tool()
def list_projects() -> list:
    """Klip Studio projelerini listeler (en son duzenlenen once)."""
    return _req("GET", "/api/projects")


@mcp.tool()
def create_project(name: str) -> dict:
    """Yeni bos proje olusturur (1080x1920, 30 fps)."""
    p = _req("POST", "/api/projects", {"name": name})
    return {"id": p["id"], "name": p["name"]}


@mcp.tool()
def get_project(project_id: str) -> dict:
    """Projenin ozeti: medya, kanallar ve ogeler (id, baslangic, sure, kaynak, metin/altyazi, stil...)."""
    return _summary(_load(project_id))


@mcp.tool()
def add_media(project_id: str, path: str) -> dict:
    """Diskteki bir dosyayi (video/ses/gorsel) projeye ekler. path: mutlak ya da klip-pipeline'a gore goreli."""
    f = Path(path)
    if not f.is_absolute():
        f = ROOT / f
    return _req("POST", f"/api/projects/{project_id}/media/link", {"path": str(f)})


@mcp.tool()
def add_item(project_id: str, track: str, start: float, media: str | None = None, text: str | None = None,
             source_in: float = 0.0, source_out: float | None = None, duration: float = 3.0,
             volume: float = 1.0, props: dict | None = None) -> dict:
    """Timeline'a oge ekler.
    - medya: media=<proje medya adi>, source_in/source_out kaynaktaki aralik (varsayilan tum dosya).
    - metin: track='overlay', text='...', duration; props ile size, color, x, y (0-1), card=True (beyaz manset karti).
    - muzik: track='music', props={'duck': True} konusmada otomatik kisilir."""
    p = _load(project_id)
    tr = _track(p, track)
    it = {"id": uuid.uuid4().hex[:8], "start": float(start), "speed": 1, "volume": float(volume), "fadeIn": 0,
          "fadeOut": 0, "transition": None, "props": {}}
    if text is not None:
        it.update({"type": "text", "src": None, "in": 0, "out": float(duration),
                   "props": {"text": text, "size": 80, "color": "#ffffff", "x": 0.5, "y": 0.2, "scale": 1}})
    else:
        m = next((m for m in p["media"] if m["name"] == media), None)
        if not m:
            raise ValueError(f"medya yok: {media}. Mevcut: {[x['name'] for x in p['media']]}")
        typ = {"video": "video", "audio": "audio", "image": "image"}[m["kind"]]
        out = source_out if source_out is not None else (m["duration"] or duration)
        if typ == "image":
            out = source_in + duration
        it.update({"type": typ, "src": m["url"], "in": float(source_in), "out": float(out),
                   "props": {"fit": "cover"} if typ != "audio" else {}})
    it["props"].update(props or {})
    tr["items"].append(it)
    tr["items"].sort(key=lambda i: i["start"])
    _save(p)
    return {"id": it["id"], "track": track}


@mcp.tool()
def update_item(project_id: str, item_id: str, changes: dict) -> dict:
    """Ogeyi gunceller. Ust alanlar: start, in, out, speed, volume, fadeIn, fadeOut, transition ({type, dur} ya da
    null; type: fade|slide-left|slide-right|slide-up|zoom|wipe|circle). Diger anahtarlar props'a yazilir
    (text, size, color, x, y, scale, fit, style, duck, duckLevel...). Baska kanala tasimak icin track=<kind>."""
    p = _load(project_id)
    t, it = _find(p, item_id)
    for k, v in changes.items():
        if k in ("start", "in", "out", "speed", "volume", "fadeIn", "fadeOut", "transition"):
            it[k] = v
        elif k == "track":
            t["items"].remove(it)
            _track(p, v)["items"].append(it)
        else:
            it["props"][k] = v
    _save(p)
    return {"ok": True}


@mcp.tool()
def split_item(project_id: str, item_id: str, at: float) -> dict:
    """Ogeyi timeline zamani 'at' noktasindan ikiye boler; yeni parcanin id'sini dondurur."""
    p = _load(project_id)
    t, a = _find(p, item_id)
    if not a["start"] < at < a["start"] + _dur(a):
        raise ValueError("bolme noktasi ogenin icinde degil")
    cut = a["in"] + (at - a["start"]) * (a.get("speed") or 1)
    b = json.loads(json.dumps(a))
    b.update({"id": uuid.uuid4().hex[:8], "start": at, "in": cut, "fadeIn": 0, "transition": None})
    a["out"], a["fadeOut"] = cut, 0
    t["items"].insert(t["items"].index(a) + 1, b)
    _save(p)
    return {"left": a["id"], "right": b["id"]}


@mcp.tool()
def delete_item(project_id: str, item_id: str) -> dict:
    """Ogeyi siler (arayuzde Ctrl+Z ile geri alinabilir)."""
    p = _load(project_id)
    t, it = _find(p, item_id)
    t["items"].remove(it)
    _save(p)
    return {"ok": True}


@mcp.tool()
def set_caption_style(project_id: str, style: str) -> dict:
    """Tum altyazilara stil uygular. Bizimkiler: pop, karaoke, pill, bold-white, podcast, glow.
    remotion-captioneer preset'leri 'cap:<ad>': cap:tiktok, cap:instagram-reels, cap:youtube-shorts, cap:podcast-bold,
    cap:cinematic-gold, cap:gaming-neon, cap:education-highlighter, cap:fun-rainbow ..."""
    p = _load(project_id)
    p["captionStyle"] = style
    for t in p["tracks"]:
        if t["kind"] == "caption":
            for it in t["items"]:
                it["props"]["style"] = style
    _save(p)
    return {"ok": True}


def _wait(pid: str, job: dict, timeout: float) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        js = next((j for j in _req("GET", f"/api/jobs?pid={pid}") if j["id"] == job["id"]), job)
        if js["status"] in ("done", "error"):
            return {k: js.get(k) for k in ("status", "message", "result")}
        time.sleep(2)
    return {"status": "running", "job_id": job["id"], "message": "hala calisiyor; get_jobs ile kontrol et"}


@mcp.tool()
def run_tool(project_id: str, tool: str, args: dict | None = None, wait_seconds: float = 600) -> dict:
    """AI aracini calistirir ve bitmesini bekler. Araclar ve argumanlari:
    captions {language: auto|en|tr} · tts {text, voice: Puck|Fenrir|..., style, speed, at} ·
    reframe {item_id, split_people} · silence_cut {item_id, min_gap} · broll {query, mode: pip|full, dur, at} ·
    moments {media, clips, min, max} · podcast_recipe {media, clips} ·
    story_recipe {scenes: [{media, text}], voice, music, transition}."""
    job = _req("POST", f"/api/projects/{project_id}/tools", {"tool": tool, "args": args or {}})
    return _wait(project_id, job, wait_seconds)


@mcp.tool()
def export_project(project_id: str, wait_seconds: float = 900) -> dict:
    """Projeyi 1080x1920 MP4 olarak disa aktarir; dosyanin diskteki yolunu dondurur."""
    job = _req("POST", f"/api/projects/{project_id}/export")
    r = _wait(project_id, job, wait_seconds)
    if r.get("status") == "done":
        r["path"] = str(ROOT / "studio" / "projects" / project_id / "exports" / r["result"]["file"])
    return r


@mcp.tool()
def get_jobs(project_id: str) -> list:
    """Projenin son isleri (durum, ilerleme, mesaj)."""
    return [{k: j.get(k) for k in ("id", "kind", "status", "progress", "message", "result")}
            for j in _req("GET", f"/api/jobs?pid={project_id}")]


if __name__ == "__main__":
    mcp.run()
