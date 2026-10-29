import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from wts_render import render_wts_clips

render_wts_clips(
    source=Path("work/wts/101TEXTLESSXOCC.mp4"),
    transcript_path=Path("work/wts_xo101_med/transcript.json"),
    work=Path("work/wts_xo101/render"),
    name_fixes={"kara": "Cara", "karra": "Cara", "kurtis": "Curtis"},
    clips=[
        {
            "name": "xo_app_crashed_live",
            "headline": "THE APP CRASHED. LIVE.",
            "hook_words": ["crashing"],
            "segments": [(177.8, 212.9)],
        },
        {
            "name": "xo_we_met_on_facebook",
            "headline": "HOW WE MET ON FACEBOOK",
            "hook_words": ["Facebook"],
            "segments": [(399.5, 412.8), (428.0, 464.6)],
        },
    ],
)
print("\nDONE")
