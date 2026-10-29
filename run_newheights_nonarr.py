import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from render import (
    render_clip,
    add_headline_overlay,
    add_pattern_interrupts,
    add_avatar_overlay,
    add_broll_insert,
    compute_broll_insert_time,
    fetch_pexels_photo,
    apply_fingerprint_break,
)

HEADLINE_SECONDS = 3.0

video_id = "newheights_cruise"
work_dir = Path("work") / video_id
source_path = work_dir / "source.mp4"
out_dir = Path("output") / video_id
out_dir.mkdir(parents=True, exist_ok=True)
final_dir = Path("output") / "shorts_nonarr"
final_dir.mkdir(parents=True, exist_ok=True)

clips = json.load(open(work_dir / "nonarr_candidates.json", encoding="utf-8"))
transcript = json.load(open(work_dir / "transcript.json", encoding="utf-8"))
flat_words = [
    {"word": w["word"], "start": w["start"], "end": w["end"]}
    for seg in transcript["segments"]
    for w in seg.get("words", [])
]

done = 0
for i, clip in enumerate(clips, start=1):
    stem = f"nonarr_{i:02d}_{clip['name']}"
    base_path = out_dir / f"{stem}_base.mp4"
    punch_path = out_dir / f"{stem}_punch.mp4"
    headline_path = out_dir / f"{stem}_headline.mp4"
    avatar_path = out_dir / f"{stem}_avatar.mp4"
    broll_path = out_dir / f"{stem}_broll.mp4"
    clip_words = [w for w in flat_words if w["end"] > clip["start"] and w["start"] < clip["end"]]
    print(f"\n[{i}/{len(clips)}] {clip['title']} [{clip['start']:.1f}-{clip['end']:.1f}]")
    try:
        render_clip(source_path, clip, clip_words, base_path, work_dir / "tmp")
        add_pattern_interrupts(base_path, clip["hook_words"], clip_words, clip["start"], clip["end"], punch_path)
        add_headline_overlay(punch_path, clip["headline"], headline_path, work_dir / "tmp", display_seconds=HEADLINE_SECONDS)
        add_avatar_overlay(headline_path, avatar_path)

        broll_img = work_dir / "broll" / f"{clip['name']}.jpg"
        if broll_img.exists() or fetch_pexels_photo(clip["broll_query"], broll_img):
            insert_time = compute_broll_insert_time(clip["hook_words"], clip_words, clip["start"], clip["end"])
            add_broll_insert(avatar_path, broll_img, insert_time, broll_path)
            print(f"broll OK (t={insert_time:.1f}s)")
        else:
            broll_path = avatar_path
            print("broll SKIPPED")

        final_path = final_dir / f"newheights_{stem}.mp4"
        apply_fingerprint_break(broll_path, final_path)
        print(f"OK -> {final_path}")
        done += 1

        for p in (base_path, punch_path, headline_path, avatar_path, broll_path):
            p.unlink(missing_ok=True)
    except Exception as e:
        print(f"FAILED clip {i}: {e}")

print(f"\nDone. {done}/{len(clips)} clips rendered.")
