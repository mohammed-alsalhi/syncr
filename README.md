# Syncr — AI Dubbing Studio

> Upload any video. Every actor speaks your target language — in their own voice — in minutes.

Built for HackIllinois 2026. Powered by Modal, ElevenLabs, OpenAI, and pyannote.audio.

---

## Architecture

```
Video → Scene-Aware Chunking (ffmpeg scene detection, ~5-min chunks)
     → [parallel per chunk on Modal GPU]
         → Extract Audio (ffmpeg, 16kHz mono)
         → Diarize Speakers (pyannote, GPU + speaker embeddings)
         → Transcribe (self-hosted faster-whisper on T4 GPU)
         → Translate (GPT-4o, context-aware with dialogue batching)
     → Cross-Chunk Speaker Matching (cosine similarity on embeddings)
     → Demucs Source Separation (remove vocals, keep music/effects)
     → Clone Voices + Synthesize (ElevenLabs, parallel per speaker)
     → Merge + Composite (crossfades, volume matching, h264 encode)
```

### 3-Level Modal Container Hierarchy
- **Level 1 — Coordinator (CPU):** Chunks video, dispatches work, matches speakers, merges final output
- **Level 2 — process_chunk (T4 GPU) × N:** Per-chunk diarize → transcribe → translate
- **Level 2 — WhisperTranscriber (T4 GPU):** Self-hosted faster-whisper "medium", parallel via `.map()`
- **Level 2 — separate_audio (T4 GPU):** Demucs htdemucs source separation
- **Level 3 — synthesize_speaker (CPU) × N:** Per-speaker voice clone + TTS via ElevenLabs

---

## Setup

### Prerequisites
- Python 3.11+
- Node 18+
- ffmpeg installed locally (`brew install ffmpeg` or `apt install ffmpeg`)

### 1. Install backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Set environment variables

```bash
cp .env.example .env
# Fill in: OPENAI_API_KEY, ELEVENLABS_API_KEY, HF_TOKEN
```

### 3. Set up Modal

```bash
# Authenticate
modal setup              # opens browser for auth
modal token new          # confirm token is saved

# Redeem HackIllinois credits ($250)
# Go to: https://modal.com/credits
# Use code: VVN-YQS-E55

# Create secrets in Modal (so GPU containers can access your keys)
modal secret create mimic-secrets \
  HF_TOKEN=hf_... \
  OPENAI_API_KEY=sk-... \
  ELEVENLABS_API_KEY=...
```

### 4. Request HuggingFace model access

Visit these pages and click "Accept":
- https://huggingface.co/pyannote/speaker-diarization-3.1
- https://huggingface.co/pyannote/segmentation-3.0

(Approval is usually instant)

### 5. Run the backend

```bash
cd backend
source venv/bin/activate        # Windows: venv\Scripts\activate
uvicorn main:app --reload --port 8000
```

### 6. Install and run frontend

```bash
cd frontend
npm install
npm run dev              # starts at http://localhost:5173
```

---

## Spike tests (do these first, in order)

### Spike 1: Diarization quality
```bash
cd backend
source venv/bin/activate
python -c "
from pipeline.extract import extract_audio
from pipeline.diarize import diarize_speakers
audio = extract_audio('tmp/test.mp4', 'spike1', 'tmp')
segs = diarize_speakers(audio, 'tmp')
for s in segs: print(s)
"
```
Pass: distinct speaker labels, reasonable timestamps
Fail: all one speaker, or too fragmented (tune pyannote min_duration_on)

### Spike 2: ElevenLabs voice cloning
```bash
cd backend
source venv/bin/activate
python -c "
import asyncio, aiohttp, os
from dotenv import load_dotenv
load_dotenv()

from pipeline.synthesize import _clone_voice, _synthesize_segment

async def test():
    api_key = os.environ['ELEVENLABS_API_KEY']
    async with aiohttp.ClientSession() as session:
        speaker, voice_id = await _clone_voice(session, api_key, 'SPEAKER_00', 'tmp/segments/seg_0000_SPEAKER_00.wav', 'test')
        print('Voice ID:', voice_id)
        seg = {'speaker': 'SPEAKER_00', 'translated_text': 'Hello, this is a test.', 'start': 0, 'end': 2}
        result = await _synthesize_segment(session, api_key, seg, voice_id, 0, 'tmp/dubbed')
        print('Synthesized:', result)

asyncio.run(test())
"
```
Pass: audio file created, sounds like the speaker
Fail: check ELEVENLABS_API_KEY and that sample is >5 seconds

### Spike 3: End-to-end on a 30-second clip
Pick a short clip with 2 speakers. Run the full pipeline via the API.
Target: output video where voices match original speakers.

---

## Test Modal deployment

```bash
cd backend
modal run pipeline/modal_jobs.py
```

---

## Prize applications

- **Modal track** — Best AI Inference
- **General** — Best Social Impact, Best UI/UX Design
- **Sponsor** — OpenAI API, Cloudflare, Supermemory
- **MLH** — Best Use of ElevenLabs, Best .Tech Domain, Best Use of DigitalOcean

---

## Demo script (for judges)

> "Dubbing costs studios $20,000 per minute and takes weeks. The result sounds robotic.
> We built Mimic. Give it any video and every actor speaks another language — in their own voice."

[Play original clip → Play dubbed clip]

---

## Docs

- [docs/TECH_SPEC.md](docs/TECH_SPEC.md) — Full technical specification
- [docs/MODAL_NOTES.md](docs/MODAL_NOTES.md) — Modal platform reference
- [docs/SPENDING_LIMITS.md](docs/SPENDING_LIMITS.md) — API cost guardrails
- [docs/CONCEPT.md](docs/CONCEPT.md) — Original project concept
- [docs/FRONTEND.md](docs/FRONTEND.md) — Frontend design philosophy and component inventory
- [docs/BRAND.md](docs/BRAND.md) — Logo specifications and brand guidelines
- [docs/BACKGROUND_IDEAS.md](docs/BACKGROUND_IDEAS.md) — Background animation concepts
