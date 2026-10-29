"""Hook Atlas - Katman B: patlamis videolarin KONUSULAN hook'u vs ayni kanalin normal videolari.

Video indirilmez; YouTube'un otomatik altyazisi (json3, kelime zamanli) yt-dlp ile cekilir. Istekler yavas ve araliklidir
(429'da uzun bekleme, ust uste 3 engelde durur). Sonra Jev ile ayni tipte siniflandirilir ve kanal-ici karsilastirilir.

  python hook_deep.py fetch   [--outliers 120] [--min-ratio 10]
  python hook_deep.py label
  python hook_deep.py analyze      -> work/research/deep_report.json
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB = Path("work/research/atlas.db")
CAP = Path("work/research/deep_caps")
YTDLP = Path("venv/Scripts/yt-dlp.exe")


def db():
    c = sqlite3.connect(DB, timeout=30)
    c.execute("CREATE TABLE IF NOT EXISTS deep(id TEXT PRIMARY KEY, channel_id TEXT, role TEXT, pair TEXT, "
              "status TEXT, hook TEXT, first10 TEXT, wps REAL, first_word REAL, labels TEXT)")
    return c


def pick(c, n_out: int, min_ratio: float) -> list[tuple]:
    """En cok patlamis n video (kanal basina 1) + her biri icin ayni kanaldan 2 normal (0.7-1.5x)."""
    rows = c.execute("SELECT v.id, v.channel_id, v.ratio FROM videos v JOIN channels ch ON ch.id=v.channel_id "
                     "WHERE v.ratio >= ? AND v.duration <= 75 ORDER BY v.ratio DESC", (min_ratio,)).fetchall()
    seen, out = set(), []
    for vid, cid, r in rows:
        if cid in seen:
            continue
        normals = [x for (x,) in c.execute("SELECT id FROM videos WHERE channel_id=? AND ratio BETWEEN 0.7 AND 1.5 "
                                           "AND duration <= 75 ORDER BY RANDOM() LIMIT 2", (cid,))]
        if len(normals) < 2:
            continue
        seen.add(cid)
        out.append((vid, cid, "outlier", vid))
        out += [(x, cid, "normal", vid) for x in normals]
        if len(seen) >= n_out:
            break
    return out


def _parse_json3(f: Path) -> list[dict]:
    d = json.loads(f.read_text(encoding="utf-8"))
    words = []
    for ev in d.get("events", []):
        t0 = ev.get("tStartMs", 0) / 1000
        for s in ev.get("segs", []) or []:
            w = (s.get("utf8") or "").strip()
            if w and w != "\n":
                words.append({"w": w, "t": t0 + s.get("tOffsetMs", 0) / 1000})
    return words


def fetch(n_out: int, min_ratio: float) -> None:
    c = db()
    # liste bir kez secilir; sonraki calistirmalar ayni listeyle kaldigi yerden devam eder
    todo = pick(c, n_out, min_ratio) if not c.execute("SELECT COUNT(*) FROM deep").fetchone()[0] else []
    for vid, cid, role, pair in todo:
        c.execute("INSERT OR IGNORE INTO deep(id, channel_id, role, pair, status) VALUES(?,?,?,?,'todo')",
                  (vid, cid, role, pair))
    c.commit()
    rows = c.execute("SELECT id FROM deep WHERE status='todo'").fetchall()
    print(f"{len(rows)} video icin altyazi cekilecek")
    CAP.mkdir(parents=True, exist_ok=True)
    blocked = 0
    for i, (vid,) in enumerate(rows, 1):
        out = CAP / vid
        cmd = [str(YTDLP), "--skip-download", "--write-auto-subs", "--write-subs", "--sub-langs", "en.*,en",
               "--sub-format", "json3", "--impersonate", "chrome", "--sleep-requests", "1.5",
               "-o", str(out), f"https://www.youtube.com/shorts/{vid}"]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        files = list(CAP.glob(f"{vid}*.json3"))
        err = (r.stderr or "")[-300:]
        if files:
            words = _parse_json3(files[0])
            hook = " ".join(w["w"] for w in words if w["t"] < 3.0)
            first10 = " ".join(w["w"] for w in words if w["t"] < 10.0)
            wps = len([w for w in words if w["t"] < 10.0]) / 10.0
            fw = words[0]["t"] if words else None
            c.execute("UPDATE deep SET status='ok', hook=?, first10=?, wps=?, first_word=? WHERE id=?",
                      (hook, first10, wps, fw, vid))
            blocked = 0
        elif "429" in err or "not a bot" in err or "Sign in" in err:
            blocked += 1
            print(f"  {vid}: ENGEL ({blocked}) -> 10 dk bekleniyor | {err[-120:]}")
            c.commit()
            if blocked >= 3:
                print("Ust uste 3 engel: duruyorum (sonra 'fetch' ile kaldigi yerden devam)")
                return
            time.sleep(600)
            continue
        else:
            c.execute("UPDATE deep SET status='nocaps' WHERE id=?", (vid,))  # sozsuz / altyazisiz video
        c.commit()
        if i % 10 == 0:
            ok = c.execute("SELECT COUNT(*) FROM deep WHERE status='ok'").fetchone()[0]
            print(f"  {i}/{len(rows)}  altyazili {ok}")
        time.sleep(random.uniform(6, 12))
    print("OK fetch bitti")


def label() -> None:
    import jev_client
    from hook_atlas import _questions
    c = db()
    rows = c.execute("SELECT id, hook, first10 FROM deep WHERE status='ok' AND labels IS NULL").fetchall()
    q = _questions()
    q["hook"]["instructions"] = "What kind of hook do the FIRST spoken words of this short video use?"

    def one(r):
        vid, hook, f10 = r
        try:
            a = jev_client.decide({"first_3_seconds_spoken": hook, "first_10_seconds_spoken": f10}, q)
            return vid, json.dumps({k: v.get("choice") for k, v in a.items()})
        except Exception as e:
            return vid, json.dumps({"error": str(e)[:100]})

    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(one, rows))
    c.executemany("UPDATE deep SET labels=? WHERE id=?", [(l, v) for v, l in res])
    c.commit()
    print(f"OK {len(res)} etiketlendi, ${jev_client.spent():.4f}")


def analyze() -> dict:
    c = db()
    rows = c.execute("SELECT d.id, d.role, d.pair, d.status, d.hook, d.wps, d.first_word, d.labels, v.title, v.ratio "
                     "FROM deep d JOIN videos v ON v.id=d.id").fetchall()
    groups: dict[str, dict] = {}
    for vid, role, pair, st, hook, wps, fw, lab, title, ratio in rows:
        g = groups.setdefault(pair, {"outlier": None, "normals": []})
        rec = {"id": vid, "status": st, "hook": hook, "wps": wps, "first_word": fw, "title": title, "ratio": ratio,
               "L": json.loads(lab) if lab else {}}
        if role == "outlier":
            g["outlier"] = rec
        else:
            g["normals"].append(rec)
    pairs = [g for g in groups.values() if g["outlier"] and g["normals"]]

    def share(recs, key, val):
        return sum(1 for r in recs if r["L"].get(key) == val) / max(1, len(recs))

    feats = {}
    for key in ("hook", "emotion"):
        vals = {r["L"].get(key) for g in pairs for r in [g["outlier"], *g["normals"]] if r["L"].get(key)}
        for val in vals:
            diffs = []
            for g in pairs:
                if g["outlier"]["L"] and any(n["L"] for n in g["normals"]):
                    diffs.append(share([g["outlier"]], key, val) - share([n for n in g["normals"] if n["L"]], key, val))
            if len(diffs) >= 10:
                m = statistics.mean(diffs)
                se = statistics.stdev(diffs) / len(diffs) ** 0.5 if len(diffs) > 1 else 1
                feats[f"{key}={val}"] = {"diff_pp": round(100 * m, 1), "z": round(m / se, 2) if se else 0, "pairs": len(diffs)}
    nocaps_out = sum(1 for g in pairs if g["outlier"]["status"] == "nocaps") / max(1, len(pairs))
    nocaps_norm = statistics.mean([sum(1 for n in g["normals"] if n["status"] == "nocaps") / len(g["normals"]) for g in pairs]) if pairs else 0
    wps_o = [g["outlier"]["wps"] for g in pairs if g["outlier"]["wps"] is not None]
    wps_n = [n["wps"] for g in pairs for n in g["normals"] if n["wps"] is not None]
    fw_o = [g["outlier"]["first_word"] for g in pairs if g["outlier"]["first_word"] is not None]
    fw_n = [n["first_word"] for g in pairs for n in g["normals"] if n["first_word"] is not None]
    rep = {
        "pairs": len(pairs),
        "speechless_share": {"outlier": round(nocaps_out, 3), "normal": round(nocaps_norm, 3)},
        "words_per_sec_first10": {"outlier": round(statistics.median(wps_o), 2) if wps_o else None,
                                  "normal": round(statistics.median(wps_n), 2) if wps_n else None},
        "first_word_sec": {"outlier": round(statistics.median(fw_o), 2) if fw_o else None,
                           "normal": round(statistics.median(fw_n), 2) if fw_n else None},
        "features": dict(sorted(feats.items(), key=lambda kv: -kv[1]["z"])),
        "examples": [{"outlier": {k: g["outlier"][k] for k in ("id", "title", "hook", "ratio")},
                      "normals": [{k: n[k] for k in ("id", "title", "hook", "ratio")} for n in g["normals"]]}
                     for g in sorted(pairs, key=lambda g: -(g["outlier"]["ratio"] or 0))[:40]],
    }
    Path("work/research/deep_report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("pairs", "speechless_share", "words_per_sec_first10", "first_word_sec")}, indent=1))
    for k, v in list(rep["features"].items())[:8]:
        print(f"  {k}: {v}")
    return rep


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["fetch", "label", "analyze"])
    p.add_argument("--outliers", type=int, default=120)
    p.add_argument("--min-ratio", type=float, default=10)
    a = p.parse_args()
    {"fetch": lambda: fetch(a.outliers, a.min_ratio), "label": label, "analyze": analyze}[a.cmd]()
