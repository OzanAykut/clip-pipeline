import sys
import time
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from transcribe import transcribe_video

work_dir = Path("work/chd_erinandrews")
source_path = work_dir / "source.mp4"

t0 = time.time()
transcript = transcribe_video(source_path, work_dir, model_size="small", language="en")
elapsed = time.time() - t0
print(f"DONE segments={len(transcript['segments'])} duration={transcript['duration']:.0f}s elapsed={elapsed:.0f}s")
