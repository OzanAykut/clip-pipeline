"""Uygulama ici Claude: Claude Desktop'un icindeki Claude Code CLI'yi (claude.exe -p) aboneligle calistirir.
API anahtari kullanilmaz. Claude sadece Klip Studio MCP araclarini kullanabilir (--strict-mcp-config).
Cikti stream-json olarak okunur ve WebSocket ile sohbet paneline akar. Sohbet surekliligi --resume <session>."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_running: dict[str, subprocess.Popen] = {}


def find_cli() -> Path | None:
    """%APPDATA%\\Claude\\claude-code\\<surum>\\<hash>\\claude.exe icinden en yeni surum."""
    # Microsoft Store (MSIX) surumunde dosyalar paket klasorunde durur; uygulama disindan calisan
    # bir surec (KlipStudio.bat) normal %APPDATA% yolunda bulamaz -> ikisine de bak
    bases = [Path(os.environ.get("APPDATA", "")) / "Claude" / "claude-code"]
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    bases += [p / "LocalCache" / "Roaming" / "Claude" / "claude-code" for p in (local / "Packages").glob("Claude_*")]
    cands = [c for b in bases for c in b.glob("*/*/claude.exe")]
    if not cands:
        return None
    ver = lambda p: tuple(int(x) for x in re.findall(r"\d+", p.parent.parent.name)[:3])  # noqa: E731
    return max(cands, key=ver)


def mcp_config() -> Path:
    cfg = ROOT / "studio" / "mcp" / "mcp.runtime.json"
    cfg.write_text(json.dumps({"mcpServers": {"klip-studio": {
        "command": str(Path(sys.executable)), "args": [str(ROOT / "studio" / "mcp" / "server.py")],
        "cwd": str(ROOT)}}}, indent=1), encoding="utf-8")
    return cfg


SYSTEM = """Sen Klip Studio'nun icindeki video edit asistanisin. Kullanici Turkce konusur; Turkce, kisa ve net cevap ver.
Kullanicinin acik projesi: {pid}. Oynatma kafasi: {time:.2f} sn. Secili oge: {selected}.
Projeyi degistirmek icin SADECE klip-studio MCP araclarini kullan (once get_project ile durumu oku).
Yaptigin degisiklikler kullanicinin ekraninda aninda gorunur ve Ctrl+Z ile geri alinabilir.
Uzun islerde (altyazi, kadraj, tarif, disa aktarma) run_tool/export_project kullan. Seslendirme repliklerinde BUYUK HARF
kullanma (TTS harf harf okur)."""


def ask(pid: str, message: str, session: str | None, context: dict, emit) -> None:
    """Arka planda calisir; emit(dict) ile olaylari arayuze iletir."""
    cli = find_cli()
    if not cli:
        emit({"kind": "error", "text": "Claude Code bulunamadi (Claude Desktop kurulu mu?)."})
        return
    cmd = [str(cli), "-p", message, "--output-format", "stream-json", "--verbose",
           "--mcp-config", str(mcp_config()), "--strict-mcp-config", "--allowedTools", "mcp__klip-studio",
           "--append-system-prompt", SYSTEM.format(pid=pid, time=context.get("time", 0), selected=context.get("selected"))]
    if session:
        cmd += ["--resume", session]

    def run():
        try:
            proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                    encoding="utf-8", errors="replace",
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as e:
            emit({"kind": "error", "text": f"Claude baslatilamadi: {e}"})
            return
        _running[pid] = proc
        sid = session
        for line in proc.stdout:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = ev.get("session_id", sid)
            if ev.get("type") == "assistant":
                for c in ev.get("message", {}).get("content", []):
                    if c.get("type") == "text" and c.get("text", "").strip():
                        emit({"kind": "text", "text": c["text"], "session": sid})
                    elif c.get("type") == "tool_use":
                        name = c.get("name", "").replace("mcp__klip-studio__", "")
                        emit({"kind": "tool", "text": name, "input": c.get("input"), "session": sid})
            elif ev.get("type") == "result":
                res = ev.get("result") or ""
                if ev.get("is_error"):
                    if "auth" in res.lower() or "login" in res.lower() or "OAuth" in res:
                        res += "\n\nTerminalde bir kez `claude login` calistirip aboneliginle giris yap."
                    emit({"kind": "error", "text": res, "session": sid})
                else:
                    emit({"kind": "done", "text": "", "session": sid,
                          "cost": ev.get("total_cost_usd"), "turns": ev.get("num_turns")})
        proc.wait()
        _running.pop(pid, None)

    threading.Thread(target=run, daemon=True).start()


def stop(pid: str) -> bool:
    p = _running.get(pid)
    if p and p.poll() is None:
        p.terminate()
        return True
    return False
