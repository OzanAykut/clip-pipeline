# clip-pipeline

An AI-assisted toolkit for turning long videos (podcasts, interviews, streams) into vertical short-form clips
for YouTube Shorts, TikTok and Reels — plus **Klip Studio**, a local CapCut-style editor built on top of it.

It started as a single CLI script and grew into a full production pipeline: moment selection, face-aware
vertical reframing, word-level captions, audio-aware jump cuts, loop edits, B-roll, AI-generated explainer
shorts, YouTube analytics and an experiment tracker for figuring out what the algorithm actually rewards.

> Personal project, actively developed. Code comments are mostly in Turkish.

---

## Features

### Clip pipeline (Python)
- **Moment finding** — transcribes with faster-whisper (word timestamps) and asks Gemini for self-contained,
  high-retention moments (`clipper.py`, `select_moments.py`).
- **Face-aware 9:16 reframing** — OpenCV/MediaPipe face tracking per shot, with layouts that switch between a
  full-frame speaker, split screen and three-way views; the active speaker is detected from mouth motion, and
  background faces (posters, album covers) are ignored (`smart_layout.py`).
- **Word-level animated captions** and headline cards, punch-in zooms, an opening "hook zoom" and synthetic SFX
  (whoosh / hit / pop / riser) (`smart_render.py`).
- **Audio-aware jump cuts** — cut points land in real silences found in the audio's energy envelope instead of
  trusting (±100 ms) transcript timestamps; natural short pauses are kept and joins get micro-fades, so edits
  don't sound choppy (`audio_cuts.py`).
- **Loop edits** — the punchline is moved to the start and the story ends right before it, with a crossfaded
  music bed so the loop seam is seamless.
- **Loudness normalization** (−16 LUFS), music ducking under speech, licensed B-roll from Pexels (`broll.py`).
- **AI explainer shorts** — "what if" science shorts and a talking-character format built from Veo clips, Gemini
  TTS narration and game-style HUD overlays (`whatif_render.py`, `gizmo_render.py`, `gizmo_voice.py`,
  `game_hud.py`), and a cinematic letterboxed format (`motiv_cinematic.py`).

### Research & analytics
- **YouTube Data + Analytics API** helper — OAuth per channel, stats, retention curves, scheduled uploads
  (`youtube_api.py`).
- **Hook research** — crawls a niche's Shorts and measures which opening patterns correlate with views
  (`niche_research.py`, `hook_atlas.py`, `hook_deep.py`).
- **Experiment tracker** — every upload is logged with the one variable it changed; stay-to-watch rate, average
  percentage viewed, 3-second hold and audience share are snapshotted at 24 h / 48 h / 7 d
  (`studio/backend/experiments.py`).

### Klip Studio (local editor)
A browser-based editor that runs on your machine (FastAPI backend + React/Vite + Remotion):
- Multi-track timeline: move, trim, split, snap, undo/redo, thumbnails.
- Waveforms on a log scale with **silent regions shaded**; trimming a clip edge **snaps to silence**.
- Preview with loop mode and a "listen to the seam" button for loop edits.
- Auto captions with 29 caption styles, transitions, text cards, music/SFX library with ducking.
- AI tools: moment finding, smart reframe, text-to-speech, silence cut, B-roll; one-click "recipes" that build a
  whole project from a long video.
- Export to MP4 with the same Remotion composition as the preview (WYSIWYG).
- Analytics dashboard (channel stats, retention chart, hook research, experiments).
- **MCP server** so an AI assistant (Claude) can drive the editor — edits show up live in the UI.

---

## Setup (Windows)

Requirements: Python 3.12, Node.js 20+, ffmpeg.

```bash
winget install --id Gyan.FFmpeg -e
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # then fill in your API keys
```

Keys used (`.env`): `GEMINI_API_KEY` (moment selection, TTS), `PEXELS_API_KEY` (B-roll, optional),
`OPENROUTER_API_KEY` (optional). For YouTube features, put an OAuth desktop client at
`secrets/client_secret.json` and run `python youtube_api.py auth <name>`.

### Quick start — CLI

```bash
python clipper.py https://www.youtube.com/watch?v=XXXXXXXX --clips 10 --min 25 --max 60 --lang auto
```

Output goes to `output/<video_id>/` (clips + `clips.json` with start/end, score, title, hook and reasoning).

### Klip Studio

```bash
cd studio\web && npm install && cd ..\..
KlipStudio.bat
```

This starts the backend on `:8765` and the UI on `:5173`.

---

## Project layout

```
clipper.py, select_moments.py, transcribe.py   long video -> clip candidates
smart_render.py, smart_layout.py, audio_cuts.py  reframing, captions, cuts, loops
whatif_render.py, gizmo_*.py, game_hud.py        AI-generated explainer formats
youtube_api.py, niche_research.py, hook_*.py     analytics & research
run_*.py                                         per-project clip specs (examples of using the pipeline)
studio/backend   FastAPI: project store, job queue, AI tools, analytics
studio/web       React + Remotion editor UI and renderer
studio/mcp       MCP server for AI control of the editor
assets/          fonts, sound effects (music is not included — see assets/music/SOURCES.txt)
```

Media, models, transcripts, API keys and OAuth tokens are intentionally not part of the repository.

---

## Roadmap

The goal is to grow this into an **all-round AI clip studio** — one app that goes from an idea or a long
video to a finished, published short:

- **Animation generation** — animated scenes, motion graphics and explainer animations generated from a script.
- **Better voices** — more natural, expressive TTS, voice styles per character, and voice consistency across videos.
- **Character generation** — consistent recurring characters (look + voice) that can star in a series.
- **Smarter editing** — automatic hook selection from retention data, automatic loop detection, smarter B-roll matching.
- **Templates & styles** — shareable edit templates, more caption/transition packs.
- **Publishing** — multi-platform upload and scheduling from inside the app, with the experiment tracker closing the loop.
- **Packaging** — a one-click installer instead of the current dev setup.

---

## Notes

- Clips of other creators' content should only be published with permission (e.g. official clipping
  campaigns) and with proper credit.
- Music in `assets/music` comes from the YouTube Audio Library and is not redistributed here.
