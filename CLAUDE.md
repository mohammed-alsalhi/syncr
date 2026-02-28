# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Syncr (Mimic) is an AI dubbing studio built for HackIllinois 2026. Upload a video — even a full-length movie — and every actor speaks a target language in their own cloned voice with timing-aware pacing. Full-stack app: React/Vite frontend + FastAPI/Python backend, orchestrated via Modal for GPU-parallel processing.

The system scales to feature-length content via intelligent scene-aware chunking, parallel multi-container processing, self-hosted GPU inference (Whisper), and a self-healing quality feedback loop.

## Repository Structure

```
syncr/
├── backend/
│   ├── main.py                 # FastAPI server (3 endpoints)
│   ├── models.py               # Pydantic models (JobStatus with pipeline metrics)
│   ├── requirements.txt
│   ├── .env.example
│   └── pipeline/
│       ├── modal_app.py        # Modal App + Image definitions (cpu, gpu, whisper)
│       ├── modal_jobs.py       # Modal functions: coordinator → process_chunk → WhisperTranscriber → synthesize_speaker
│       ├── orchestrator.py     # Local orchestrator (calls Modal, polls real progress via modal.Dict)
│       ├── chunk.py            # Scene-aware video chunking (ffmpeg scene detection + splitting)
│       ├── extract.py          # Step 1: ffmpeg audio extraction
│       ├── diarize.py          # Step 2: pyannote speaker diarization (GPU) + speaker embeddings
│       ├── transcribe.py       # Local-only Whisper fallback (pipeline uses self-hosted WhisperTranscriber on Modal)
│       ├── translate.py        # Step 4: GPT-4o-mini context-aware translation
│       ├── synthesize.py       # Step 5: ElevenLabs voice cloning + TTS (local fallback)
│       ├── quality.py          # Quality verification + retry loop for synthesized segments
│       ├── merge.py            # Chunk merging + final video composite
│       └── composite.py        # Per-chunk ffmpeg video composition (building block used by merge.py)
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── src/
│       ├── main.jsx
│       ├── index.css           # Tailwind + custom keyframe animations
│       └── App.jsx             # Pipeline dashboard UI with synced video player
├── docs/
│   ├── CONCEPT.md              # Original project concept
│   ├── TECH_SPEC.md            # Detailed technical specification
│   ├── MODAL_NOTES.md          # Modal platform reference
│   └── SPENDING_LIMITS.md      # API cost guardrails
└── README.md
```

## Architecture

### 3-Level Modal Container Hierarchy

```
Local FastAPI                     Modal Cloud
─────────────                     ───────────────────────────────────────────
POST /dub ──→ orchestrator.py ──→ Level 1: coordinator (CPU)
              polls modal.Dict       │  chunks video via scene detection
              for real progress      │  spawns process_chunk per chunk
                                     │  matches speakers across chunks
                                     │  dispatches synthesis per global speaker
                                     │  runs quality verification + retries
                                     │  merges chunks into final video
                                     │
                                     ├──→ Level 2: process_chunk (T4 GPU) × N chunks
                                     │       extract audio (ffmpeg)
                                     │       diarize speakers (pyannote + embeddings)
                                     │       transcribe (WhisperTranscriber.map())
                                     │       translate (GPT-4o-mini, context-aware)
                                     │
                                     ├──→ Level 2: WhisperTranscriber (T4 GPU) × up to 4
                                     │       self-hosted faster-whisper "medium"
                                     │       model loaded once via @modal.enter()
                                     │       parallel segment transcription via .map()
                                     │
                                     └──→ Level 3: synthesize_speaker (CPU) × N speakers
                                             clone voice via ElevenLabs
                                             synthesize all segments for that speaker
                                             delete cloned voice after completion
```

**Container counts scale with content length:**
- 30-second clip: ~8-10 containers
- 10-minute video: ~15-20 containers
- Full movie: 40-60+ containers

**Backend (FastAPI):** 3 endpoints — `POST /dub`, `GET /status/{job_id}`, `GET /download/{job_id}`. Jobs tracked in-memory. Orchestrator calls Modal coordinator via `.remote()` and polls `modal.Dict` for real progress.

**Frontend (React/Vite):** Upload dropzone → language picker → pipeline dashboard with chunk map, step visualization, live metrics, transcript preview → side-by-side synced video player → download.

## Commands

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
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
- `OPENAI_API_KEY` — GPT-4o-mini translation (Whisper transcription now self-hosted on Modal)
- `ELEVENLABS_API_KEY` — voice cloning and TTS
- `HF_TOKEN` — HuggingFace (pyannote model access)

Modal secrets: `modal secret create mimic-secrets HF_TOKEN=... OPENAI_API_KEY=... ELEVENLABS_API_KEY=...`

## Key Conventions

- **Segment data as dicts** — `{speaker, start, end, audio_path, text, translated_text, dubbed_audio_path, embedding}`
- **3-level Modal hierarchy** — coordinator (CPU) → process_chunk (GPU) → synthesize_speaker (CPU), with WhisperTranscriber (GPU) for parallel transcription
- **Scene-aware chunking** — videos split at scene boundaries into ~5-min chunks, processed in parallel across GPU containers
- **Bytes over paths for cross-container data** — all containers receive/return audio as bytes since they have separate filesystems
- **Self-hosted Whisper** — faster-whisper "medium" on T4 GPU via `@app.cls` with `@modal.enter()` for model caching
- **Speaker consistency** — pyannote speaker embeddings compared across chunks via cosine similarity to assign global speaker IDs
- **Quality feedback loop** — after synthesis, verify timing/overlap/silence, re-translate and re-synthesize failed segments (max 2 retries)
- **Context-aware translation** — GPT prompt includes segment duration + surrounding dialogue context for natural phrasing
- **Real progress tracking** — `modal.Dict` written by all containers, polled by local orchestrator every 1s
- **Voice cleanup** — delete ElevenLabs cloned voices after each job (free tier: 3 voice limit)
- **Frontend env** — API URL via `import.meta.env.VITE_API_URL`, defaults to `http://localhost:8000`

## External Dependencies

- **ffmpeg** must be installed locally and in Modal images
- **HuggingFace model access** required: accept terms for `pyannote/speaker-diarization-3.1` and `pyannote/segmentation-3.0`
- **Modal** for GPU container orchestration (`modal setup` + `modal token new`)
- **faster-whisper** runs inside Modal containers only (not installed locally)

## Migration Status

Tracking the rebuild from simple sequential pipeline to movie-scale intelligent architecture.

- [x] Sprint 0: Update CLAUDE.md with target architecture
- [x] Sprint 1: Scene-aware chunking + self-hosted Whisper on Modal GPU
- [x] Sprint 2: Real progress tracking via modal.Dict
- [x] Sprint 3: Quality feedback loop (verify + retry)
- [x] Sprint 4: Speaker consistency across chunks (embeddings + matching)
- [x] Sprint 5: Frontend pipeline dashboard + synced video player
- [ ] Sprint 6: Integration testing + demo prep
