# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Syncr (Mimic) is an AI dubbing studio built for HackIllinois 2026. Upload a video and every actor speaks a target language in their own cloned voice with lip-sync-aware pacing. Full-stack app: React/Vite frontend + FastAPI/Python backend, orchestrated via Modal for GPU-parallel processing.

## Architecture

```
Video → Extract Audio (ffmpeg)
     → Diarize Speakers (pyannote.audio via Modal GPU)
     → Transcribe (OpenAI Whisper)
     → Translate (GPT-4o, timing-aware prompts)
     → Clone Voices + Synthesize (ElevenLabs, parallel per speaker)
     → Composite back onto video (ffmpeg)
     → Output: dubbed video
```

**Backend (FastAPI):** 3 endpoints — `POST /dub` (upload + start job), `GET /status/{job_id}` (poll progress), `GET /download/{job_id}` (get result). Jobs tracked in-memory by UUID. Pipeline runs as background task via `orchestrator.run_pipeline()`.

**Frontend (React/Vite):** Single-page `App.jsx`. Upload dropzone → language picker → polls `/status` every 2s → side-by-side video player (original vs dubbed) → download.

**Pipeline modules** (in `backend/pipeline/`): `extract.py`, `diarize.py`, `transcribe.py`, `translate.py`, `synthesize.py`, `composite.py`, `modal_jobs.py`. Each step updates job progress (5% → 15% → 30% → 45% → 60% → 85% → 100%).

## Commands

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate              # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173
```

### Test pipeline
```bash
cd backend
modal run pipeline/modal_jobs.py   # test Modal diarization
```

### Spike tests (run in order)
1. **Diarization quality** — extract audio + diarize locally, check speaker labels
2. **Voice cloning** — clone a speaker via ElevenLabs, synthesize a test segment
3. **End-to-end** — 30-second clip through full pipeline via API

See README.md for exact spike test commands.

## Environment Variables

Required in `backend/.env`:
- `OPENAI_API_KEY` — GPT-4o translation + Whisper transcription
- `ELEVENLABS_API_KEY` — voice cloning and TTS
- `HF_TOKEN` — HuggingFace (pyannote model access)

Modal secrets created separately via `modal secret create mimic-secrets`.

## Key Conventions

- **Async throughout** — backend uses `async/await` with `aiohttp` and `aiofiles` for concurrent API calls
- **Segment data as dicts** — `{speaker, start, end, audio_path, text, translated_text, dubbed_audio_path}`
- **Parallel per-speaker processing** — voice cloning and synthesis run concurrently per speaker via Modal containers
- **Temp files** — uploads in `tmp/uploads/`, outputs in `tmp/outputs/`, intermediate segments in `tmp/segments/`
- **Frontend env** — API URL via `import.meta.env.VITE_API_URL`, defaults to `http://localhost:8000`

## External Dependencies

- **ffmpeg** must be installed locally
- **HuggingFace model access** required: accept terms for `pyannote/speaker-diarization-3.1` and `pyannote/segmentation-3.0`
- **Modal** for GPU container orchestration (`modal setup` + `modal token new`)
