"""Rakip Shorts arastirmasi: hangi hook'lar ve video yapilari izleyiciyi tutuyor?

Rakiplerin retention egrisi disaridan alinamaz (Shorts'ta 'most replayed' yok) -> basari vekili OUTLIER skoru:
videonun izlenmesi / kanalin son yuklemelerinin medyan izlenmesi. Siniflandirmayi Jev yapar (jev_client.py).

  python niche_research.py collect  <nis>          # YouTube API ile korpus + outlier skorlari
  python niche_research.py process  <nis> [--n 60] # top/bottom/rastgele ornek: indir, transcript, kesimler
  python niche_research.py classify <nis>          # Jev: video ve ~2.5 sn'lik bolum etiketleri
  python niche_research.py report   <nis>          # top vs bottom karsilastirmasi -> summary.json
Nisler: whatif, character, podcast. Ciktilar: work/research/<nis>/
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import re
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path("work/research")
NICHES = {
    "whatif": ["what if", "what would happen if", "what if earth", "what if you fell into",
               "what happens if you", "what if the sun", "science what if shorts", "physics shorts"],
    "character": ["animated science shorts", "cartoon explains science", "science animation short",
                  "animated fun facts", "what if animation", "educational cartoon shorts",
                  "animated explainer shorts", "cartoon character explains"],
    "podcast": ["podcast clips", "podcast shorts", "funny podcast moment", "podcast story clip",
                "celebrity podcast clip", "comedy podcast clip", "interview clip shorts", "viral podcast moment"],
}
NICHE_DESC = {
    "whatif": "a 'what if' / science / space / physics curiosity short explaining what would happen in a hypothetical scenario",
    "character": "an animated or cartoon educational short where a character explains science or facts",
    "podcast": "a clip from a podcast, talk show or interview with people talking (not music, not an ad)",
}
SEG_LEN = 2.5  # bolum siniflandirmasi icin transcript parca uzunlugu (sn)
MIN_CHANNEL_MEDIAN = 2000  # kucuk/olu kanallarin medyani anlamsiz outlier uretir
MIN_LIKE_RATE = 0.003      # reklamlar (ucretli gosterim) cok dusuk begeni oranina sahip


def _eligible(v: dict) -> bool:
    return bool(v.get("outlier")) and v["channel_median"] >= MIN_CHANNEL_MEDIAN and v["like_rate"] >= MIN_LIKE_RATE


def relevance(niche: str, vids: list[dict], workers: int = 8) -> list[dict]:
    """Jev ile basligin nise uygunlugu (sarki, reklam, alakasiz arama sonuclarini eler). Sonuc korpusa yazilir."""
    import jev_client
    q = {"in_niche": jev_client.noul(f"Is this video {NICHE_DESC[niche]}?", "Yes, it belongs to this niche.",
                                     "No: music, advertisement, unrelated topic or different format.")}

    def one(v):
        if "in_niche" not in v:
            a = jev_client.decide({"title": v["title"], "channel": v["channel"]}, q)
            v["in_niche"] = round(a["in_niche"].get("noul", 0), 3)
        return v

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, vids))
    return vids
_quota = 0


def _yt():
    from youtube_api import clients
    return clients("whatif")[0]


def _iso_dur(s: str) -> float:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0.0
    h, mi, se = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + se


def _chunks(xs, n):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


# ---------------- 1) korpus ----------------

def collect(niche: str, per_query: int = 50, months: int = 12) -> Path:
    global _quota
    yt = _yt()
    after = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30 * months)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids: dict[str, str] = {}
    for q in NICHES[niche]:
        r = yt.search().list(part="snippet", q=q, type="video", videoDuration="short", order="viewCount",
                             publishedAfter=after, maxResults=per_query, relevanceLanguage="en").execute()
        _quota += 100
        for it in r.get("items", []):
            ids.setdefault(it["id"]["videoId"], q)
        print(f"  '{q}': {len(r.get('items', []))} sonuc (toplam benzersiz {len(ids)})")
    vids = []
    for part in _chunks(list(ids), 50):
        r = yt.videos().list(part="snippet,statistics,contentDetails", id=",".join(part)).execute()
        _quota += 1
        for v in r["items"]:
            dur = _iso_dur(v["contentDetails"]["duration"])
            if dur == 0 or dur > 180:
                continue
            st = v["statistics"]
            vids.append({"id": v["id"], "title": v["snippet"]["title"], "channel_id": v["snippet"]["channelId"],
                         "channel": v["snippet"]["channelTitle"], "published": v["snippet"]["publishedAt"],
                         "duration": dur, "views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                         "comments": int(st.get("commentCount", 0)), "query": ids[v["id"]]})
    medians = _channel_medians(yt, {v["channel_id"] for v in vids})
    for v in vids:
        med = medians.get(v["channel_id"]) or 0
        v["channel_median"] = med
        v["outlier"] = round(v["views"] / med, 3) if med else None
        v["like_rate"] = round(v["likes"] / v["views"], 5) if v["views"] else 0
        v["comment_rate"] = round(v["comments"] / v["views"], 6) if v["views"] else 0
    out = ROOT / niche / "corpus.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(vids, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"OK {len(vids)} video, {len(medians)} kanal -> {out}   (kota ~{_quota} birim)")
    return out


def _channel_medians(yt, channel_ids: set[str]) -> dict[str, float]:
    """Kanalin son 50 yuklemesinin medyan izlenmesi (kanal basina ~2 birim kota)."""
    global _quota
    uploads = {}
    for part in _chunks(list(channel_ids), 50):
        r = yt.channels().list(part="contentDetails", id=",".join(part)).execute()
        _quota += 1
        for c in r.get("items", []):
            uploads[c["id"]] = c["contentDetails"]["relatedPlaylists"]["uploads"]
    med = {}
    for cid, pl in uploads.items():
        try:
            items = yt.playlistItems().list(part="contentDetails", playlistId=pl, maxResults=50).execute()["items"]
            _quota += 1
            vids = [i["contentDetails"]["videoId"] for i in items]
            r = yt.videos().list(part="statistics", id=",".join(vids)).execute()
            _quota += 1
            views = [int(v["statistics"].get("viewCount", 0)) for v in r["items"]]
            med[cid] = statistics.median(views) if views else 0
        except Exception as e:  # silinmis/gizli playlist
            print(f"  kanal {cid}: {e}")
    return med


# ---------------- 2) indirme + transcript + kesimler ----------------

def _download(vid: str, d: Path) -> Path:
    import yt_dlp
    out = d / "v.mp4"
    if out.exists():
        return out
    d.mkdir(parents=True, exist_ok=True)
    opts = {"quiet": True, "no_warnings": True, "noprogress": True, "sleep_interval": 3, "max_sleep_interval": 8, "sleep_interval_requests": 1, "outtmpl": str(d / "v.%(ext)s"),
            "format": "bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[height<=480]/worst", "merge_output_format": "mp4"}
    with yt_dlp.YoutubeDL(opts) as y:
        y.download([f"https://www.youtube.com/shorts/{vid}"])
    if not out.exists():
        alt = next(d.glob("v.*"), None)
        if alt is None:
            raise RuntimeError("indirilemedi")
        out = alt
    return out


def cut_times(path: Path) -> list[float]:
    """Yuz tespiti olmadan hafif kesim tespiti (smart_layout esikleriyle ayni)."""
    import cv2
    import numpy as np

    from smart_layout import CUT_DIFF, CUT_THRESHOLD, _hist, _read_frames, _source_fps
    from utils import ffprobe_duration
    fps = _source_fps(path)
    cuts, prev_h, prev_g, last = [], None, None, -1.0
    for i, f in enumerate(_read_frames(path, 0, ffprobe_duration(path), 320, 180)):
        t = i / fps
        h = _hist(f)
        g = cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (64, 36)).astype(np.float32)
        if prev_h is not None and t - last >= 0.4:
            corr = cv2.compareHist(prev_h, h, cv2.HISTCMP_CORREL)
            if corr < CUT_THRESHOLD or float(np.abs(g - prev_g).mean()) > CUT_DIFF:
                cuts.append(round(t, 2))
                last = t
        prev_h, prev_g = h, g
    return cuts


def _features(v: dict, tr: dict, cuts: list[float]) -> dict:
    words = [w for s in tr["segments"] for w in s.get("words", [])]
    dur = tr.get("duration") or v["duration"]
    text = " ".join(s["text"].strip() for s in tr["segments"]).strip()
    hook = " ".join(w["word"].strip() for w in words if w["start"] < 3.0)
    first_word = words[0]["start"] if words else None
    segs = []
    t = 0.0
    while t < dur:
        chunk = " ".join(w["word"].strip() for w in words if t <= w["start"] < t + SEG_LEN)
        segs.append({"t0": round(t, 2), "t1": round(min(dur, t + SEG_LEN), 2), "text": chunk,
                     "cuts": sum(1 for c in cuts if t <= c < t + SEG_LEN)})
        t += SEG_LEN
    last_text = tr["segments"][-1]["text"].strip() if tr["segments"] else ""
    return {"duration": round(dur, 2), "text": text, "hook_3s": hook, "words": len(words),
            "wps": round(len(words) / dur, 2) if dur else 0, "cuts": len(cuts),
            "cps": round(len(cuts) / dur, 2) if dur else 0, "first_cut": cuts[0] if cuts else None,
            "first_word": first_word, "ends_question": last_text.endswith("?"),
            "has_cta": bool(re.search(r"\b(follow|subscribe|comment|like|part 2)\b", text, re.I)),
            "segments": segs}


def process(niche: str, n: int = 60, workers: int = 3) -> None:
    from transcribe import transcribe_video
    cpath = ROOT / niche / "corpus.json"
    corpus = json.loads(cpath.read_text(encoding="utf-8"))
    pool = [v for v in corpus if _eligible(v)]
    relevance(niche, pool)
    cpath.write_text(json.dumps(corpus, indent=1, ensure_ascii=False), encoding="utf-8")
    pool = [v for v in pool if v["in_niche"] >= 0.5]
    print(f"{len(corpus)} video -> {len(pool)} uygun (reklam/kucuk kanal/nis disi elendi)")
    ranked = sorted(pool, key=lambda v: v["outlier"], reverse=True)
    q = max(1, n // 3)
    top, bottom = ranked[:q], ranked[-q:]
    middle = ranked[q:-q]
    random.seed(7)
    pick = {v["id"]: ("top", v) for v in top}
    pick.update({v["id"]: ("bottom", v) for v in bottom})
    for v in random.sample(middle, min(len(middle), n - len(pick))):
        pick.setdefault(v["id"], ("mid", v))
    out_path = ROOT / niche / "processed.json"
    done = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}

    def dl(item):
        vid, (grp, v) = item
        try:
            return vid, _download(vid, ROOT / niche / vid), None
        except Exception as e:
            return vid, None, str(e)[:200]

    todo = [(k, x) for k, x in pick.items() if k not in done]
    print(f"{len(pick)} video secildi ({len(top)} top / {len(bottom)} bottom), {len(todo)} islenecek")
    with ThreadPoolExecutor(workers) as ex:
        paths = list(ex.map(dl, todo))
    for vid, path, err in paths:
        grp, v = pick[vid]
        if err:
            print(f"  {vid}: indirme hatasi {err}")
            continue
        try:
            tr = transcribe_video(path, path.parent, model_size="small", language="en")
            cuts = cut_times(path)
            done[vid] = {**v, "group": grp, **_features(v, tr, cuts)}
            print(f"  {vid} [{grp}] x{v['outlier']}  {done[vid]['wps']} kel/sn  {done[vid]['cps']} kesim/sn  "
                  f"hook: {done[vid]['hook_3s'][:70]}")
        except Exception as e:
            print(f"  {vid}: isleme hatasi {str(e)[:200]}")
        out_path.write_text(json.dumps(done, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"OK {len(done)} video -> {out_path}")


# ---------------- 3) Jev siniflandirma ----------------

def _video_questions():
    from jev_client import choice, noul
    return {
        "hook_type": choice({
            "shock_number": "Opens with a surprising number, size, speed or statistic.",
            "question": "Opens by asking the viewer a question.",
            "danger_threat": "Opens with danger, a threat or something terrible about to happen.",
            "you_pov": "Puts the viewer in the scene ('you are', 'imagine you').",
            "myth_bust": "Says something people believe is wrong / reveals a misconception.",
            "curiosity_gap": "Teases a secret or outcome without revealing it.",
            "bold_claim": "A bold or controversial statement or opinion.",
            "story_start": "Starts in the middle of a personal story or anecdote.",
            "visual_only": "No meaningful spoken hook; relies on the visual or music.",
            "celebrity_name": "Leads with a famous person's name or presence.",
        }, "Classify the main hook used in the first 3 seconds of this short video."),
        "emotion": choice({
            "curiosity": "curiosity / wonder", "fear": "fear or anxiety", "humor": "humor, comedy",
            "awe": "awe at scale or beauty", "outrage": "outrage or controversy",
            "relatable": "relatable everyday situation",
        }, "Which emotion does the video mainly trigger?"),
        "structure": choice({
            "list_facts": "A list of facts or steps.", "story": "A narrative with a beginning, middle and end.",
            "myth_bust": "Misconception first, then the correction.",
            "escalation": "Events escalate step by step (timeline, 'then...').",
            "reaction_moment": "A single funny/shocking moment or reaction.",
            "explainer": "A plain explanation of one concept.",
            "dialogue": "A back-and-forth conversation between people.",
        }, "What is the overall structure of the video?"),
        "ending": choice({
            "question_viewer": "Ends by asking the viewer a question.", "cta": "Ends with follow/subscribe/comment request.",
            "loop": "The ending flows back into the beginning (seamless loop).", "punchline": "Ends on a joke or punchline.",
            "cliffhanger": "Ends unresolved / part 2 teaser.", "plain": "Simply ends after the last fact.",
        }, "How does the video end?"),
        "direct_address": noul("Does the speaker address the viewer directly as 'you'?",
                               "Speaks to the viewer as 'you'.", "Does not address the viewer."),
        "open_loop": noul("Does the hook create an unanswered question that keeps the viewer watching until it is answered later?",
                          "Yes, the hook opens a question that is resolved later.", "No open question."),
    }


def _segment_questions():
    from jev_client import choice, noul
    return {
        "role": choice({
            "hook": "Grabs attention at the start.", "setup": "Gives context or background.",
            "escalation": "Raises stakes, tension or intensity.", "reveal": "Delivers the answer, payoff or surprising fact.",
            "twist": "Contradicts what was expected.", "joke": "A joke or funny beat.",
            "cta": "Asks the viewer to like, follow, comment.", "filler": "Low-information filler or transition.",
        }, "What role does this part play in the short video?"),
        "curiosity_open": noul("After this part, does the viewer still have an unanswered question pulling them to keep watching?",
                               "Yes, something is still unresolved.", "No, nothing pulls the viewer forward."),
    }


def classify(niche: str, workers: int = 8, segments: bool = True) -> None:
    import jev_client
    p = ROOT / niche / "processed.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    vq, sq = _video_questions(), _segment_questions()

    def one(vid):
        v = data[vid]
        state = {"title": v["title"], "first_3_seconds": v["hook_3s"], "transcript": v["text"][:2000],
                 "duration_s": v["duration"]}
        ans = jev_client.decide(state, vq)
        v["jev"] = {k: (a.get("choice") if a["type"] == "choice" else round(a.get("noul", 0), 3))
                    for k, a in ans.items()}
        v["jev_prob"] = {k: a.get("probabilities") for k, a in ans.items() if a["type"] == "choice"}
        if segments:
            n = len(v["segments"])
            for i, s in enumerate(v["segments"]):
                if not s["text"]:
                    s["role"], s["curiosity_open"] = "visual_only", None
                    continue
                st = {"video_hook": v["hook_3s"], "part_text": s["text"], "position": f"part {i + 1} of {n}",
                      "previous_part": v["segments"][i - 1]["text"] if i else ""}
                a = jev_client.decide(st, sq)
                s["role"] = a["role"].get("choice")
                s["curiosity_open"] = round(a["curiosity_open"].get("noul", 0), 3)
        return vid

    todo = [k for k, v in data.items() if "jev" not in v]
    with ThreadPoolExecutor(workers) as ex:
        for i, vid in enumerate(ex.map(one, todo), 1):
            print(f"  {i}/{len(todo)} {vid} {data[vid]['jev']}")
            if i % 10 == 0:
                p.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"OK siniflandirildi. Jev maliyeti bu oturum: ${jev_client.spent():.4f}")


# ---------------- 4) rapor ----------------

def report(niche: str) -> dict:
    data = list(json.loads((ROOT / niche / "processed.json").read_text(encoding="utf-8")).values())
    data = [v for v in data if "jev" in v]
    top = [v for v in data if v["group"] == "top"]
    bot = [v for v in data if v["group"] == "bottom"]

    def share(group, key, val):
        return sum(1 for v in group if v["jev"].get(key) == val) / max(1, len(group))

    labels = {}
    for key in ("hook_type", "emotion", "structure", "ending"):
        vals = sorted({v["jev"].get(key) for v in data if v["jev"].get(key)})
        rows = []
        for val in vals:
            t, b = share(top, key, val), share(bot, key, val)
            outs = [v["outlier"] for v in data if v["jev"].get(key) == val]
            rows.append({"label": val, "top_share": round(t, 3), "bottom_share": round(b, 3),
                         "lift": round((t + 0.02) / (b + 0.02), 2), "n": len(outs),
                         "median_outlier": round(statistics.median(outs), 2)})
        labels[key] = sorted(rows, key=lambda r: -r["lift"])
    for key in ("direct_address", "open_loop"):
        t = statistics.mean(v["jev"][key] for v in top) if top else 0
        b = statistics.mean(v["jev"][key] for v in bot) if bot else 0
        labels[key] = {"top_mean": round(t, 3), "bottom_mean": round(b, 3)}

    def med(group, k):
        xs = [v[k] for v in group if v.get(k) is not None]
        return round(statistics.median(xs), 2) if xs else None

    numeric = {k: {"top": med(top, k), "bottom": med(bot, k)}
               for k in ("duration", "wps", "cps", "first_cut", "first_word")}
    numeric["ends_question"] = {"top": round(share_bool(top, "ends_question"), 2),
                                "bottom": round(share_bool(bot, "ends_question"), 2)}
    numeric["has_cta"] = {"top": round(share_bool(top, "has_cta"), 2), "bottom": round(share_bool(bot, "has_cta"), 2)}

    # bolum rolleri: videonun ilk/orta/son ucunde rollerin dagilimi (top vs bottom)
    def role_profile(group):
        prof = {"first": {}, "middle": {}, "last": {}}
        for v in group:
            segs = [s for s in v["segments"] if s.get("role")]
            for i, s in enumerate(segs):
                part = "first" if i < len(segs) / 3 else ("middle" if i < 2 * len(segs) / 3 else "last")
                prof[part][s["role"]] = prof[part].get(s["role"], 0) + 1
        return {p: {r: round(c / max(1, sum(d.values())), 2) for r, c in sorted(d.items(), key=lambda x: -x[1])}
                for p, d in prof.items()}

    def curiosity_curve(group):
        pts = [[] for _ in range(5)]
        for v in group:
            segs = v["segments"]
            for i, s in enumerate(segs):
                if s.get("curiosity_open") is not None:
                    pts[min(4, int(5 * i / max(1, len(segs))))].append(s["curiosity_open"])
        return [round(statistics.mean(p), 2) if p else None for p in pts]

    summary = {
        "niche": niche, "n": len(data), "n_top": len(top), "n_bottom": len(bot),
        "median_outlier_top": med(top, "outlier"), "median_outlier_bottom": med(bot, "outlier"),
        "labels": labels, "numeric": numeric,
        "roles": {"top": role_profile(top), "bottom": role_profile(bot)},
        "curiosity_curve": {"top": curiosity_curve(top), "bottom": curiosity_curve(bot)},
        "best_hooks": [{"id": v["id"], "outlier": v["outlier"], "views": v["views"], "hook": v["hook_3s"],
                        "title": v["title"], "type": v["jev"]["hook_type"]}
                       for v in sorted(top, key=lambda v: -v["outlier"])[:12]],
    }
    out = ROOT / niche / "summary.json"
    out.write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("niche", "n", "median_outlier_top", "median_outlier_bottom")}))
    for key in ("hook_type", "structure", "ending"):
        print(f"  {key}: " + ", ".join(f"{r['label']} x{r['lift']}" for r in labels[key][:4]))
    print(f"  sayisal (top/bottom): " + ", ".join(f"{k} {v['top']}/{v['bottom']}" for k, v in numeric.items()))
    print(f"OK -> {out}")
    return summary


def share_bool(group, k):
    return sum(1 for v in group if v.get(k)) / max(1, len(group))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["collect", "process", "classify", "report"])
    p.add_argument("niche", choices=list(NICHES))
    p.add_argument("--n", type=int, default=60)
    p.add_argument("--per-query", type=int, default=50)
    p.add_argument("--no-segments", action="store_true")
    p.add_argument("--workers", type=int, default=3)
    a = p.parse_args()
    if a.cmd == "collect":
        collect(a.niche, a.per_query)
    elif a.cmd == "process":
        process(a.niche, a.n, workers=a.workers)
    elif a.cmd == "classify":
        classify(a.niche, segments=not a.no_segments)
    else:
        report(a.niche)


if __name__ == "__main__":
    main()
