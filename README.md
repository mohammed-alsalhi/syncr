# 🎭 Syncr — AI Dubbing Studio

> Upload any video. Every actor speaks your target language — in their own voice — in minutes.

Built for HackIllinois 2026. Powered by Modal, ElevenLabs, OpenAI, and pyannote.audio.

---

## Architecture

```
Video → Extract Audio → Diarize Speakers (Modal/pyannote)
     → Transcribe (Whisper) → Translate (GPT-4o)
     → Clone Voices + Synthesize (ElevenLabs, parallel)
     → Composite back onto video (ffmpeg)
```

---

## Setup

### Prerequisites
- Python 3.11+
- Node 18+
- ffmpeg installed locally (`brew install ffmpeg` or `apt install ffmpeg`)

### 1. Clone and install backend

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
# Install and authenticate
pip install modal
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
source venv/bin/activate
uvicorn main:app --reload --port 8000
```

### 6. Install and run frontend

```bash
cd frontend
npm install
npm run dev              # starts at http://localhost:5173
```

---

## Test the pipeline (before running the full server)

```bash
# Test Modal diarization directly
cd backend
modal run pipeline/modal_jobs.py

# Or run diarization locally (no Modal needed, slower)
python -c "
from pipeline.extract import extract_audio
from pipeline.diarize import diarize_speakers
audio = extract_audio('your_test_video.mp4', 'test')
segments = diarize_speakers(audio)
print(segments[:3])
"
```

---

## Spike tests (do these first, in order)

### Spike 1: Diarization quality
```bash
# Put a video in tmp/ and run:
python -c "
from pipeline.extract import extract_audio
from pipeline.diarize import _diarize_local
audio = extract_audio('tmp/test.mp4', 'spike1')
segs = _diarize_local(audio)
for s in segs: print(s)
"
```
✅ Pass: distinct speaker labels, reasonable timestamps
❌ Fail: all one speaker, or too fragmented (tune pyannote min_duration_on)

### Spike 2: ElevenLabs voice cloning
```bash
python -c "
import asyncio, aiohttp, aiofiles, os
from dotenv import load_dotenv
load_dotenv()

async def test():
    from pipeline.synthesize import _clone_voice, _synthesize_segment
    async with aiohttp.ClientSession() as session:
        speaker, voice_id = await _clone_voice(session, 'SPEAKER_00', 'tmp/segments/seg_0000_SPEAKER_00.wav', 'test')
        print('Voice ID:', voice_id)
        seg = {'speaker': 'SPEAKER_00', 'translated_text': 'Hello, this is a test.', 'start': 0, 'end': 2, 'dubbed_audio_path': None}
        result = await _synthesize_segment(session, seg, voice_id, 0)
        print('Synthesized:', result)

asyncio.run(test())
"
```
✅ Pass: audio file created, sounds like the speaker
❌ Fail: check ELEVENLABS_API_KEY and that sample is >5 seconds

### Spike 3: End-to-end on a 30-second clip
Pick a short clip with 2 speakers. Run the full pipeline via the API.
Target: output video where voices match original speakers.

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
