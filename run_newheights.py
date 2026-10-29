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
    add_headline_and_narration,
    add_pattern_interrupts,
    add_avatar_overlay,
    add_broll_insert,
    compute_broll_insert_time,
    fetch_pexels_photo,
    apply_fingerprint_break,
)

video_id = "newheights_cruise"
work_dir = Path("work") / video_id
source_path = work_dir / "source.mp4"
out_dir = Path("output") / video_id
out_dir.mkdir(parents=True, exist_ok=True)
captioned_dir = Path("output") / "captioned_batch"
captioned_dir.mkdir(parents=True, exist_ok=True)

clips = json.load(open(work_dir / "manual_candidates.json", encoding="utf-8"))
transcript = json.load(open(work_dir / "transcript.json", encoding="utf-8"))
flat_words = [
    {"word": w["word"], "start": w["start"], "end": w["end"]}
    for seg in transcript["segments"]
    for w in seg.get("words", [])
]

results = []
for i, clip in enumerate(clips, start=1):
    base_path = out_dir / f"{i:02d}_{clip['name']}_base.mp4"
    punch_path = out_dir / f"{i:02d}_{clip['name']}_punch.mp4"
    narrated_path = out_dir / f"{i:02d}_{clip['name']}_narrated.mp4"
    avatar_path = out_dir / f"{i:02d}_{clip['name']}_avatar.mp4"
    broll_path = out_dir / f"{i:02d}_{clip['name']}_broll.mp4"
    clip_words = [w for w in flat_words if w["end"] > clip["start"] and w["start"] < clip["end"]]
    print(f"\n[{i}/{len(clips)}] {clip['title']} [{clip['start']:.1f}-{clip['end']:.1f}]")
    try:
        render_clip(source_path, clip, clip_words, base_path, work_dir / "tmp")
        print(f"base OK -> {base_path}")

        add_pattern_interrupts(base_path, clip["hook_words"], clip_words, clip["start"], clip["end"], punch_path)
        print(f"pattern-interrupt OK -> {punch_path}")

        add_headline_and_narration(punch_path, clip["headline"], clip["narration"], narrated_path, work_dir / "tmp")
        print(f"narration OK -> {narrated_path}")

        add_avatar_overlay(narrated_path, avatar_path)
        print(f"avatar overlay OK -> {avatar_path}")

        broll_img = work_dir / "broll" / f"{clip['name']}.jpg"
        got_broll = clip.get("broll_query") and fetch_pexels_photo(clip["broll_query"], broll_img)
        if got_broll:
            insert_time = compute_broll_insert_time(clip["hook_words"], clip_words, clip["start"], clip["end"])
            add_broll_insert(avatar_path, broll_img, insert_time, broll_path)
            print(f"broll OK (t={insert_time:.1f}s) -> {broll_path}")
        else:
            broll_path = avatar_path
            print("broll SKIPPED (Pexels sonucu yok)")

        final_name = f"newheights_{i:02d}_{clip['name']}.mp4"
        final_path = captioned_dir / final_name
        apply_fingerprint_break(broll_path, final_path)
        print(f"fingerprint-break OK -> {final_path}")

        base_path.unlink(missing_ok=True)
        punch_path.unlink(missing_ok=True)
        narrated_path.unlink(missing_ok=True)
        avatar_path.unlink(missing_ok=True)
        broll_path.unlink(missing_ok=True)

        clip["file"] = final_name
        results.append(clip)
        print(f"OK -> {final_path}")
    except Exception as e:
        print(f"FAILED clip {i}: {e}")

with open(out_dir / "clips.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\nDone. {len(results)}/{len(clips)} clips rendered.")
