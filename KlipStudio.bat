@echo off
rem Klip Studio: backend (FastAPI :8765) + arayuz (Vite :5173) baslatir ve tarayicida acar.
cd /d "%~dp0"
start "Klip Studio - backend" /min cmd /c "venv\Scripts\python -m uvicorn studio.backend.app:app --host 127.0.0.1 --port 8765"
start "Klip Studio - arayuz" /min cmd /c "cd studio\web && npm run dev -- --host 127.0.0.1"
timeout /t 4 /nobreak >nul
start "" http://127.0.0.1:5173
