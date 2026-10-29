import sys
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from pathlib import Path
from transcribe import transcribe_video

video_id = "bertcast_ford"
work_dir = Path("work") / video_id
source_path = work_dir / "source.mp4"

transcribe_video(source_path, work_dir, model_size="small")
print("DONE")
