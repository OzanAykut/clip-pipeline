"""Hook Atlas: buyuk olcekli 'kanalina gore patlamis Shorts' arastirmasi (Katman A - sadece resmi API).

Fikir: bir videonun basarisini KENDI KANALININ normaline gore olc (ayni kisi/kitle/kalite sabit kalir),
sonra patlamis videolari ayni kanalin normal videolariyla karsilastir -> fark hook/konu/baslikta.

  python hook_atlas.py crawl  [--niche whatif,character,podcast] [--per-channel 150] [--budget 5000]
  python hook_atlas.py label  [--limit 20000]      # Jev: baslik hook tipi / duygu / format (+ yerel ozellikler)
  python hook_atlas.py analyze                     # kanal-ici karsilastirma -> work/research/atlas_report.json
Veri: work/research/atlas.db (SQLite). Kaldigi yerden devam eder; kota butcesi asilinca durur.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB = Path("work/research/atlas.db")
MIN_AGE_DAYS = 14        # yeni videolar henuz izlenme toplamadi
MIN_CHANNEL_SHORTS = 15  # medyan anlamli olsun
OUTLIER_X = 5.0          # kanal medyaninin 5 kati = patlamis
MIN_LIKE_RATE = 0.002    # reklamlar (ucretli gosterim) ve bot izlenmeleri: begeni/izlenme ~0


def bad_channels() -> set[str]:
    """Korpus asamasinda Jev'in 'nis disi' dedigi (tum videolari in_niche < 0.5) kanallar: sarki, reklam vb."""
    seen: dict[str, bool] = {}
    for f in Path("work/research").glob("*/corpus.json"):
        for v in json.loads(f.read_text(encoding="utf-8")):
            if "in_niche" in v:
                seen[v["channel_id"]] = seen.get(v["channel_id"], False) or v["in_niche"] >= 0.5
    return {c for c, ok in seen.items() if not ok}
_quota = 0


def db() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS channels(id TEXT PRIMARY KEY, title TEXT, niche TEXT, subs INTEGER,
        uploads TEXT, crawled REAL, n_shorts INTEGER, median REAL);
    CREATE TABLE IF NOT EXISTS videos(id TEXT PRIMARY KEY, channel_id TEXT, title TEXT, published TEXT,
        duration REAL, views INTEGER, likes INTEGER, comments INTEGER, ratio REAL, labels TEXT);
    CREATE INDEX IF NOT EXISTS v_ch ON videos(channel_id);
    """)
    return c


def _yt():
    from youtube_api import clients
    return clients("whatif")[0]


def _iso_dur(s: str) -> float:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    return sum(int(x or 0) * k for x, k in zip(m.groups(), (3600, 60, 1))) if m else 0.0


# ---------------- crawl ----------------

def seed_channels(niches: list[str]) -> dict[str, str]:
    """Daha once toplanan nis korpuslarindaki kanallar (niche_research collect ciktisi)."""
    out = {}
    for n in niches:
        f = Path(f"work/research/{n}/corpus.json")
        if f.exists():
            for v in json.loads(f.read_text(encoding="utf-8")):
                out.setdefault(v["channel_id"], n)
    return out


def crawl(niches: list[str], per_channel: int, budget: int) -> None:
    global _quota
    yt = _yt()
    c = db()
    seeds = seed_channels(niches)
    done = {r[0] for r in c.execute("SELECT id FROM channels WHERE crawled IS NOT NULL")}
    todo = [cid for cid in seeds if cid not in done]
    print(f"{len(seeds)} tohum kanal, {len(todo)} taranacak (butce {budget} birim)")
    for i in range(0, len(todo), 50):
        part = todo[i:i + 50]
        r = yt.channels().list(part="snippet,statistics,contentDetails", id=",".join(part)).execute()
        _quota += 1
        for ch in r.get("items", []):
            c.execute("INSERT OR REPLACE INTO channels(id,title,niche,subs,uploads) VALUES(?,?,?,?,?)",
                      (ch["id"], ch["snippet"]["title"], seeds[ch["id"]],
                       int(ch["statistics"].get("subscriberCount", 0) or 0),
                       ch["contentDetails"]["relatedPlaylists"]["uploads"]))
        c.commit()
    now = datetime.now(timezone.utc)
    rows = c.execute("SELECT id, uploads FROM channels WHERE crawled IS NULL").fetchall()
    for n, (cid, pl) in enumerate(rows, 1):
        if _quota >= budget:
            print(f"kota butcesi doldu ({_quota}); yarin 'crawl' ile devam edilir")
            break
        ids, token = [], None
        try:
            while len(ids) < per_channel:
                r = yt.playlistItems().list(part="contentDetails", playlistId=pl, maxResults=50,
                                            pageToken=token).execute()
                _quota += 1
                ids += [it["contentDetails"]["videoId"] for it in r.get("items", [])]
                token = r.get("nextPageToken")
                if not token:
                    break
        except Exception as e:
            print(f"  {cid}: {str(e)[:120]}")
            c.execute("UPDATE channels SET crawled=? WHERE id=?", (time.time(), cid))
            continue
        shorts = []
        for i in range(0, len(ids), 50):
            r = yt.videos().list(part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50])).execute()
            _quota += 1
            for v in r.get("items", []):
                d = _iso_dur(v["contentDetails"]["duration"])
                if not 0 < d <= 180:
                    continue
                st = v["statistics"]
                shorts.append((v["id"], cid, v["snippet"]["title"], v["snippet"]["publishedAt"], d,
                               int(st.get("viewCount", 0) or 0), int(st.get("likeCount", 0) or 0),
                               int(st.get("commentCount", 0) or 0)))
        c.executemany("INSERT OR REPLACE INTO videos(id,channel_id,title,published,duration,views,likes,comments)"
                      " VALUES(?,?,?,?,?,?,?,?)", shorts)
        # kanal normali: en az 14 gunluk Shorts'larin medyani
        old = [s[5] for s in shorts if (now - datetime.fromisoformat(s[3].replace("Z", "+00:00"))).days >= MIN_AGE_DAYS]
        med = statistics.median(old) if len(old) >= MIN_CHANNEL_SHORTS else None
        c.execute("UPDATE channels SET crawled=?, n_shorts=?, median=? WHERE id=?", (time.time(), len(shorts), med, cid))
        if med:
            c.execute("UPDATE videos SET ratio = views / ? WHERE channel_id=?", (med, cid))
        c.commit()
        if n % 20 == 0:
            tot = c.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
            print(f"  {n}/{len(rows)} kanal, {tot} short, kota ~{_quota}")
    tot = c.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    outl = c.execute("SELECT COUNT(*) FROM videos WHERE ratio >= ?", (OUTLIER_X,)).fetchone()[0]
    print(f"OK {tot} short, {outl} patlamis (>= {OUTLIER_X}x kanal medyani), kota ~{_quota}")


# ---------------- etiketleme ----------------

def local_features(title: str) -> dict:
    t = re.sub(r"#\w+", "", title).strip()
    words = t.split()
    return {
        "has_number": bool(re.search(r"\d", t)),
        "question": "?" in t,
        "you": bool(re.search(r"\b(you|your|you're)\b", t, re.I)),
        "what_if": bool(re.search(r"\bwhat (if|would|happens)\b", t, re.I)),
        "caps_word": any(w.isupper() and len(w) > 2 for w in words),
        "emoji": bool(re.search(r"[\U0001F300-\U0001FAFF☀-➿]", t)),
        "short_title": len(words) <= 5,
        "exclaim": "!" in t,
    }


def _questions():
    from jev_client import choice
    return {
        "hook": choice({
            "shock_number": "a surprising number, size, speed or statistic",
            "question": "asks the viewer a question",
            "danger": "danger, threat, disaster or something terrible",
            "you_pov": "puts the viewer in the scene ('you', 'imagine')",
            "myth_bust": "says a common belief is wrong",
            "curiosity_gap": "teases a secret/outcome without revealing it",
            "bold_claim": "a bold, extreme or controversial statement",
            "story": "starts a personal story or anecdote",
            "celebrity": "leads with a famous person or brand",
            "label_only": "just names the topic plainly, no hook",
        }, "What kind of hook does this short-video title use?"),
        "emotion": choice({"curiosity": "curiosity", "fear": "fear/anxiety", "humor": "humor", "awe": "awe/scale",
                           "outrage": "outrage/drama", "satisfying": "satisfying/oddly satisfying",
                           "relatable": "relatable everyday"}, "Main emotion the title triggers?"),
    }


def label(limit: int, workers: int = 12) -> None:
    import jev_client
    c = db()
    rows = c.execute("SELECT v.id, v.title FROM videos v JOIN channels ch ON ch.id=v.channel_id "
                     "WHERE ch.median IS NOT NULL AND (v.labels IS NULL OR v.labels LIKE '%\"error\"%') LIMIT ?",
                     (limit,)).fetchall()
    q = _questions()
    print(f"{len(rows)} baslik etiketlenecek")

    def one(r):
        vid, title = r
        try:
            a = jev_client.decide({"title": title}, q)
            lab = {k: v.get("choice") for k, v in a.items()} | local_features(title)
        except Exception as e:
            lab = {"error": str(e)[:100]} | local_features(title)
        return vid, json.dumps(lab)

    out = []
    with ThreadPoolExecutor(workers) as ex:
        for i, res in enumerate(ex.map(one, rows), 1):
            out.append(res)
            if i % 500 == 0:
                c.executemany("UPDATE videos SET labels=? WHERE id=?", [(l, v) for v, l in out])
                c.commit()
                out = []
                print(f"  {i}/{len(rows)}  ${jev_client.spent():.3f}")
    c.executemany("UPDATE videos SET labels=? WHERE id=?", [(l, v) for v, l in out])
    c.commit()
    print(f"OK etiketlendi, Jev maliyeti ${jev_client.spent():.3f}")


# ---------------- kanal-ici analiz ----------------

def analyze() -> dict:
    """Her ozellik icin: patlamis videolarda gorulme orani vs AYNI KANALIN normal videolarinda (0.5x-2x medyan)
    gorulme orani. Kanal basina fark alinip kanallar uzerinden ortalanir (kanal etkisi sabitlenir)."""
    c = db()
    now = datetime.now(timezone.utc)
    bad = bad_channels()
    rows = c.execute("SELECT v.channel_id, v.ratio, v.labels, v.published, v.title, v.views, v.id, ch.niche "
                     "FROM videos v JOIN channels ch ON ch.id=v.channel_id "
                     "WHERE v.ratio IS NOT NULL AND v.labels IS NOT NULL AND v.views > 0 "
                     "AND 1.0 * v.likes / v.views >= ?", (MIN_LIKE_RATE,)).fetchall()
    rows = [r for r in rows if r[0] not in bad]
    by_ch: dict[str, list] = {}
    for cid, ratio, lab, pub, title, views, vid, niche in rows:
        if (now - datetime.fromisoformat(pub.replace("Z", "+00:00"))).days < MIN_AGE_DAYS:
            continue
        L = json.loads(lab)
        L.pop("error", None)  # Jev hatasi (or. kredi bitti): hook/emotion yok ama yerel baslik ozellikleri gecerli
        by_ch.setdefault(cid, []).append({"ratio": ratio, "L": L, "title": title, "views": views, "id": vid,
                                          "niche": niche})
    feats: dict[str, list[float]] = {}
    counts: dict[str, list[int]] = {}
    n_ch = 0
    examples = []
    for cid, vs in by_ch.items():
        outs = [v for v in vs if v["ratio"] >= OUTLIER_X]
        norm = [v for v in vs if 0.5 <= v["ratio"] <= 2.0]
        if not outs or len(norm) < 5:
            continue
        n_ch += 1
        keys = set()
        for v in vs:
            for k, val in v["L"].items():
                keys.add(f"{k}={val}" if isinstance(val, str) else k if val else None)
        keys.discard(None)
        for key in keys:
            def has(v):
                if "=" in key:
                    k, val = key.split("=", 1)
                    return v["L"].get(k) == val
                return bool(v["L"].get(key))
            po = sum(map(has, outs)) / len(outs)
            pn = sum(map(has, norm)) / len(norm)
            feats.setdefault(key, []).append(po - pn)
            cnt = counts.setdefault(key, [0, 0])
            cnt[0] += sum(map(has, outs))
            cnt[1] += len(outs)
        best = max(outs, key=lambda v: v["ratio"])
        examples.append({"channel": cid, "niche": best["niche"], "title": best["title"], "ratio": round(best["ratio"], 1),
                         "views": best["views"], "id": best["id"],
                         "channel_normal_titles": [v["title"] for v in norm[:3]]})
    res = []
    for key, diffs in feats.items():
        if len(diffs) < 8:
            continue
        m = statistics.mean(diffs)
        se = statistics.stdev(diffs) / math.sqrt(len(diffs)) if len(diffs) > 1 else 1
        res.append({"feature": key, "diff_pp": round(100 * m, 1), "z": round(m / se, 2) if se else 0,
                    "channels": len(diffs), "outlier_share": round(counts[key][0] / max(1, counts[key][1]), 3)})
    res.sort(key=lambda r: -r["z"])
    report = {"channels_compared": n_ch, "videos": len(rows), "outlier_x": OUTLIER_X,
              "features": res, "examples": sorted(examples, key=lambda e: -e["ratio"])[:60]}
    out = Path("work/research/atlas_report.json")
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{n_ch} kanal karsilastirildi ({len(rows)} video)")
    print("Patlamis videolarda DAHA SIK (kanal-ici, yuzde puan farki, z):")
    for r in res[:10]:
        print(f"  +{r['diff_pp']:>5} pp  z={r['z']:>5}  {r['feature']}  ({r['channels']} kanal)")
    print("DAHA SEYREK:")
    for r in res[-6:]:
        print(f"  {r['diff_pp']:>6} pp  z={r['z']:>5}  {r['feature']}")
    print(f"OK -> {out}")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["crawl", "label", "analyze"])
    p.add_argument("--niche", default="whatif,character,podcast")
    p.add_argument("--per-channel", type=int, default=150)
    p.add_argument("--budget", type=int, default=5000)
    p.add_argument("--limit", type=int, default=20000)
    a = p.parse_args()
    if a.cmd == "crawl":
        crawl(a.niche.split(","), a.per_channel, a.budget)
    elif a.cmd == "label":
        label(a.limit)
    else:
        analyze()


if __name__ == "__main__":
    main()
