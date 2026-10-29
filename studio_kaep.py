"""Kaepernick (Street You Grew Up On) kliplerini Klip Studio projesi olarak hazirlar; loop/kesim kullaniciya birakilir.

Her klip icin: hook parcasi + govde parcasi (kenar paylariyla 9:16 kadrajlanmis, ses -16 LUFS civarina cekilmis),
timeline'da hook basta + govde jump-cut parcalari, sabit manset, kisilan muzik, dogru altyazi.
Kullanici parcalarin kenarlarini surukleyip loop noktasini ayarlar, Altyazi aracini tekrar calistirir (transkript
onbellegi duzeltilmis kelimelerle yazildigi icin Whisper tekrar calismaz), disa aktarir.

Kesit secimi (2026-10-09 kurallari): tek fikir, ilk cumle baglamsiz anlasilir, itiraf/gorus/fikir ayriligi/unlu isim,
<=25-30 sn, siyasi icerik YOK (e5 diz cokme/irkcilik tartismasi elendi)."""
import json
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from audio_cuts import smart_tighten
from smart_render import render_range
from studio.backend.store import PROJECTS, load, new_item, new_project, register_media, save, track

SRC = Path("work/campaigns/evang/src")
TMP = Path("work/campaigns/evang/studio_tmp")
GAIN_DB = 21.5      # kaynak ~-37.5 LUFS -> ~-16
HOOK_PAD, BODY_PAD = 1.5, 2.0
GAP = 1.2           # altyazi blok bosluğu (tools.captions ile ayni)

# kaynak saniyesine gore duzeltmeler: (kaynak, yaklasik baslangic) -> yeni kelime (None = sil)
FIX_AT = {(2, 208.57): "Snoop,", (2, 209.95): "2Pac,", (2, 210.43): None, (2, 215.19): "Korn",
          (2, 8.28): "child"}

CLIPS = [
    # itiraf: kendini farkli renge boyadigi cocuk resmi. Hikaye "draw your family and" ile biter -> hook
    {"name": "colored_myself", "src": 2,
     "headline": "AS A KID, COLIN KAEPERNICK DREW HIS FAMILY *YELLOW* AND HIMSELF *BROWN*",
     "hook": (64.10, 66.80),
     "body": [(0.52, 2.25), (6.46, 12.20), (41.76, 45.00), (47.88, 51.42), (57.54, 64.10)],
     "music": "recollections.mp3", "music_start": 8.0},
    # gorus + fikir ayriligi: Kerry "kazanmayi mi rekabeti mi" diye sikistiriyor. Soru -> hook (cevap)
    {"name": "hate_losing", "src": 1,
     "headline": "COLIN KAEPERNICK: THE MOST COMPETITIVE PEOPLE *DON'T LIKE LOSING*",
     "hook": (202.40, 208.35),
     "body": [(180.31, 191.70), (194.33, 200.98)],
     "music": "ancient_civilisations.mp3", "music_start": 10.0},
    # unlu isimler: abisinin cektigi muzik. "So it would be like" -> "Dr. Dre, Snoop, 2Pac..."
    {"name": "brother_music", "src": 2,
     "headline": "KAEPERNICK'S BROTHER RAISED HIM ON *DR. DRE AND MARILYN MANSON*",
     "hook": (207.60, 219.20),
     "body": [(183.82, 187.20), (192.73, 203.00), (205.47, 206.75)],
     "music": "vibe_check.mp3", "music_start": 6.0},
    # babayla HORSE: kisa versiyon. "I can't hit this shot." -> "my dad being like, are you going to cry?"
    {"name": "cry_or_shoot_short", "src": 1,
     "headline": "KAEPERNICK'S DAD: *CRY OR SHOOT?*",
     "hook": (275.10, 279.40),
     "body": [(228.31, 235.62), (238.87, 248.25), (258.59, 259.88), (261.35, 271.22)],
     "music": "the_theme.mp3", "music_start": 12.0},
]


def source_words(i: int) -> list[dict]:
    tr = json.load(open(f"work/campaigns/evang/tr{i}/transcript.json", encoding="utf-8"))
    out = []
    for s in tr["segments"]:
        for w in s.get("words", []):
            t = w["word"].strip()
            key = next((k for k in FIX_AT if k[0] == i and abs(k[1] - w["start"]) < 0.03), None)
            if key:
                if FIX_AT[key] is None:
                    continue
                t = FIX_AT[key]
            if t.startswith("-") and out:  # "hip" "-hop" -> "hip-hop"
                out[-1]["word"] += t
                out[-1]["end"] = w["end"]
                continue
            out.append({"word": t, "start": w["start"], "end": w["end"]})
    return out


def render_piece(src: Path, words: list[dict], a: float, b: float, out: Path) -> None:
    if out.exists():
        return
    raw = out.with_name(out.stem + "_raw.mp4")
    render_range(src, a, b, words, raw, TMP / "rr")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-c:v", "copy",
                    "-af", f"volume={GAIN_DB}dB,alimiter=limit=0.89:level=false", "-ar", "48000",
                    "-c:a", "aac", "-b:a", "192k", str(out)], check=True)
    raw.unlink()


def write_tr_cache(pid: str, media_name: str, words: list[dict], a: float, b: float) -> list[dict]:
    """Medya dosyasina gore (0'dan baslayan) kelimeler; Altyazi araci bu onbellegi okur."""
    rel = [{"word": w["word"], "start": round(max(0.0, w["start"] - a), 3), "end": round(min(b, w["end"]) - a, 3)}
           for w in words if w["end"] > a and w["start"] < b]
    d = PROJECTS / pid / "cache" / f"tr_{Path(media_name).stem}"
    d.mkdir(parents=True, exist_ok=True)
    seg = {"id": 0, "start": 0.0, "end": round(b - a, 3), "text": " ".join(w["word"] for w in rel), "words": rel}
    (d / "transcript.json").write_text(json.dumps({"language": "en", "duration": b - a, "segments": [seg]},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    return rel


def caption_items(video_items: list[dict], words_by_url: dict[str, list[dict]], style: str) -> list[dict]:
    words = []
    for it in video_items:
        for w in words_by_url[it["src"]]:
            if it["in"] - 0.05 <= w["start"] < it["out"]:
                s = it["start"] + (w["start"] - it["in"])
                e = it["start"] + (min(w["end"], it["out"]) - it["in"])
                words.append({"w": w["word"], "s": round(s, 3), "e": round(max(e, s + 0.05), 3)})
    words.sort(key=lambda w: w["s"])
    blocks: list[list[dict]] = []
    for w in words:
        if not blocks or w["s"] - blocks[-1][-1]["e"] > GAP:
            blocks.append([w])
        else:
            blocks[-1].append(w)
    items = []
    for b in blocks:
        st = max(0.0, b[0]["s"] - 0.05)
        it = new_item("caption", None, st, 0, round(b[-1]["e"] + 0.2 - st, 3),
                      props={"auto": True, "style": style,
                             "words": [{"w": w["w"], "s": round(w["s"] - st, 3), "e": round(w["e"] - st, 3)} for w in b]})
        it["src"] = None
        items.append(it)
    return items


def build(clip: dict) -> str:
    i = clip["src"]
    src = SRC / f"e{i}.mp4"
    words = source_words(i)
    tmp = TMP / clip["name"]
    tmp.mkdir(parents=True, exist_ok=True)
    hs, he = clip["hook"]
    ha, hb = max(0.0, hs - HOOK_PAD), he + HOOK_PAD
    ba = max(0.0, min(s for s, _ in clip["body"]) - BODY_PAD)
    bb = max(e for _, e in clip["body"]) + BODY_PAD
    hook_f, body_f = tmp / f"{clip['name']}_hook.mp4", tmp / f"{clip['name']}_govde.mp4"
    print(f"\n== {clip['name']}: hook {ha:.1f}-{hb:.1f}, govde {ba:.1f}-{bb:.1f}", flush=True)
    render_piece(src, words, ha, hb, hook_f)
    render_piece(src, words, ba, bb, body_f)

    p = new_project(f"Kaep · {clip['name']}")
    pid = p["id"]
    hook_m = register_media(pid, hook_f)
    body_m = register_media(pid, body_f)
    words_by_url = {hook_m["url"]: write_tr_cache(pid, hook_m["name"], words, ha, hb),
                    body_m["url"]: write_tr_cache(pid, body_m["name"], words, ba, bb)}
    music_m = register_media(pid, Path("assets/music") / clip["music"])
    p = load(pid)

    vids = []
    t = 0.0
    hook = new_item("video", hook_m["url"], 0.0, hs - ha, he - ha, props={"fit": "cover", "marks": [
        {"t": hs - ha, "label": "HOOK", "color": "#4ADE80"}]})
    vids.append(hook)
    t += he - hs
    pieces = smart_tighten(src, clip["body"], words=words)  # kesimler sessizlik vadilerinde
    for k, (s, e) in enumerate(pieces):
        it = new_item("video", body_m["url"], round(t, 3), s - ba, e - ba, props={"fit": "cover"})
        vids.append(it)
        t += e - s
    last = vids[-1]
    last["props"]["marks"] = [{"t": last["out"] - 0.03, "label": "↻ LOOP dikişi → başa", "color": "#FDE047"}]
    total = round(t, 3)

    track(p, "video")["items"] = vids
    track(p, "overlay")["items"] = [new_item("text", None, 0.0, 0.0, total, props={
        "text": clip["headline"], "size": 64, "color": "#ffffff", "x": 0.5, "y": 0.1, "scale": 1, "card": True})]
    track(p, "music")["items"] = [new_item("audio", music_m["url"], 0.0, clip["music_start"],
                                           clip["music_start"] + total, volume=0.3,
                                           props={"duck": True, "duckLevel": 0.5})]
    track(p, "caption")["items"] = caption_items(vids, words_by_url, p.get("captionStyle", "pop"))
    p["notes"] = {"hook_src": clip["hook"], "body_src": clip["body"], "hook_file_start": ha, "body_file_start": ba}
    save(pid, p)
    print(f"  proje {pid}: {len(vids)} video parcasi, {total:.1f} sn", flush=True)
    return pid


if __name__ == "__main__":
    only = sys.argv[1:]
    for c in CLIPS:
        if not only or c["name"] in only:
            build(c)
