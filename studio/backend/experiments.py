"""Deney takibi: her yuklenen video bir deney (stil + degistirilen tek degisken). YouTube Analytics'ten
kaydirmadan izleme orani (engagedViews/views), ortalama izlenme %, 3. saniyede kalan, T1 ulke payi, abone cekilir;
24 sa / 48 sa / 7 gun esiklerinde anlik goruntu saklanir ki videolar ayni yasta karsilastirilabilsin.

  python -m studio.backend.experiments add <kanal> <video_id|url> --style "..." --variable "..." [--notes "..."]
  python -m studio.backend.experiments refresh
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import statistics
import sys
import threading
from pathlib import Path

STORE = Path("work/experiments.json")
T1 = {"US", "GB", "CA", "AU"}
MILESTONES = [("h24", 24), ("h48", 48), ("d7", 168)]
_lock = threading.Lock()


def _load() -> dict:
    if STORE.exists():
        return json.loads(STORE.read_text(encoding="utf-8"))
    return {"videos": {}}


def _save(d: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STORE)


def video_id(s: str) -> str:
    m = re.search(r"(?:shorts/|v=|youtu\.be/)([A-Za-z0-9_-]{11})", s)
    return m.group(1) if m else s.strip()


def _iso_dur(s: str) -> float:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    h, mi, se = (int(x or 0) for x in m.groups()) if m else (0, 0, 0)
    return h * 3600 + mi * 60 + se


def metrics(channel: str, vid: str) -> dict:
    """Anlik metrikler. Analytics 1-2 gun gecikmeli oldugundan bazi alanlar None olabilir."""
    from youtube_api import clients
    yt, ya = clients(channel)
    items = yt.videos().list(part="snippet,statistics,contentDetails", id=vid).execute()["items"]
    if not items:
        return {"error": "video bulunamadi (silinmis ya da baska kanalin)"}
    v = items[0]
    st, sn = v["statistics"], v["snippet"]
    dur = _iso_dur(v["contentDetails"]["duration"])
    out = {"title": sn["title"], "published": sn["publishedAt"], "duration": dur,
           "views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
           "comments": int(st.get("commentCount", 0)), "fetched": dt.datetime.now(dt.timezone.utc).isoformat()}
    start, end = sn["publishedAt"][:10], dt.date.today().isoformat()
    q = dict(ids="channel==MINE", startDate=start, endDate=end, filters=f"video=={vid}")
    try:
        r = ya.reports().query(**q, metrics="views,engagedViews,averageViewPercentage,averageViewDuration,"
                                            "subscribersGained,shares").execute()
        if r.get("rows"):
            hdr = [h["name"] for h in r["columnHeaders"]]
            a = dict(zip(hdr, r["rows"][0]))
            out.update({"a_views": a.get("views"), "engaged": a.get("engagedViews"),
                        "apv": a.get("averageViewPercentage"), "avd": a.get("averageViewDuration"),
                        "subs": a.get("subscribersGained"), "shares": a.get("shares")})
            if a.get("views"):
                out["stay"] = round(100 * (a.get("engagedViews") or 0) / a["views"], 1)
        r = ya.reports().query(**q, metrics="views", dimensions="country", sort="-views", maxResults=50).execute()
        rows = r.get("rows") or []
        tot = sum(x[1] for x in rows)
        if tot:
            out["t1"] = round(100 * sum(x[1] for x in rows if x[0] in T1) / tot, 1)
            out["top_country"] = rows[0][0]
        r = ya.reports().query(**q, dimensions="elapsedVideoTimeRatio", metrics="audienceWatchRatio").execute()
        curve = r.get("rows") or []
        if curve and dur:
            target = min(1.0, 3.0 / dur)
            out["hold3s"] = round(100 * min(curve, key=lambda p: abs(p[0] - target))[1], 1)
    except Exception as e:  # analytics henuz hazir degil / yetki yok
        out["analytics_error"] = str(e)[:160]
    return out


def add(channel: str, vid_or_url: str, style: str, variable: str = "", notes: str = "") -> dict:
    vid = video_id(vid_or_url)
    with _lock:
        d = _load()
        e = d["videos"].get(vid, {"video_id": vid, "snapshots": {}})
        e.update({"channel": channel, "style": style, "variable": variable, "notes": notes})
        d["videos"][vid] = e
        _save(d)
    return e


def remove(vid: str) -> None:
    with _lock:
        d = _load()
        d["videos"].pop(vid, None)
        _save(d)


def refresh(only: str | None = None) -> dict:
    d = _load()
    now = dt.datetime.now(dt.timezone.utc)
    for vid, e in d["videos"].items():
        if only and vid != only:
            continue
        try:
            m = metrics(e["channel"], vid)
        except SystemExit as ex:  # token yok / suresi dolmus
            e["error"] = str(ex)
            continue
        except Exception as ex:
            e["error"] = str(ex)[:200]
            continue
        e.pop("error", None)
        e["latest"] = m
        e["title"] = m.get("title", e.get("title"))
        e["published"] = m.get("published", e.get("published"))
        if e.get("published"):
            age_h = (now - dt.datetime.fromisoformat(e["published"].replace("Z", "+00:00"))).total_seconds() / 3600
            e["age_h"] = round(age_h, 1)
            # esik gecildiyse ve henuz kaydedilmediyse (ya da analytics eksik kaydedildiyse) anlik goruntu al
            for key, hours in MILESTONES:
                snap = e["snapshots"].get(key)
                if age_h >= hours and (not snap or (snap.get("stay") is None and m.get("stay") is not None
                                                    and age_h < hours + 48)):
                    e["snapshots"][key] = {**m, "age_h": round(age_h, 1)}
    with _lock:
        cur = _load()
        for vid, e in d["videos"].items():
            if vid in cur["videos"]:
                # yenilenen kayit esas; yalnizca kullanicinin girdigi alanlar (stil/degisken/not) mevcut kayittan gelir
                keep = {k: cur["videos"][vid][k] for k in ("style", "variable", "notes", "channel") if k in cur["videos"][vid]}
                cur["videos"][vid] = {**e, **keep}
        _save(cur)
    return cur


def by_style(d: dict, snap: str = "latest") -> list[dict]:
    """Stil bazinda ortalamalar (yalnizca o anlik goruntusu olan videolar)."""
    groups: dict[str, list[dict]] = {}
    for e in d["videos"].values():
        m = e.get("latest") if snap == "latest" else e.get("snapshots", {}).get(snap)
        if m:
            groups.setdefault(e.get("style") or "?", []).append(m)
    out = []
    for style, ms in groups.items():
        def avg(k):
            xs = [m[k] for m in ms if m.get(k) is not None]
            return round(statistics.mean(xs), 1) if xs else None
        out.append({"style": style, "n": len(ms), "views": avg("views"), "stay": avg("stay"), "apv": avg("apv"),
                    "hold3s": avg("hold3s"), "t1": avg("t1"), "subs": avg("subs")})
    return sorted(out, key=lambda r: -(r["stay"] or -1))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("channel")
    a.add_argument("video")
    a.add_argument("--style", required=True)
    a.add_argument("--variable", default="")
    a.add_argument("--notes", default="")
    sub.add_parser("refresh")
    args = p.parse_args()
    if args.cmd == "add":
        print(add(args.channel, args.video, args.style, args.variable, args.notes))
    else:
        d = refresh()
        for e in d["videos"].values():
            m = e.get("latest", {})
            print(f"{e['channel']:7} {e['video_id']} {str(e.get('style'))[:28]:28} izl={m.get('views')} "
                  f"kal%={m.get('stay')} apv={m.get('apv')} 3sn={m.get('hold3s')} t1={m.get('t1')} {e.get('error', '')[:60]}")


if __name__ == "__main__":
    main()
