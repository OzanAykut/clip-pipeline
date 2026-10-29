"""Analiz + yayin: kanal istatistikleri (youtube_api), retention egrisi, Jev/atlas arastirma raporlari, YouTube'a gonderme.

YouTube API ile yukleme, denetlenmemis projede videoyu OZEL kilitler; bu yuzden varsayilan yol: dosyayi Gezgin'de
secili ac + YouTube Studio yukleme sayfasini ac (kullanici surukler). API ile ozel yukleme de secenek olarak var.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from studio.backend.store import PROJECTS

router = APIRouter(prefix="/api/analysis")
RESEARCH = Path("work/research")
_cache: dict[str, tuple[float, object]] = {}


def _cached(key: str, ttl: float, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    val = fn()
    _cache[key] = (time.time(), val)
    return val


def _channels() -> list[str]:
    return sorted(p.stem.replace("yt_token_", "") for p in Path("secrets").glob("yt_token_*.json"))


@router.get("/channels")
def channels():
    return _channels()


@router.get("/channel/{ch}")
def channel(ch: str, days: int = 28):
    from youtube_api import clients, my_channel, recent_uploads, video_analytics

    def load():
        yt, ya = clients(ch)
        c = my_channel(yt)
        try:
            an = video_analytics(ya, days)
        except Exception:
            an = {}
        vids = []
        for v in recent_uploads(yt, c, 50):
            st, sn = v["statistics"], v["snippet"]
            r = an.get(v["id"], {})
            vids.append({"id": v["id"], "title": sn["title"], "published": v["status"].get("publishAt") or sn["publishedAt"],
                         "privacy": v["status"]["privacyStatus"], "views": int(st.get("viewCount", 0)),
                         "likes": int(st.get("likeCount", 0)), "comments": int(st.get("commentCount", 0)),
                         "avd": r.get("averageViewDuration"), "avp": r.get("averageViewPercentage"),
                         "subs": r.get("subscribersGained"), "thumb": sn.get("thumbnails", {}).get("medium", {}).get("url")})
        s = c["statistics"]
        return {"channel": ch, "title": c["snippet"]["title"], "subs": int(s.get("subscriberCount", 0)),
                "views": int(s.get("viewCount", 0)), "videos": int(s.get("videoCount", 0)), "uploads": vids}
    try:
        return _cached(f"ch:{ch}:{days}", 300, load)
    except SystemExit as e:
        raise HTTPException(401, f"'{ch}' icin YouTube girisi gecersiz/suresi dolmus: python youtube_api.py auth {ch}") from e


@router.get("/retention/{ch}/{video_id}")
def retention(ch: str, video_id: str):
    from youtube_api import clients, retention_curve

    def load():
        yt, ya = clients(ch)
        v = yt.videos().list(part="contentDetails", id=video_id).execute()["items"][0]
        m = re.match(r"PT(?:(\d+)M)?(?:(\d+)S)?", v["contentDetails"]["duration"])
        dur = int(m.group(1) or 0) * 60 + int(m.group(2) or 0)
        return {"duration": dur, "curve": retention_curve(ya, video_id)}
    return _cached(f"ret:{video_id}", 1800, load)


@router.get("/research")
def research():
    """Nis raporlari (niche_research summary.json) + kanal-ici atlas raporu (hook_atlas)."""
    out = {"niches": {}, "atlas": None, "atlas_status": None}
    for f in sorted(RESEARCH.glob("*/summary.json")):
        try:
            out["niches"][f.parent.name] = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    a = RESEARCH / "atlas_report.json"
    if a.exists():
        out["atlas"] = json.loads(a.read_text(encoding="utf-8"))
    db = RESEARCH / "atlas.db"
    if db.exists():
        import sqlite3
        c = sqlite3.connect(db)
        out["atlas_status"] = {
            "channels": c.execute("SELECT COUNT(*), SUM(crawled IS NOT NULL) FROM channels").fetchone(),
            "videos": c.execute("SELECT COUNT(*), SUM(ratio >= 5), SUM(labels IS NOT NULL) FROM videos").fetchone(),
        }
    return out


@router.get("/hooks")
def hooks(niche: str = "", hook: str = "", emotion: str = "", q: str = "", min_ratio: float = 5.0,
          limit: int = 60, offset: int = 0):
    """Hook kutuphanesi: kanalina gore patlamis Short'larin gercek basliklari (Jev etiketli), en cok patlayandan.
    Her biri icin ayni kanalin normal (0.5-2x) videolarindan ornek basliklar da doner."""
    import sqlite3
    db = RESEARCH / "atlas.db"
    if not db.exists():
        return {"items": [], "facets": {}}
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
    from hook_atlas import MIN_LIKE_RATE, bad_channels
    bad = sorted(bad_channels())
    # Jev hatali satirlar da gosterilir; reklamlar (begeni/izlenme ~0) ve nis disi kanallar elenir
    where = ["v.labels IS NOT NULL", "v.ratio >= ?", "v.views > 0", "1.0 * v.likes / v.views >= ?",
             f"v.channel_id NOT IN ({','.join('?' * len(bad))})" if bad else "1=1"]
    args: list = [min_ratio, MIN_LIKE_RATE, *bad]
    if niche:
        where.append("ch.niche = ?")
        args.append(niche)
    if hook:
        where.append("v.labels LIKE ?")
        args.append(f'%"hook": "{hook}"%')
    if emotion:
        where.append("v.labels LIKE ?")
        args.append(f'%"emotion": "{emotion}"%')
    if q:
        where.append("v.title LIKE ?")
        args.append(f"%{q}%")
    w = " AND ".join(where)
    rows = c.execute(f"SELECT v.id, v.title, v.ratio, v.views, v.labels, v.channel_id, ch.title, ch.niche, ch.median "
                     f"FROM videos v JOIN channels ch ON ch.id=v.channel_id WHERE {w} "
                     f"ORDER BY v.ratio DESC LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
    total = c.execute(f"SELECT COUNT(*) FROM videos v JOIN channels ch ON ch.id=v.channel_id WHERE {w}", args).fetchone()[0]
    items = []
    for vid, title, ratio, views, lab, cid, cht, n, med in rows:
        normals = [t for (t,) in c.execute("SELECT title FROM videos WHERE channel_id=? AND ratio BETWEEN 0.7 AND 1.5 "
                                           "ORDER BY views DESC LIMIT 3", (cid,))]
        items.append({"id": vid, "title": title, "ratio": round(ratio, 1), "views": views, "channel": cht, "niche": n,
                      "channel_median": int(med or 0), "labels": json.loads(lab), "normals": normals})
    # filtre secenekleri icin sayimlar (patlamislar icinde)
    facets: dict[str, dict[str, int]] = {"hook": {}, "emotion": {}}
    for (lab,) in c.execute("SELECT labels FROM videos WHERE labels IS NOT NULL AND ratio >= ?", (min_ratio,)):
        L = json.loads(lab)
        for k in facets:
            if L.get(k):
                facets[k][L[k]] = facets[k].get(L[k], 0) + 1
    return {"items": items, "total": total, "facets": facets}


@router.get("/spoken-hooks")
def spoken_hooks(niche: str = "whatif"):
    """Indirilip yaziya dokulmus nis orneklerinde ilk 3 saniyede SOYLENEN hook (baslik degil), top/bottom grubu."""
    f = RESEARCH / niche / "processed.json"
    if not f.exists():
        return []
    data = json.loads(f.read_text(encoding="utf-8"))
    out = [{"id": v["id"], "title": v["title"], "hook": v.get("hook_3s", ""), "ratio": v.get("outlier"),
            "views": v["views"], "group": v.get("group"), "type": (v.get("jev") or {}).get("hook_type"),
            "wps": v.get("wps"), "cps": v.get("cps")} for v in data.values()]
    return sorted(out, key=lambda x: -(x["ratio"] or 0))


class Experiment(BaseModel):
    channel: str
    video: str
    style: str
    variable: str = ""
    notes: str = ""


@router.get("/experiments")
def experiments(refresh: bool = False, snap: str = "latest"):
    """Deney listesi + stil karsilastirmasi. refresh=1 YouTube'dan guncel metrikleri ceker (kanal basina birkac istek)."""
    from studio.backend import experiments as ex
    d = ex.refresh() if refresh else ex._load()
    return {"videos": sorted(d["videos"].values(), key=lambda e: e.get("published") or "", reverse=True),
            "styles": ex.by_style(d, snap), "channels": _channels()}


@router.post("/experiments")
def experiment_add(b: Experiment):
    from studio.backend import experiments as ex
    e = ex.add(b.channel, b.video, b.style, b.variable, b.notes)
    try:
        ex.refresh(only=e["video_id"])
    except Exception:
        pass
    return e


@router.delete("/experiments/{vid}")
def experiment_delete(vid: str):
    from studio.backend import experiments as ex
    ex.remove(vid)
    return {"ok": True}


class Publish(BaseModel):
    pid: str
    file: str
    channel: str = "whatif"
    mode: str = "studio"  # studio | api_private
    title: str = ""
    description: str = ""
    tags: str = ""
    ai: bool = True


@router.post("/publish")
def publish(b: Publish):
    f = (PROJECTS / b.pid / "exports" / b.file).resolve()
    if not f.exists():
        raise HTTPException(404, "disa aktarilmis dosya yok")
    if b.mode == "api_private":
        from youtube_api import upload
        vid = upload(b.channel, str(f), b.title or f.stem, b.description,
                     [t.strip() for t in b.tags.split(",") if t.strip()], None, b.ai)
        return {"mode": "api_private", "video_id": vid, "url": f"https://youtube.com/shorts/{vid}",
                "note": "Denetlenmemis API projesi: video OZEL kalir; Studio'dan herkese acik yapilamayabilir."}
    # varsayilan: dosyayi Gezgin'de sec + Studio yukleme sayfasini ac (kullanici surukler)
    subprocess.Popen(["explorer.exe", f"/select,{f}"])
    return {"mode": "studio", "open": "https://www.youtube.com/upload", "file": str(f)}
