import shutil
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from render import add_headline_overlay

SRC_DIR = Path("output") / "ymh_zacefron"
OUT_DIR = Path("output") / "captioned_batch"
OUT_DIR.mkdir(parents=True, exist_ok=True)
TMP_DIR = Path("work") / "_headline_tmp"

# (source file, final descriptive filename, headline banner text)
ITEMS = [
    ("01_clip.mp4", "ymh_01_winston_churchill_scared_of_ledges.mp4", "WINSTON CHURCHILL WAS SCARED OF THIS"),
    ("02_clip.mp4", "ymh_02_driver_loved_smoking_crack.mp4", "WHY THEIR DRIVER LOVED SMOKING CRACK"),
    ("03_clip.mp4", "ymh_03_terrifying_theory_about_death.mp4", "HIS TERRIFYING THEORY ABOUT DEATH"),
    ("04_clip.mp4", "ymh_04_rather_watch_drone_footage.mp4", "HE'D RATHER WATCH DRONE FOOTAGE"),
    ("05_clip.mp4", "ymh_05_craigslist_free_room_ad.mp4", "THIS FREE ROOM AD IS UNHINGED"),
    ("06_clip.mp4", "ymh_06_met_zac_efron_green_room.mp4", "HE MET ZAC EFRON IN THE GREEN ROOM"),
    ("07_clip.mp4", "ymh_07_texted_zac_efron_this.mp4", "SHE TEXTED ZAC EFRON THIS"),
    ("08_clip.mp4", "ymh_08_what_animal_does_she_look_like.mp4", "WHAT ANIMAL DOES SHE LOOK LIKE?"),
]

for i, (src_name, out_name, headline) in enumerate(ITEMS, start=1):
    in_path = SRC_DIR / src_name
    out_path = OUT_DIR / out_name
    print(f"\n[{i}/{len(ITEMS)}] {src_name} -> {out_name}  \"{headline}\"")
    if not in_path.exists():
        print(f"SKIP (bulunamadi): {in_path}")
        continue
    try:
        add_headline_overlay(in_path, headline, out_path, TMP_DIR)
        print(f"OK -> {out_path}")
    except Exception as e:
        print(f"FAILED: {e}")

print(f"\nDone. Output folder: {OUT_DIR}")
