# Syncr — Technical Specification

## 1. System Overview

Syncr is a movie-scale AI dubbing pipeline. Upload a video of any length — from a 30-second clip to a full-length film — and every actor speaks the target language in their own cloned voice with lip-sync-aware pacing. The pipeline runs on Modal (serverless GPU cloud) using a 3-level container hierarchy that scales to 40–60+ containers for feature-length content.

```
┌──────────┐       POST /dub       ┌─────────────┐     .remote()     ┌──────────────────────────────────────┐
│ Frontend │ ───────────────────→  │ FastAPI      │ ────────────────→ │ Modal Cloud                          │
│ (React)  │ ←── GET /status ────  │ (local)      │ ←── return ─────  │                                      │
│ Pipeline │ polls every 1.5s      │              │                   │ ┌──────────────────────────────────┐ │
│ Dashboard│                       └─────────────┘                   │ │ Coordinator (CPU)                │ │
└──────────┘                                                         │ │ chunk → dispatch → match speakers│ │
                                                                     │ │ → synthesize → quality → merge   │ │
                                                                     │ └──────────┬───────────────────────┘ │
                                                                     │            │ .spawn() per chunk       │
                                                                     │  ┌─────────▼──────────────────────┐  │
                                                                     │  │ process_chunk (GPU, N parallel) │  │
                                                                     │  │ extract → diarize → transcribe  │  │
                                                                     │  │ → translate (per chunk)         │  │
                                                                     │  └─────────┬──────────────────────┘  │
                                                                     │            │ .map() per segment       │
                                                                     │  ┌─────────▼──────────────────────┐  │
                                                                     │  │ WhisperTranscriber (GPU, T4)   │  │
                                                                     │  │ Self-hosted faster-whisper      │  │
                                                                     │  └────────────────────────────────┘  │
                                                                     │                                      │
                                                                     │  ┌────────────────────────────────┐  │
                                                                     │  │ synthesize_speaker (CPU, 1/spk)│  │
                                                                     │  │ ElevenLabs clone + TTS         │  │
                                                                     │  └────────────────────────────────┘  │
                                                                     └──────────────────────────────────────┘
```

**Data flow:** Video file → FastAPI saves to disk → orchestrator calls `coordinator.remote()` in a background thread → coordinator extracts 44.1kHz audio for Demucs and spawns `separate_audio` in parallel → chunks the video at scene boundaries → spawns `process_chunk` GPU containers in parallel (one per chunk) → each chunk runs extract → diarize → transcribe (self-hosted Whisper via `.map()`) → context-aware translate → coordinator matches speakers across chunks via embedding cosine similarity → spawns `synthesize_speaker` CPU containers (one per global speaker) → center-trims Demucs accompaniment → merges all chunks with crossfades, volume matching, and background audio into final video (h264 + AAC) → return bytes → FastAPI saves to disk and serves download.

**Container topology** (10-minute video, 2 chunks, 3 speakers, 20 segments):

| Container | Count | Type | Purpose |
|---|---|---|---|
| coordinator | 1 | CPU | Chunk + dispatch + merge |
| process_chunk | 2 | T4 GPU | Per-chunk pipeline |
| WhisperTranscriber | up to 4 | T4 GPU | Parallel segment transcription |
| separate_audio | 1 | T4 GPU | Demucs source separation |
| synthesize_speaker | 3 | CPU | Per-speaker voice synthesis |
| **Total** | **~11** | **4–6 GPU + 4–5 CPU** | |

For a full movie (20 chunks, 5 speakers, 200 segments): **40–60+ containers**.

---

## 2. Data Models

### `models.py`

```python
from pydantic import BaseModel
from typing import Optional

class JobStatus(BaseModel):
    job_id: str
    status: str                             # queued | running | done | error
    step: str                               # human-readable current step
    progress: int                           # 0-100
    error: Optional[str] = None
    output_url: Optional[str] = None
    # Chunk tracking
    total_chunks: Optional[int] = None
    completed_chunks: Optional[int] = None
    # Pipeline metrics
    speakers_found: Optional[int] = None
    segments_found: Optional[int] = None
    containers_active: Optional[int] = None
    containers_total: Optional[int] = None
    # Live transcript preview
    transcript_preview: Optional[list[dict]] = None
    # Per-step timing data
    step_timings: Optional[dict] = None

class DubRequest(BaseModel):
    target_language: str = "es"
```

**Segment dict shape** (used throughout the pipeline):
```python
{
    "speaker": "SPEAKER_00",        # local label (per-chunk) or global (post-matching)
    "start": 0.5,                   # seconds (chunk-relative in process_chunk, absolute after coordinator)
    "end": 3.2,
    "audio_path": "/tmp/seg.wav",   # local to container (not cross-container)
    "text": "Hello, how are you?",  # original transcription
    "translated_text": "Hola, ¿cómo estás?",
    "audio_bytes": b"...",          # raw audio for cross-container transfer
    "embedding": [0.1, 0.2, ...],   # speaker embedding for cross-chunk matching
    "dubbed_audio_path": "/tmp/dub.mp3",  # after synthesis
    "dubbed_audio_bytes": b"...",   # cross-container synthesis result
}
```

Not all keys are present at every stage. Keys are added progressively as data flows through the pipeline.

---

## 3. API Contract

### `POST /dub`

Upload a video and start a dubbing job.

| Field | Type | Location | Required | Default |
|---|---|---|---|---|
| `file` | video file | form-data | yes | — |
| `target_language` | string | form-data | no | `"es"` |

**Response** `200`:
```json
{ "job_id": "550e8400-e29b-41d4-a716-446655440000" }
```

**Supported `target_language` values:** `es`, `fr`, `de`, `ar`, `zh`, `ja`, `pt`, `hi`, `ko`, `it`

### `GET /status/{job_id}`

Poll job progress. Returns rich pipeline state for the frontend dashboard.

**Response** `200`:
```json
{
  "job_id": "550e8400-...",
  "status": "running",
  "step": "Diarizing speakers (chunk 2/4)...",
  "progress": 35,
  "error": null,
  "output_url": null,
  "total_chunks": 4,
  "completed_chunks": 1,
  "speakers_found": 3,
  "segments_found": 20,
  "containers_active": 3,
  "containers_total": 10,
  "transcript_preview": [
    {"speaker": "SPEAKER_00", "start": 0.5, "text": "Hello", "translated_text": "Hola"}
  ],
  "step_timings": {"diarize": 12.3, "transcribe": 8.1}
}
```

`status` transitions: `queued` → `running` → `done` | `error`

### `GET /download/{job_id}`

Returns the dubbed MP4 file. Only available when `status === "done"`.

---

## 4. Modal Setup

### App and Image Definitions

Three image tiers, all with `.add_local_python_source("pipeline")` for module access in remote containers:

```python
# pipeline/modal_app.py
import modal

app = modal.App("syncr")

cpu_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install("openai", "aiohttp", "aiofiles", "python-dotenv", "pydub")
    .add_local_python_source("pipeline")
)

gpu_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "torch==2.2.0", "torchaudio==2.2.0", "pyannote.audio",
        "openai", "aiohttp", "aiofiles", "python-dotenv", "pydub", "numpy",
    )
    .add_local_python_source("pipeline")
)

whisper_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install("faster-whisper", "pydub", "ctranslate2")
    .add_local_python_source("pipeline")
)
```

**Why `.add_local_python_source("pipeline")`:** Every remote container needs access to the pipeline modules (`extract.py`, `diarize.py`, etc.). Without this, `from pipeline.xxx import ...` fails with `ModuleNotFoundError`.

**Why pinned torch versions:** Unpinned `torch` on GPU images may install CPU-only builds. `torch==2.2.0` guarantees CUDA support.

**Why `ctranslate2`:** `faster-whisper` depends on it for GPU inference. Explicitly installing it ensures the CUDA runtime is bundled.

### Secrets

```python
@app.function(
    image=cpu_image,
    secrets=[modal.Secret.from_name("mimic-secrets")],
)
```

Create via: `modal secret create mimic-secrets HF_TOKEN=... OPENAI_API_KEY=... ELEVENLABS_API_KEY=...`

### Progress Tracking via `modal.Dict`

All containers write real-time progress to a shared `modal.Dict`:

```python
progress_dict = modal.Dict.from_name("syncr-progress", create_if_missing=True)
progress_dict[job_id] = {
    "status": "running",
    "step": "Diarizing speakers (chunk 2/4)...",
    "progress": 35,
    "total_chunks": 4,
    "completed_chunks": 1,
    "containers_active": 3,
}
```

The local orchestrator polls this Dict every 1 second and maps it to `JobStatus` fields.

---

## 5. Pipeline Functions

### 5.1 Scene-Aware Chunking (`chunk.py`)

**Purpose:** Split long videos into ~5-minute chunks at scene boundaries for parallel processing.

```python
def detect_scenes(video_path: str) -> list[dict]:
    """Uses ffmpeg scene filter (gt(scene,0.3)) + showinfo. Returns scene boundaries."""

def split_video(video_path, scenes, max_chunk_duration=300.0, work_dir="/tmp") -> list[dict]:
    """Groups scenes into chunks, applies 2s overlap, extracts via ffmpeg."""
```

**Scene detection:** Runs `ffmpeg -filter:v "select='gt(scene,0.3)',showinfo"` and parses `pts_time` values from stderr. If no scene changes detected, falls back to a single chunk.

**Overlap:** Each chunk extends 2 seconds into its neighbors to preserve speaker continuity. Duplicate segments at boundaries are filtered out during merge.

**Extraction:** Uses `-ss` before `-i` for fast seeking, then re-encodes with `libx264 -preset fast -crf 22` for frame-accurate boundaries (stream copy can drift on non-keyframe boundaries).

### 5.2 Audio Extraction (`extract.py`)

```python
def extract_audio(input_video_path: str, job_id: str, work_dir: str = "/tmp") -> str:
    """ffmpeg: extract audio as WAV, 16kHz mono, 16-bit PCM."""
```

Output format required by both pyannote (diarization) and Whisper (transcription).

### 5.3 Speaker Diarization (`diarize.py`)

```python
def diarize_speakers(audio_path: str, work_dir: str = "/tmp") -> list[dict]:
    """pyannote/speaker-diarization-3.1 on GPU. Returns segments with speaker embeddings."""
```

**Speaker embeddings:** After diarization, extracts a representative embedding per speaker using `pyannote/wespeaker-voxceleb-resnet34-LM` (from the longest segment per speaker). Embeddings are used by the coordinator for cross-chunk speaker matching.

**Graceful degradation:** Embedding extraction is wrapped in try/except. If it fails, segments still work — just without cross-chunk speaker matching capability.

### 5.4 Self-Hosted Whisper Transcription (`WhisperTranscriber` in `modal_jobs.py`)

```python
@app.cls(image=whisper_image, gpu="T4", concurrency_limit=4)
class WhisperTranscriber:
    @modal.enter()
    def load_model(self):
        self.model = WhisperModel("medium", device="cuda", compute_type="float16")

    @modal.method()
    def transcribe(self, audio_bytes: bytes) -> str:
```

**Key design:** Uses `@modal.enter()` to load the model once when the container starts, then reuses it across all `.transcribe()` calls. Called via `.map()` from `process_chunk` for parallel transcription across segments.

**Why self-hosted instead of API:** Eliminates per-minute API costs, runs on our own GPU containers, gives us more control, and looks much more impressive for the Modal prize.

### 5.5 Context-Aware Translation (`translate.py`)

Two modes:
- `translate_segments()` — sequential, per-segment (for local testing)
- `translate_segments_with_context()` — groups 5 segments into batches with surrounding dialogue context

```python
def translate_segments_with_context(segments, target_language) -> list[dict]:
    """GPT-4o with dialogue context. Format: [SPEAKER, duration]: text"""
```

**Why context-aware:** Single-segment translation misses conversational flow. Batching nearby segments lets GPT understand who's responding to whom, producing dramatically better translations for dialogue.

**Response parsing:** Expects `[SPEAKER]: translation` format. Parser only strips prefix if line starts with `[` (bracket format) or `SPEAKER` to avoid accidentally truncating translated text that contains colons.

### 5.6 Voice Synthesis (`synthesize_speaker` in `modal_jobs.py`)

```python
@app.function(image=cpu_image, concurrency_limit=6, secrets=[...])
def synthesize_speaker(speaker, segments, sample_bytes, job_id) -> list[dict]:
    """Clone one voice via ElevenLabs, synthesize all segments, delete voice."""
```

**One container per global speaker.** After cross-chunk speaker matching, the coordinator spawns one synthesis container per unique speaker (not per chunk). Each container: clones the voice → synthesizes all segments → deletes the clone (free tier: 3 voice limit).

**Bytes, not paths:** Containers have separate filesystems. Voice samples go in as `sample_bytes`, dubbed audio comes back as `dubbed_audio_bytes`.

### 5.7 Quality Verification (`quality.py`)

```python
def verify_segments(segments) -> tuple[list[dict], list[dict]]:
    """Returns (passed, failed) with failure_reason on failed segments."""

def build_strict_retranslation_prompt(segment, target_language) -> str:
    """Builds a stricter prompt asking for 80% duration translation."""
```

**Checks per segment:**
- **Timing:** Dubbed audio > 1.5x the original time slot → `too_long`
- **Overlap:** Dubbed audio (after speedup) would collide with next segment → `overlap`
- **Silence:** dBFS < -35 → `mostly_silence`
- **Minimum length:** < 0.3 seconds → `too_short`

**Note:** The quality retry loop was removed in Sprint 9 because it created new voice clones per retry, causing voice inconsistency. Timing issues are now handled by `merge.py` using atempo speedup. The verification functions remain available but are not called in the main pipeline flow.

### 5.8 Demucs Source Separation (`separate_audio` in `modal_jobs.py`)

```python
@app.function(image=gpu_image, gpu="T4", timeout=600, secrets=[...])
def separate_audio(audio_bytes: bytes) -> bytes:
    """Run Demucs htdemucs to remove vocals, return accompaniment (music/effects/ambient)."""
```

**Purpose:** Removes original vocal track from the video's audio, preserving music, sound effects, and ambient sounds. The accompaniment is used as the background track under the dubbed voices.

**Implementation:** Uses `python -m demucs --two-stems=vocals` CLI subprocess (not `demucs.api`, which only exists on GitHub main, not PyPI 4.0.1). Runs on T4 GPU in parallel with chunk processing.

### 5.9 Chunk Merging (`merge.py`)

```python
def merge_chunks(original_video, chunk_results, job_id, output_dir, bg_audio_bytes=None) -> str:
    """Merge dubbed audio from all chunks onto original video with background audio."""
```

**Steps:**
1. Filter overlap duplicates at chunk boundaries
2. Center-trim Demucs accompaniment (remove symmetric padding from both start and end)
3. Build full-length AudioSegment from Demucs background (or silence if unavailable)
4. Overlay each dubbed segment at absolute timestamp with 30ms fade-in/fade-out crossfades
5. Match each dubbed segment's volume (dBFS) to the original audio at that timestamp
6. Apply atempo speedup for segments that exceed their time slot
7. Encode final video with `libx264 -preset fast -crf 22` + AAC audio + `-movflags +faststart`

### 5.10 Video Composition (`composite.py`)

Provides `_build_atempo_chain()` for speedup and `composite_video()` for single-chunk compositing. Used by `merge.py` for the atempo chain.

---

## 6. Container Orchestration

### 3-Level Hierarchy (`modal_jobs.py`)

**Level 1 — `coordinator` (CPU, timeout=900s):**
1. Save input video to temp dir
2. Extract 44.1kHz audio for Demucs, spawn `separate_audio.spawn()` in parallel
3. Call `detect_scenes()` + `split_video()` (fast, just ffmpeg)
4. Spawn `process_chunk.spawn()` per chunk (parallel GPU containers)
5. Collect results as they complete, update progress
6. Match speakers across chunks via embedding cosine similarity
7. Spawn `synthesize_speaker.spawn()` per global speaker (parallel CPU containers)
8. Collect synthesis results
9. Center-trim Demucs accompaniment, call `merge_chunks()` for final video (crossfades, volume matching, h264)
10. Return final video as bytes

**Level 2 — `process_chunk` (GPU T4, timeout=600s):**
1. Extract audio from chunk
2. Diarize speakers (pyannote on GPU)
3. Transcribe via `WhisperTranscriber.transcribe.map()` (parallel GPU)
4. Translate with context (`translate_segments_with_context`)
5. Return segments with text, translated_text, audio_bytes, embeddings

**Level 2 — `WhisperTranscriber` (GPU T4, `@app.cls`):**
- Model loaded once via `@modal.enter()`, reused across calls
- Called via `.map()` for parallel segment transcription
- `concurrency_limit=4` — up to 4 transcriber containers

**Level 2 — `separate_audio` (GPU T4):**
- Runs Demucs htdemucs via CLI subprocess (`python -m demucs --two-stems=vocals`)
- Spawned in parallel with chunk processing (doesn't wait for chunks)
- Returns accompaniment audio bytes (music + effects + ambient, no vocals)

**Level 3 — `synthesize_speaker` (CPU, concurrency_limit=6):**
- One container per speaker
- Clone voice → synthesize all segments → delete voice
- Returns `dubbed_audio_bytes` per segment

### Cross-Chunk Speaker Matching

After all chunks complete, the coordinator has speaker embeddings from every segment across all chunks. Speaker matching:

1. Collect one representative embedding per `(chunk_idx, local_speaker)` pair
2. Greedy clustering: for each embedding, compute cosine similarity against existing clusters
3. If similarity > 0.85, assign to that cluster (same person)
4. Otherwise, create a new global speaker cluster
5. Map all segments to global speaker IDs

This ensures that "SPEAKER_00" in chunk 1 and "SPEAKER_01" in chunk 3 are recognized as the same person if their voice embeddings match.

### Progress Tracking

All containers write to `modal.Dict.from_name("syncr-progress")`. The `_update_progress()` helper merges updates:

```python
_update_progress(job_id,
    step="Diarizing speakers (chunk 2/4)...",
    progress=35,
    completed_chunks=1,
    containers_active=3,
)
```

The local orchestrator (`orchestrator.py`) runs `_poll_modal_progress()` in a background thread that reads this Dict every 1 second and maps it to `JobStatus` fields.

The Dict reference is lazily initialized (not at module import time) to avoid crashing when Modal is not authenticated during local development.

---

## 7. Local Orchestrator (`orchestrator.py`)

```python
def run_pipeline(job_id, input_path, target_language, jobs, output_dir):
    """Sync function — FastAPI BackgroundTasks runs it in a threadpool."""
```

**Key design:** This is a regular (non-async) function. FastAPI's `BackgroundTasks.add_task()` runs sync functions in a threadpool, so the blocking `coordinator.remote()` call doesn't freeze the event loop. This means `/status` polling continues to work while the pipeline runs.

**Flow:**
1. Read video bytes from disk
2. Start `_poll_modal_progress` thread (polls `modal.Dict` every 1s)
3. Call `coordinator.remote(video_bytes, target_language, job_id)` — blocks until pipeline completes
4. Stop progress polling thread
5. Save output bytes to disk
6. Update job status to `done`

**Error handling:** `stop_event` is initialized before the try block so it's always available in the except handler.

---

## 8. Frontend (`App.jsx`)

### Pipeline Dashboard

The frontend replaces a simple progress bar with a rich pipeline visualization:

**Pipeline nodes:** Horizontal row of step icons (Extract → Diarize → Transcribe → Translate → Synthesize → Quality → Composite) with per-step status derived from `status.step` keywords. Active steps pulse with a glow animation.

**Metric pills:** Live counters — chunks completed, speakers identified, segments processed, containers active, quality checks passed.

**Transcript panel:** Scrollable panel showing speaker-color-coded transcript building up as chunks complete. Each speaker gets a consistent color.

### Synced Video Player

Two `<video>` elements in a grid with shared controls:
- Left: original video (muted by default)
- Right: dubbed video (plays audio)
- Shared play/pause button and scrubber
- Drift correction: if videos desync by > 0.3s, the lagging video seeks to match

### Animations (`index.css` + `tailwind.config.js`)

Custom keyframes registered as Tailwind utilities:
- `animate-fade-in` — elements entering view
- `animate-slide-up` — dashboard components mounting
- `animate-glow` — active pipeline step indicator
- `animate-shake` — error state

---

## 9. File Structure

```
syncr/
├── CLAUDE.md                    # Source of truth for Claude sessions
├── README.md
├── TODO.md                      # Setup, spike tests, demo prep checklist
├── setup.sh                     # Project setup script
├── backend/
│   ├── .env                     # API keys (git-ignored)
│   ├── .env.example
│   ├── requirements.txt
│   ├── main.py                  # FastAPI server (3 endpoints)
│   ├── models.py                # Pydantic models (JobStatus with chunk tracking)
│   ├── spike1_diarize.py        # Spike test: diarization quality
│   ├── spike2_voice.py          # Spike test: ElevenLabs voice cloning
│   ├── spike3_e2e.py            # Spike test: end-to-end pipeline
│   └── pipeline/
│       ├── __init__.py
│       ├── modal_app.py         # Modal App + 3 image definitions
│       ├── modal_jobs.py        # 3-level container hierarchy + Demucs separation
│       ├── orchestrator.py      # Local orchestrator (real progress via modal.Dict)
│       ├── chunk.py             # Scene-aware video chunking
│       ├── extract.py           # ffmpeg audio extraction
│       ├── diarize.py           # pyannote diarization + speaker embeddings
│       ├── transcribe.py        # Whisper fallback (pipeline uses self-hosted WhisperTranscriber)
│       ├── translate.py         # GPT-4o context-aware translation (sequential + batched)
│       ├── synthesize.py        # ElevenLabs local helper (pipeline uses synthesize_speaker)
│       ├── composite.py         # ffmpeg composition + atempo helper
│       ├── merge.py             # Multi-chunk merge + Demucs bg + crossfades + volume matching
│       └── quality.py           # Segment verification (retry loop removed)
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js       # Custom animation utilities
│   ├── postcss.config.js        # Autoprefixer
│   └── src/
│       ├── main.jsx
│       ├── index.css            # Keyframe animations (sonar, wave-bar, shimmer, etc.)
│       └── App.jsx              # Pipeline dashboard + synced player + sonar bg
├── docs/
│   ├── CONCEPT.md               # Original project concept
│   ├── TECH_SPEC.md             # This file
│   ├── MODAL_NOTES.md           # Modal platform reference
│   ├── SPENDING_LIMITS.md       # API cost guardrails
│   ├── FRONTEND.md              # Frontend design philosophy + component inventory
│   ├── BRAND.md                 # Logo specifications + brand guidelines
│   └── BACKGROUND_IDEAS.md      # Background animation concepts
└── tmp/                         # git-ignored, runtime files
    ├── uploads/
    └── outputs/
```

---

## 10. `requirements.txt`

**Local requirements:**
```
fastapi>=0.104.0
uvicorn>=0.24.0
python-multipart>=0.0.9
python-dotenv>=1.0.0
aiohttp>=3.9.0
aiofiles>=23.2.0
openai>=1.6.0
pydub>=0.25.1
modal>=0.64.0
```

Heavy deps (`pyannote.audio`, `torch`, `torchaudio`, `faster-whisper`) are NOT in local requirements — they're installed inside the Modal image definitions. This keeps local install fast.

---

## 11. Error Handling

| Step | Likely failure | Handling |
|---|---|---|
| chunk | ffmpeg scene detection fails | Falls back to single chunk |
| extract | Corrupt/unsupported video | CalledProcessError → job error |
| diarize | Bad HF_TOKEN or model terms | RuntimeError → job error |
| diarize (embeddings) | Embedding model unavailable | try/except, degrades gracefully |
| transcribe | Whisper model load failure | Container error → job error |
| translate | OpenAI API rate limit | APIError → job error |
| synthesize | ElevenLabs char limit / API key | ClientError → job error |
| quality | All segments fail verification | Accept with speedup after 2 retries |
| merge | ffmpeg/ffprobe failure | CalledProcessError → job error |
| Modal | Timeout, OOM, no GPU | Container timeout → job error |

The orchestrator wraps the entire pipeline in try/except and updates job status to `"error"` with the exception message. The `stop_event` for progress polling is initialized before the try block to prevent `UnboundLocalError` in the except handler.

---

## 12. Key Design Decisions

1. **Scene-aware chunking over fixed-time splitting:** Splitting mid-scene can cut a speaker mid-sentence, producing broken transcriptions. Scene boundary detection ensures clean cuts.

2. **Self-hosted Whisper over API:** Eliminates per-minute costs, runs on our own GPU containers, enables parallel transcription via `.map()`, and demonstrates real GPU inference for the Modal prize.

3. **Context-aware translation over per-segment:** Single-segment translation misses conversational flow. Batching 5 segments with speaker labels and durations produces dramatically better dialogue translations.

4. **Global speaker matching over per-chunk synthesis:** Without matching, the same actor would get a different cloned voice in each chunk. Embedding cosine similarity (threshold > 0.85) identifies the same speaker across chunks.

5. **Single clone per speaker over retry loop:** The quality retry loop was removed because each retry created a new voice clone, causing voice inconsistency across segments. Timing issues are handled by merge.py atempo speedup, and 30ms crossfades eliminate hard pops at segment boundaries.

6. **Demucs source separation over silence/original audio:** Building from silence loses ambient atmosphere. Keeping original audio has vocal bleed. Demucs separates vocals from accompaniment, preserving music/effects/ambient as the background track under dubbed voices.

7. **Sync function orchestrator over async:** `coordinator.remote()` is a blocking Modal call. Running it inside an `async def` would freeze FastAPI's event loop. Using a sync `def` lets FastAPI run it in a threadpool automatically.

8. **Lazy `modal.Dict` initialization over module-level:** Creating the Dict reference at import time crashes if Modal isn't authenticated. Lazy init defers it to first use (inside a Modal container where auth is guaranteed).

9. **Bytes over paths for cross-container data:** Modal containers have separate filesystems. Voice samples and dubbed audio must be passed as bytes, not file paths.
