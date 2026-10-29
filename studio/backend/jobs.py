"""Is kuyrugu: tek worker thread (pipeline modulleri global ayar degistirdigi icin eszamanli calistirilmaz).
Her is: {id, pid, kind, args, status: queued|running|done|error, progress 0-1, message, result}.
Ilerleme WebSocket ile arayuze akar."""
from __future__ import annotations

import asyncio
import queue
import threading
import time
import traceback
import uuid

_jobs: dict[str, dict] = {}
_q: queue.Queue = queue.Queue()
_broadcast = None
_loop: asyncio.AbstractEventLoop | None = None
HANDLERS: dict = {}


def handler(name: str):
    def deco(fn):
        HANDLERS[name] = fn
        return fn
    return deco


def set_broadcaster(fn) -> None:
    global _broadcast
    _broadcast = fn


def _emit(job: dict) -> None:
    if _broadcast and _loop:
        asyncio.run_coroutine_threadsafe(_broadcast(job["pid"], {"type": "job", "job": job}), _loop)


def submit(pid: str, kind: str, args: dict) -> dict:
    if kind not in HANDLERS:
        from studio.backend import tools  # noqa: F401  (handler kayitlari)
    if kind not in HANDLERS:
        raise ValueError(f"bilinmeyen arac: {kind}")
    job = {"id": uuid.uuid4().hex[:8], "pid": pid, "kind": kind, "args": args, "status": "queued",
           "progress": 0.0, "message": "sırada", "result": None, "created": time.time()}
    _jobs[job["id"]] = job
    _q.put(job["id"])
    _emit(job)
    return job


def list_jobs(pid: str | None = None) -> list[dict]:
    return sorted([j for j in _jobs.values() if pid is None or j["pid"] == pid], key=lambda j: -j["created"])[:30]


def progress(job: dict, frac: float, message: str = "") -> None:
    job["progress"] = round(max(0.0, min(1.0, frac)), 3)
    if message:
        job["message"] = message
    _emit(job)


def _worker() -> None:
    from studio.backend import tools  # noqa: F401
    while True:
        job = _jobs[_q.get()]
        job["status"] = "running"
        progress(job, 0.0, "başladı")
        try:
            job["result"] = HANDLERS[job["kind"]](job)
            job["status"] = "done"
            progress(job, 1.0, "tamam")
        except SystemExit as e:  # pipeline'daki die() cagrilari
            job["status"], job["message"] = "error", f"pipeline durdu: {e}"
            _emit(job)
        except Exception as e:
            job["status"], job["message"] = "error", str(e)[:500]
            job["trace"] = traceback.format_exc()[-2000:]
            _emit(job)


def start_worker() -> None:
    global _loop
    _loop = asyncio.get_event_loop()
    threading.Thread(target=_worker, daemon=True).start()
