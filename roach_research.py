"""Hamam bocegi (cockroach) Shorts arastirmasi: Turkiye vs global, ozellikle AI uretimi videolar.

  python roach_research.py collect   -> work/research/roach/corpus.json
  python roach_research.py report    -> konsola ozet
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

from niche_research import _channel_medians, _chunks, _iso_dur, _yt

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
OUT = Path("work/research/roach/corpus.json")

# (sorgu, dil grubu, regionCode, relevanceLanguage)
QUERIES = [
    ("hamam böceği", "TR", "TR", "tr"), ("hamam böceği yapay zeka", "TR", "TR", "tr"),
    ("hamam böceği animasyon", "TR", "TR", "tr"), ("hamamböceği komik", "TR", "TR", "tr"),
    ("hamam böceği hikaye", "TR", "TR", "tr"),
    ("cockroach ai", "EN", "US", "en"), ("cockroach ai video", "EN", "US", "en"),
    ("cockroach animation", "EN", "US", "en"), ("cockroach story", "EN", "US", "en"),
    ("cockroach funny", "EN", "US", "en"), ("cockroach family ai", "EN", "US", "en"),
    ("cucaracha ia", "ES", "MX", "es"), ("cucaracha animación", "ES", "MX", "es"),
    ("barata ia", "PT", "BR", "pt"), ("barata animação", "PT", "BR", "pt"),
    ("kecoa ai", "ID", "ID", "id"), ("kecoak animasi", "ID", "ID", "id"),
    ("таракан ии", "RU", "RU", "ru"), ("таракан анимация", "RU", "RU", "ru"),
    ("cockroach cartoon hindi", "IN", "IN", "hi"), ("कॉकरोच", "IN", "IN", "hi"),
    ("صرصور", "AR", "SA", "ar"), ("con gián", "VI", "VN", "vi"), ("Kakerlake", "DE", "DE", "de"),
]
ROACH = re.compile(r"hamam|böce|bocek|cockroach|roach|cucarach|barata|kecoa|тарака|कॉकरोच|cockroch|صرصور|gián|kakerlak", re.I)
AI = re.compile(r"\bai\b|\bia\b|yapay zeka|\bии\b|veo|sora|kling|animation|animasyon|animación|animação|animasi|анимац|cartoon|3d", re.I)


def collect(months: int = 12) -> None:
    yt = _yt()
    after = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30 * months)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids: dict[str, tuple[str, str]] = {}
    for q, grp, region, lang in QUERIES:
        r = yt.search().list(part="snippet", q=q, type="video", videoDuration="short", order="viewCount",
                             publishedAfter=after, maxResults=50, regionCode=region, relevanceLanguage=lang).execute()
        for it in r.get("items", []):
            ids.setdefault(it["id"]["videoId"], (q, grp))
        print(f"  [{grp}] '{q}': {len(r.get('items', []))} (toplam {len(ids)})")
    vids = []
    for part in _chunks(list(ids), 50):
        r = yt.videos().list(part="snippet,statistics,contentDetails", id=",".join(part)).execute()
        for v in r["items"]:
            dur = _iso_dur(v["contentDetails"]["duration"])
            if dur == 0 or dur > 180:
                continue
            st, sn = v["statistics"], v["snippet"]
            vids.append({"id": v["id"], "title": sn["title"], "desc": sn.get("description", "")[:300],
                         "tags": sn.get("tags", [])[:15], "channel_id": sn["channelId"], "channel": sn["channelTitle"],
                         "published": sn["publishedAt"], "duration": dur, "lang": sn.get("defaultAudioLanguage"),
                         "views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                         "comments": int(st.get("commentCount", 0)), "query": ids[v["id"]][0], "group": ids[v["id"]][1]})
    chans = {v["channel_id"] for v in vids}
    country = {}
    for part in _chunks(list(chans), 50):
        for c in yt.channels().list(part="snippet,statistics", id=",".join(part)).execute().get("items", []):
            country[c["id"]] = (c["snippet"].get("country"), int(c["statistics"].get("subscriberCount", 0)),
                                c["snippet"].get("publishedAt"))
    medians = _channel_medians(yt, chans)
    for v in vids:
        med = medians.get(v["channel_id"]) or 0
        v["country"], v["subs"], v["channel_created"] = country.get(v["channel_id"], (None, 0, None))
        v["channel_median"] = med
        v["outlier"] = round(v["views"] / med, 2) if med else None
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(vids, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"OK {len(vids)} video, {len(chans)} kanal -> {OUT}")


def report() -> None:
    vids = json.loads(OUT.read_text(encoding="utf-8"))
    vids = [v for v in vids if ROACH.search(v["title"] + " " + v["desc"] + " " + " ".join(v["tags"]))]
    for v in vids:
        blob = v["title"] + " " + v["desc"] + " " + " ".join(v["tags"])
        v["ai"] = bool(AI.search(blob))
    print(f"{len(vids)} konu ile ilgili video\n")
    by = collections.defaultdict(list)
    for v in vids:
        by[v["group"]].append(v)
    print(f"{'grup':4} {'n':>4} {'toplam izl':>14} {'medyan':>10} {'>=1M':>5} {'AI%':>5}")
    for g, vs in sorted(by.items(), key=lambda kv: -sum(x["views"] for x in kv[1])):
        views = sorted(x["views"] for x in vs)
        print(f"{g:4} {len(vs):4} {sum(views):14,} {views[len(views)//2]:10,} {sum(x >= 1e6 for x in views):5} "
              f"{100*sum(x['ai'] for x in vs)/len(vs):4.0f}%")
    # aylik trend (yayin ayi -> video sayisi / izlenme)
    print("\nAy bazinda (>=100k izlenmeli videolar):")
    months = collections.defaultdict(lambda: collections.Counter())
    for v in vids:
        if v["views"] >= 1e5:
            months[v["published"][:7]][v["group"] if v["group"] == "TR" else "GLOBAL"] += 1
    for m in sorted(months):
        print(f"  {m}: TR {months[m]['TR']:3}  global {months[m]['GLOBAL']:3}")
    print("\nEn cok izlenen 40:")
    for v in sorted(vids, key=lambda x: -x["views"])[:40]:
        print(f"  {v['views']:>12,}  x{v['outlier'] or 0:<7} [{v['group']}/{v['country'] or '-'}] {v['published'][:10]} "
              f"{v['duration']:>3.0f}s  {v['title'][:80]}  — {v['channel']} ({v['subs']:,})")
    print("\nKanal basina toplam (top 25):")
    ch = collections.defaultdict(lambda: [0, 0, None, None, 0])
    for v in vids:
        c = ch[v["channel"]]
        c[0] += v["views"]; c[1] += 1; c[2] = v["country"]; c[3] = v["channel_created"]; c[4] = v["subs"]
    for name, (tot, n, cc, created, subs) in sorted(ch.items(), key=lambda kv: -kv[1][0])[:25]:
        print(f"  {tot:>13,}  {n:2} vid  {cc or '-':3} acilis {str(created)[:7]}  abone {subs:>10,}  {name}")


if __name__ == "__main__":
    {"collect": collect, "report": report}[sys.argv[1]]()
