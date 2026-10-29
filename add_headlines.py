import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from render import add_headline_overlay

OUT_DIR = Path("output") / "captioned_batch"
OUT_DIR.mkdir(parents=True, exist_ok=True)
TMP_DIR = Path("work") / "_headline_tmp"

HEADLINES = {
    "fullsend_lebron": {
        "fullsend_01_harvests_sons_blood.mp4": "HE HARVESTS HIS SON'S BLOOD",
        "fullsend_02_lost_3000_golf_match.mp4": "HE LOST $3,000 IN ONE HOLE",
        "fullsend_03_how_lebron_reached_out.mp4": "LEBRON SLID INTO THEIR DMS",
        "fullsend_04_lebron_asked_about_luca.mp4": "LEBRON LEFT HIM SPEECHLESS",
        "fullsend_05_nba_players_good_at_golf.mp4": "NBA PLAYERS ARE TOO GOOD AT GOLF",
        "fullsend_06_million_dollar_tournament_plans.mp4": "HIS $1M TOURNAMENT PLAN",
        "fullsend_07_mushrooms_mid_round.mp4": "HE TOOK SHROOMS MID-ROUND",
        "fullsend_08_picked_last_like_a_kid.mp4": "PICKED LAST... AGAIN",
    },
    "whiskeyginger_cena": {
        "ws_01_platinum_album_record.mp4": "NO ONE HAS BROKEN CENA'S RECORD",
        "ws_02_make_a_wish_story.mp4": "CENA'S MAKE-A-WISH STORY",
        "ws_03_how_rap_gimmick_started.mp4": "HOW CENA'S RAP GIMMICK STARTED",
        "ws_04_bus_driver_blizzard_story.mp4": "THEIR BUS DRIVER'S INSANE STORY",
        "ws_05_bullied_for_hip_hop.mp4": "CENA GOT BULLIED FOR THIS",
        "ws_06_ping_pong_ball_bit.mp4": "THE PING PONG BALL BIT",
        "ws_07_fans_mad_about_hair.mp4": "FANS GOT MAD HE WENT BALD",
        "ws_08_selling_out_isnt_real.mp4": "\"SELLING OUT\" ISN'T REAL",
    },
    "smartless_garfield": {
        "sl_01_social_network_fan_reaction.mp4": "THE WILDEST FAN REACTION EVER",
        "sl_02_how_many_laptops_smashed.mp4": "HOW MANY LAPTOPS DID HE SMASH?",
        "sl_03_truman_show_feeling.mp4": "HE FELT LIKE THE TRUMAN SHOW",
        "sl_04_dad_crying_at_oscars.mp4": "HIS DAD BROKE DOWN AT THE OSCARS",
        "sl_05_grief_quote.mp4": "HIS QUOTE ON GRIEF WILL HIT YOU",
        "sl_06_spider_named_after_him.mp4": "A SPIDER IS NAMED AFTER HIM",
        "sl_07_theater_disaster_story.mp4": "HIS THEATER DISASTER STORY",
        "sl_08_disneyland_birthday.mp4": "HIS DISNEYLAND BIRTHDAY WENT WRONG",
    },
}

total = sum(len(v) for v in HEADLINES.values())
done = 0
for source_id, files in HEADLINES.items():
    src_dir = Path("output") / source_id
    for filename, headline in files.items():
        done += 1
        in_path = src_dir / filename
        out_path = OUT_DIR / filename
        print(f"\n[{done}/{total}] {filename}  ->  \"{headline}\"")
        if not in_path.exists():
            print(f"SKIP (bulunamadi): {in_path}")
            continue
        try:
            add_headline_overlay(in_path, headline, out_path, TMP_DIR)
            print(f"OK -> {out_path}")
        except Exception as e:
            print(f"FAILED: {e}")

print(f"\nDone. Output folder: {OUT_DIR}")
