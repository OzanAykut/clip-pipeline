import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from wts_render import render_wts_clips

# Ilk segment her klipte "flash-forward": en carpici an basa, sonra hikaye bastan akiyor.
render_wts_clips(
    source=Path("work/wts/RR_EP_204_Textless_VFinal_260924.mp4"),
    transcript_path=Path("work/wts_rr204/transcript.json"),
    work=Path("work/wts_rr204/render"),
    name_fixes={"emily": "Emaly"},
    clips=[
        {
            "name": "rr_ive_got_it_handled",
            "headline": "\"I'VE GOT IT HANDLED.\"",
            "hook_words": ["gas"],
            "segments": [
                (840.1, 844.8),
                (277.0, 278.3),
                (283.1, 287.8),
                (294.8, 299.7),
                (743.0, 752.9),
                (757.0, 763.9),
                (836.1, 848.3),
            ],
        },
        {
            "name": "rr_survival_dad",
            "headline": "DAD'S SURVIVAL LESSON",
            "hook_words": ["poop"],
            "segments": [
                (473.9, 475.7),
                (442.2, 480.3),
            ],
        },
    ],
)
print("\nDONE")
