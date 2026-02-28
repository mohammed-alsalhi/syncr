# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Syncr (Mimic) is an AI dubbing studio built for HackIllinois 2026. Upload a video and every actor speaks a target language in their own cloned voice with lip-sync-aware pacing. Full-stack app: React/Vite frontend + FastAPI/Python backend, orchestrated via Modal for GPU-parallel processing.

## Repository Structure

```
syncr/
├── backend/
│   ├── main.py                 # FastAPI server (3 endpoints)
│   ├── models.py               # Pydantic models (JobStatus, DubRequest)
│   ├── requirements.txt
│   ├── .env.example
│   └── pipeline/
│       ├── modal_app.py        # Modal App + Image definitions
│       ├── modal_jobs.py       # Modal functions (orchestrator + per-speaker synth)
│       ├── orchestrator.py     # Local orchestrator (calls Modal, simulates progress)
│       ├── extract.py          # Step 1: ffmpeg audio extraction
│       ├── diarize.py          # Step 2: pyannote speaker diarization (GPU)
│       ├── transcribe.py       # Step 3: Whisper transcription
│       ├── translate.py        # Step 4: GPT-4o-mini translation
│       ├── synthesize.py       # Step 5: ElevenLabs voice cloning + TTS
│       └── composite.py        # Step 6: ffmpeg video composition
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── src/
│       ├── main.jsx
│       ├── index.css
│       └── App.jsx             # Single-page React UI
├── docs/
│   ├── CONCEPT.md              # Original project concept
│   ├── TECH_SPEC.md            # Detailed technical specification
│   ├── MODAL_NOTES.md          # Modal platform reference
│   └── SPENDING_LIMITS.md      # API cost guardrails
└── README.md
```

## Architecture

One GPU container on Modal runs the sequential pipeline steps (extract → diarize → transcribe → translate), then spawns parallel CPU containers for per-speaker voice synthesis. Results composited back in the GPU container.

**Backend (FastAPI):** 3 endpoints — `POST /dub`, `GET /status/{job_id}`, `GET /download/{job_id}`. Jobs tracked in-memory. Orchestrator calls Modal via `.remote()` and simulates progress locally.

**Frontend (React/Vite):** Upload dropzone → language picker → polls `/status` every 2s → before/after video player → download.

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

### Test pipeline on Modal
```bash
cd backend
modal run pipeline/modal_jobs.py
```

## Environment Variables

Required in `backend/.env` (copy from `backend/.env.example`):
- `OPENAI_API_KEY` — GPT-4o-mini translation + Whisper transcription
- `ELEVENLABS_API_KEY` — voice cloning and TTS
- `HF_TOKEN` — HuggingFace (pyannote model access)

Modal secrets: `modal secret create mimic-secrets HF_TOKEN=... OPENAI_API_KEY=... ELEVENLABS_API_KEY=...`

## Key Conventions

- **Segment data as dicts** — `{speaker, start, end, audio_path, text, translated_text, dubbed_audio_path}`
- **Modal hybrid architecture** — GPU container for sequential steps, `.spawn()` for parallel per-speaker synthesis
- **Bytes over paths for cross-container data** — synth containers receive/return audio as bytes since they have separate filesystems
- **Timing-aware translation** — GPT prompt includes segment duration to constrain translation length
- **Voice cleanup** — delete ElevenLabs cloned voices after each job (free tier: 3 voice limit)
- **Frontend env** — API URL via `import.meta.env.VITE_API_URL`, defaults to `http://localhost:8000`

## External Dependencies

- **ffmpeg** must be installed locally and in Modal images
- **HuggingFace model access** required: accept terms for `pyannote/speaker-diarization-3.1` and `pyannote/segmentation-3.0`
- **Modal** for GPU container orchestration (`modal setup` + `modal token new`)
