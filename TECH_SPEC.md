# Syncr — Technical Specification

## 1. System Overview

Syncr is a video dubbing pipeline that takes an input video and produces a dubbed version where every speaker's voice is cloned and speaks the target language. The entire compute-heavy pipeline runs on Modal (serverless GPU cloud). A local FastAPI server handles uploads, job tracking, and serves results.

```
┌──────────┐       POST /dub       ┌─────────────┐     .remote()     ┌──────────────────────┐
│ Frontend │ ───────────────────→  │ FastAPI      │ ────────────────→ │ Modal Cloud          │
│ (React)  │ ←── GET /status ────  │ (local)      │ ←── return ─────  │                      │
│          │ ←── GET /download ──  │              │                   │ extract (CPU)        │
└──────────┘                       └─────────────┘                   │ diarize (GPU)        │
                                                                     │ transcribe (CPU)     │
                                                                     │ translate (CPU)      │
                                                                     │ synthesize (CPU)     │
                                                                     │ composite (CPU)      │
                                                                     └──────────────────────┘
```

**Data flow:** Video file → FastAPI saves to disk → orchestrator calls Modal function → Modal runs 6-step pipeline → output video saved to disk → FastAPI serves download.

---

## 2. Data Models

### `models.py`

```python
from pydantic import BaseModel
from typing import Optional

class JobStatus(BaseModel):
    job_id: str
    status: str           # "queued" | "running" | "done" | "error"
    step: str             # human-readable current step
    progress: int         # 0-100
    error: Optional[str] = None
    output_url: Optional[str] = None

class SpeakerSegment(BaseModel):
    """A single continuous speech segment from one speaker."""
    speaker: str          # "SPEAKER_00", "SPEAKER_01", etc.
    start: float          # start time in seconds
    end: float            # end time in seconds
    audio_path: str       # path to extracted audio clip for this segment

class TranscribedSegment(SpeakerSegment):
    text: str             # transcribed text (original language)

class TranslatedSegment(TranscribedSegment):
    translated_text: str  # translated text (target language)

class SynthesizedSegment(BaseModel):
    """A segment with dubbed audio ready for compositing."""
    speaker: str
    start: float
    end: float
    dubbed_audio_path: str  # path to synthesized audio clip
```

> **Implementation note:** The orchestrator currently passes dicts between steps. These models define the contract. Each pipeline function should accept and return lists of these dicts (matching the model fields). Pydantic validation is optional during hackathon — the models serve as documentation of the shape.

---

## 3. API Contract

### `POST /dub`

Upload a video and start a dubbing job.

| Field             | Type       | Location  | Required | Default |
|-------------------|------------|-----------|----------|---------|
| `file`            | video file | form-data | yes      | —       |
| `target_language` | string     | form-data | no       | `"es"`  |

**Response** `200`:
```json
{ "job_id": "550e8400-e29b-41d4-a716-446655440000" }
```

**Supported `target_language` values:** `es`, `fr`, `de`, `ar`, `zh`, `ja`, `pt`, `hi`, `ko`, `it`

### `GET /status/{job_id}`

Poll job progress.

**Response** `200`:
```json
{
  "job_id": "550e8400-...",
  "status": "running",
  "step": "Cloning voices and synthesizing speech...",
  "progress": 60,
  "error": null,
  "output_url": null
}
```

`status` transitions: `queued` → `running` → `done` | `error`

### `GET /download/{job_id}`

Returns the dubbed MP4 file. Only available when `status === "done"`.

**Response** `200`: `video/mp4` file
**Response** `200`: `{"error": "Output not ready"}` if not done

---

## 4. Modal Setup

### App and Image Definitions

All Modal functions share one `modal.App`. Define two images — one for GPU work (diarization), one for CPU work (everything else).

```python
# pipeline/modal_app.py

import modal

app = modal.App("syncr")

# CPU image — lightweight, used by most steps
cpu_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "openai",
        "aiohttp",
        "aiofiles",
        "python-dotenv",
        "pydub",
    )
)

# GPU image — heavy, only used by diarization
gpu_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "torch",
        "torchaudio",
        "pyannote.audio",
    )
)
```

### Secrets

All Modal functions that call external APIs need the `mimic-secrets` secret:

```python
@app.function(
    image=cpu_image,
    secrets=[modal.Secret.from_name("mimic-secrets")],
    timeout=300,
    concurrency_limit=3,
)
```

### Volume for File Transfer

Modal containers don't share a filesystem with your local machine. Use a `modal.Volume` to pass files between steps and back to the local server.

```python
vol = modal.Volume.from_name("syncr-workspace", create_if_missing=True)

@app.function(
    image=cpu_image,
    volumes={"/workspace": vol},
    timeout=300,
)
def extract_audio(input_path: str, job_id: str) -> str:
    # input_path is relative to /workspace
    # writes output to /workspace/tmp/audio/{job_id}.wav
    ...
```

**File transfer flow:**
1. FastAPI saves uploaded video to local disk
2. Before calling Modal, upload the file to the volume (or use `modal.Volume.put_file()`)
3. Each Modal function reads/writes inside `/workspace/`
4. After pipeline completes, download the output from the volume back to local disk

**Alternative (simpler for hackathon):** Run the entire pipeline as a single Modal function that receives the video bytes and returns the dubbed video bytes. This avoids volume complexity:

```python
@app.function(image=gpu_image, gpu="T4", timeout=600, concurrency_limit=2,
              secrets=[modal.Secret.from_name("mimic-secrets")])
def run_full_pipeline(video_bytes: bytes, target_language: str) -> bytes:
    """Receive video bytes, return dubbed video bytes. Everything runs in one container."""
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, "input.mp4")
        with open(input_path, "wb") as f:
            f.write(video_bytes)

        audio_path = _extract_audio(input_path, tmpdir)
        segments = _diarize_speakers(audio_path, tmpdir)
        segments = _transcribe_segments(segments)
        segments = _translate_segments(segments, target_language)
        segments = _synthesize_speakers(segments, tmpdir)
        output_path = _composite_video(input_path, segments, tmpdir)

        with open(output_path, "rb") as f:
            return f.read()
```

> **Recommendation for hackathon:** Start with the single-function approach. It eliminates file transfer complexity. You only need one container with the GPU image. Refactor to multi-function only if you need per-step parallelism.

---

## 5. Pipeline Functions — Full Specifications

### 5.1 `extract_audio`

**Purpose:** Extract the audio track from the input video as a WAV file.

```python
def extract_audio(input_video_path: str, job_id: str, work_dir: str = "/tmp") -> str:
    """
    Extract audio from video using ffmpeg.

    Args:
        input_video_path: Absolute path to input video file (mp4, mov, avi)
        job_id:           Unique job identifier (used for output filename)
        work_dir:         Directory to write output files

    Returns:
        Absolute path to extracted audio file (WAV, 16kHz mono)

    Raises:
        subprocess.CalledProcessError: If ffmpeg fails (corrupt video, unsupported codec)
    """
```

**Implementation:**
```python
import subprocess
import os

def extract_audio(input_video_path: str, job_id: str, work_dir: str = "/tmp") -> str:
    output_path = os.path.join(work_dir, f"{job_id}_audio.wav")

    subprocess.run([
        "ffmpeg", "-y",
        "-i", input_video_path,
        "-vn",                    # no video
        "-acodec", "pcm_s16le",   # 16-bit PCM
        "-ar", "16000",           # 16kHz (required by Whisper and pyannote)
        "-ac", "1",               # mono
        output_path,
    ], check=True, capture_output=True)

    return output_path
```

**Output format:** WAV, 16kHz, mono, 16-bit PCM. This format is required by both pyannote (diarization) and Whisper (transcription).

**Edge cases:**
- Video with no audio track → ffmpeg returns error, raise exception
- Very large video → ffmpeg streams, no memory issue, but may be slow

---

### 5.2 `diarize_speakers`

**Purpose:** Identify who speaks when. Split the full audio into per-speaker, per-segment audio clips.

```python
def diarize_speakers(audio_path: str, work_dir: str = "/tmp") -> list[dict]:
    """
    Run speaker diarization on audio and split into per-segment clips.

    Args:
        audio_path: Path to WAV audio file (16kHz mono)
        work_dir:   Directory to write segment audio files

    Returns:
        List of segment dicts, each containing:
        {
            "speaker": "SPEAKER_00",    # speaker label
            "start": 0.5,               # start time in seconds
            "end": 3.2,                 # end time in seconds
            "audio_path": "/tmp/seg_0000_SPEAKER_00.wav"
        }

        Segments are sorted by start time.

    Raises:
        RuntimeError: If pyannote model fails to load (bad HF_TOKEN or no model access)
    """
```

**Implementation:**
```python
import os
import torch
from pyannote.audio import Pipeline
from pydub import AudioSegment

def diarize_speakers(audio_path: str, work_dir: str = "/tmp") -> list[dict]:
    hf_token = os.environ["HF_TOKEN"]

    # Load pyannote diarization pipeline
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=hf_token,
    )

    # Move to GPU if available
    if torch.cuda.is_available():
        pipeline.to(torch.device("cuda"))

    # Run diarization
    diarization = pipeline(audio_path)

    # Load full audio for slicing
    full_audio = AudioSegment.from_wav(audio_path)

    segments = []
    seg_dir = os.path.join(work_dir, "segments")
    os.makedirs(seg_dir, exist_ok=True)

    for i, (turn, _, speaker) in enumerate(diarization.itertracks(yield_label=True)):
        start = turn.start
        end = turn.end

        # Skip very short segments (< 0.5s) — usually noise
        if end - start < 0.5:
            continue

        # Extract audio clip for this segment
        clip = full_audio[int(start * 1000):int(end * 1000)]
        seg_path = os.path.join(seg_dir, f"seg_{i:04d}_{speaker}.wav")
        clip.export(seg_path, format="wav")

        segments.append({
            "speaker": speaker,
            "start": round(start, 3),
            "end": round(end, 3),
            "audio_path": seg_path,
        })

    # Sort by start time
    segments.sort(key=lambda s: s["start"])
    return segments
```

**This is the only GPU-dependent step.** pyannote runs a neural network for voice activity detection and speaker embedding. On a T4 GPU, diarization of a 30-second clip takes ~10-30 seconds. Without GPU it may take 2-5x longer.

**Tuning parameters:**
- `min_duration_on` in pyannote controls minimum segment length. If segments are too fragmented, increase this.
- The 0.5s minimum filter above prevents noise segments.

**Model access prerequisite:** User must accept terms at:
- https://huggingface.co/pyannote/speaker-diarization-3.1
- https://huggingface.co/pyannote/segmentation-3.0

---

### 5.3 `transcribe_segments`

**Purpose:** Convert each audio segment's speech to text using OpenAI Whisper API.

```python
def transcribe_segments(segments: list[dict]) -> list[dict]:
    """
    Transcribe each segment's audio to text using Whisper.

    Args:
        segments: List of dicts with keys: speaker, start, end, audio_path

    Returns:
        Same list with added "text" field:
        {
            "speaker": "SPEAKER_00",
            "start": 0.5,
            "end": 3.2,
            "audio_path": "/tmp/seg_0000_SPEAKER_00.wav",
            "text": "Hello, how are you today?"
        }

    Raises:
        openai.APIError: If Whisper API call fails
    """
```

**Implementation:**
```python
import os
from openai import OpenAI

def transcribe_segments(segments: list[dict]) -> list[dict]:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    result = []

    for seg in segments:
        with open(seg["audio_path"], "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text",
            )

        result.append({
            **seg,
            "text": transcript.strip(),
        })

    return result
```

**Cost:** Whisper API charges $0.006/minute of audio. A 30-second clip ≈ $0.003.

**Edge cases:**
- Silent segment → Whisper returns empty string. Keep the segment (it will produce empty translation, which is fine).
- Non-English audio → Whisper auto-detects language. No `language` param needed for transcription.

**Optimization (optional):** Batch segments from the same speaker into one longer audio file to reduce API call overhead. Not needed for hackathon.

---

### 5.4 `translate_segments`

**Purpose:** Translate each segment's text into the target language, with timing awareness.

```python
def translate_segments(segments: list[dict], target_language: str) -> list[dict]:
    """
    Translate transcribed text to target language.

    Args:
        segments:        List of dicts with keys: speaker, start, end, audio_path, text
        target_language: ISO 639-1 language code (e.g., "es", "fr", "de")

    Returns:
        Same list with added "translated_text" field:
        {
            ...
            "text": "Hello, how are you today?",
            "translated_text": "Hola, ¿cómo estás hoy?"
        }

    Raises:
        openai.APIError: If GPT API call fails
    """
```

**Implementation:**
```python
import os
from openai import OpenAI

LANGUAGE_NAMES = {
    "es": "Spanish", "fr": "French", "de": "German", "ar": "Arabic",
    "zh": "Mandarin Chinese", "ja": "Japanese", "pt": "Portuguese",
    "hi": "Hindi", "ko": "Korean", "it": "Italian",
}

def translate_segments(segments: list[dict], target_language: str) -> list[dict]:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    lang_name = LANGUAGE_NAMES.get(target_language, target_language)
    result = []

    for seg in segments:
        if not seg["text"].strip():
            result.append({**seg, "translated_text": ""})
            continue

        duration = seg["end"] - seg["start"]

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a professional dubbing translator. "
                        f"Translate the following dialogue line into {lang_name}. "
                        f"The original line is spoken in {duration:.1f} seconds. "
                        f"Your translation must be speakable in approximately the same duration. "
                        f"Prefer shorter, natural phrasing over literal accuracy. "
                        f"Return ONLY the translated text, nothing else."
                    ),
                },
                {"role": "user", "content": seg["text"]},
            ],
            max_tokens=500,
            temperature=0.3,
        )

        translated = response.choices[0].message.content.strip()
        result.append({**seg, "translated_text": translated})

    return result
```

**Key design decision: timing-aware prompt.** The system prompt tells GPT the segment duration and asks for a translation that fits the same time window. This is the "lip-sync-aware pacing" from the concept doc. It's approximate but effective — shorter translations prevent dubbed audio from overrunning the original timing.

**Why `gpt-4o-mini`:** 10x cheaper than `gpt-4o`, translation quality is comparable for common languages. Upgrade to `gpt-4o` only if translation quality is noticeably bad.

**Batching optimization (optional):** Send all segments for one speaker in a single API call with numbered lines. Parse the numbered response. Reduces latency and cost for many short segments.

---

### 5.5 `synthesize_speakers`

**Purpose:** Clone each speaker's voice using ElevenLabs, then synthesize dubbed audio for every segment in that voice.

```python
async def synthesize_speakers(segments: list[dict], job_id: str, work_dir: str = "/tmp") -> list[dict]:
    """
    Clone voices and synthesize dubbed audio for all segments.
    Processes speakers in parallel.

    Args:
        segments: List of dicts with keys: speaker, start, end, audio_path, text, translated_text
        job_id:   Job identifier (used for voice clone naming)
        work_dir: Directory to write synthesized audio files

    Returns:
        List of dicts with added "dubbed_audio_path" field:
        {
            "speaker": "SPEAKER_00",
            "start": 0.5,
            "end": 3.2,
            "dubbed_audio_path": "/tmp/dubbed/dub_0000_SPEAKER_00.wav"
        }

    Raises:
        aiohttp.ClientError: If ElevenLabs API call fails
    """
```

**Implementation:**
```python
import os
import asyncio
import aiohttp
import aiofiles

ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"

async def synthesize_speakers(segments: list[dict], job_id: str, work_dir: str = "/tmp") -> list[dict]:
    api_key = os.environ["ELEVENLABS_API_KEY"]
    dub_dir = os.path.join(work_dir, "dubbed")
    os.makedirs(dub_dir, exist_ok=True)

    # Group segments by speaker
    speakers = {}
    for seg in segments:
        speakers.setdefault(seg["speaker"], []).append(seg)

    # Find longest audio clip per speaker (best sample for cloning)
    speaker_samples = {}
    for spk, segs in speakers.items():
        best = max(segs, key=lambda s: s["end"] - s["start"])
        speaker_samples[spk] = best["audio_path"]

    async with aiohttp.ClientSession() as session:
        # Step A: Clone each speaker's voice (parallel)
        voice_ids = {}
        clone_tasks = [
            _clone_voice(session, api_key, spk, sample_path, job_id)
            for spk, sample_path in speaker_samples.items()
        ]
        clone_results = await asyncio.gather(*clone_tasks)
        for spk, voice_id in clone_results:
            voice_ids[spk] = voice_id

        # Step B: Synthesize each segment (parallel, grouped by speaker)
        synth_tasks = []
        for i, seg in enumerate(segments):
            if not seg.get("translated_text", "").strip():
                continue
            synth_tasks.append(
                _synthesize_segment(session, api_key, seg, voice_ids[seg["speaker"]], i, dub_dir)
            )
        synth_results = await asyncio.gather(*synth_tasks)

        # Step C: Clean up cloned voices (free tier has voice limit)
        for voice_id in voice_ids.values():
            await _delete_voice(session, api_key, voice_id)

    return synth_results


async def _clone_voice(
    session: aiohttp.ClientSession,
    api_key: str,
    speaker: str,
    sample_path: str,
    job_id: str,
) -> tuple[str, str]:
    """
    Clone a voice from an audio sample.

    Returns:
        Tuple of (speaker_label, voice_id)
    """
    url = f"{ELEVENLABS_BASE}/voices/add"
    headers = {"xi-api-key": api_key}

    async with aiofiles.open(sample_path, "rb") as f:
        sample_bytes = await f.read()

    form = aiohttp.FormData()
    form.add_field("name", f"{job_id}_{speaker}")
    form.add_field("files", sample_bytes, filename=f"{speaker}.wav", content_type="audio/wav")

    async with session.post(url, headers=headers, data=form) as resp:
        resp.raise_for_status()
        data = await resp.json()
        return (speaker, data["voice_id"])


async def _synthesize_segment(
    session: aiohttp.ClientSession,
    api_key: str,
    segment: dict,
    voice_id: str,
    index: int,
    output_dir: str,
) -> dict:
    """
    Synthesize one segment of dubbed audio.

    Returns:
        Segment dict with dubbed_audio_path added.
    """
    url = f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": segment["translated_text"],
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }

    async with session.post(url, headers=headers, json=payload) as resp:
        resp.raise_for_status()
        audio_bytes = await resp.read()

    output_path = os.path.join(output_dir, f"dub_{index:04d}_{segment['speaker']}.mp3")
    async with aiofiles.open(output_path, "wb") as f:
        await f.write(audio_bytes)

    return {
        "speaker": segment["speaker"],
        "start": segment["start"],
        "end": segment["end"],
        "dubbed_audio_path": output_path,
    }


async def _delete_voice(session: aiohttp.ClientSession, api_key: str, voice_id: str):
    """Delete a cloned voice to stay within free tier limits."""
    url = f"{ELEVENLABS_BASE}/voices/{voice_id}"
    headers = {"xi-api-key": api_key}
    async with session.delete(url, headers=headers) as resp:
        pass  # best-effort cleanup, don't fail the pipeline
```

**Critical details:**
- **Clone once per speaker, not per segment.** Group segments by speaker, clone voice once, reuse for all that speaker's segments.
- **Use the longest audio clip as the clone sample.** Longer samples (>5 seconds) produce better voice clones.
- **Delete voices after the job.** ElevenLabs free tier limits you to 3 custom voices. Cleanup prevents hitting the limit.
- **`eleven_multilingual_v2`** is the model that supports non-English TTS. Do not use `eleven_monolingual_v1`.
- **Output is MP3** (ElevenLabs default). ffmpeg can handle this in the composite step.

**Parallel execution:** `asyncio.gather` runs all clone operations in parallel, then all synthesis operations in parallel. This is the main speed optimization.

---

### 5.6 `composite_video`

**Purpose:** Replace the original audio track with the dubbed audio segments, producing the final video.

```python
def composite_video(
    input_video: str,
    synthesized_segments: list[dict],
    job_id: str,
    output_dir: str,
) -> str:
    """
    Composite dubbed audio segments back onto the original video.

    Args:
        input_video:           Path to original video file
        synthesized_segments:  List of dicts with keys: speaker, start, end, dubbed_audio_path
        job_id:                Job identifier (used for output filename)
        output_dir:            Directory to write final video

    Returns:
        Path to dubbed video file (MP4)

    Raises:
        subprocess.CalledProcessError: If ffmpeg fails
    """
```

**Implementation:**
```python
import subprocess
import os
from pydub import AudioSegment

def composite_video(
    input_video: str,
    synthesized_segments: list[dict],
    job_id: str,
    output_dir: str,
) -> str:
    os.makedirs(output_dir, exist_ok=True)

    # Step 1: Get original video duration
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", input_video],
        capture_output=True, text=True, check=True,
    )
    total_duration_ms = int(float(probe.stdout.strip()) * 1000)

    # Step 2: Build a full-length silent audio track
    mixed = AudioSegment.silent(duration=total_duration_ms)

    # Step 3: Overlay each dubbed segment at its timestamp
    for seg in synthesized_segments:
        dubbed_clip = AudioSegment.from_file(seg["dubbed_audio_path"])
        position_ms = int(seg["start"] * 1000)
        target_duration_ms = int((seg["end"] - seg["start"]) * 1000)

        # If dubbed audio is longer than the original slot, speed it up
        if len(dubbed_clip) > target_duration_ms and target_duration_ms > 0:
            speed_factor = len(dubbed_clip) / target_duration_ms
            # Use ffmpeg to change speed without pitch shift
            sped_up_path = seg["dubbed_audio_path"] + ".speed.wav"
            subprocess.run([
                "ffmpeg", "-y",
                "-i", seg["dubbed_audio_path"],
                "-filter:a", f"atempo={min(speed_factor, 2.0)}",  # atempo max 2.0
                sped_up_path,
            ], check=True, capture_output=True)
            dubbed_clip = AudioSegment.from_file(sped_up_path)

        # Truncate if still too long
        dubbed_clip = dubbed_clip[:target_duration_ms]

        mixed = mixed.overlay(dubbed_clip, position=position_ms)

    # Step 4: Export mixed audio
    mixed_audio_path = os.path.join(output_dir, f"{job_id}_mixed.wav")
    mixed.export(mixed_audio_path, format="wav")

    # Step 5: Combine original video (no audio) with new audio
    output_path = os.path.join(output_dir, f"{job_id}_dubbed.mp4")
    subprocess.run([
        "ffmpeg", "-y",
        "-i", input_video,
        "-i", mixed_audio_path,
        "-c:v", "copy",         # keep original video codec (fast, no re-encoding)
        "-map", "0:v:0",        # video from first input
        "-map", "1:a:0",        # audio from second input
        "-shortest",
        output_path,
    ], check=True, capture_output=True)

    return output_path
```

**Key decisions:**
- **Silent base track:** Start with silence, overlay dubbed clips at their timestamps. Gaps between segments are naturally silent.
- **Speed adjustment:** If the dubbed audio is longer than the original segment's time window, speed it up using ffmpeg's `atempo` filter (max 2x). This is the practical lip-sync timing solution.
- **Video passthrough:** `-c:v copy` copies the video stream without re-encoding. This is fast and lossless.
- **Output format:** MP4 with original video + new audio.

---

## 6. Orchestrator — Modal Integration

The orchestrator ties everything together. For the hackathon, run the entire pipeline as a single Modal function.

### `pipeline/modal_jobs.py`

```python
import modal
from modal_app import app, gpu_image, vol

@app.function(
    image=gpu_image,
    gpu="T4",
    timeout=600,
    concurrency_limit=2,
    secrets=[modal.Secret.from_name("mimic-secrets")],
)
def run_pipeline_remote(video_bytes: bytes, target_language: str) -> bytes:
    """
    Full pipeline in one container. Receives video bytes, returns dubbed video bytes.
    GPU needed for pyannote diarization.
    """
    import tempfile, os

    with tempfile.TemporaryDirectory() as tmpdir:
        # Save input
        input_path = os.path.join(tmpdir, "input.mp4")
        with open(input_path, "wb") as f:
            f.write(video_bytes)

        # Run pipeline
        from extract import extract_audio
        from diarize import diarize_speakers
        from transcribe import transcribe_segments
        from translate import translate_segments
        from synthesize import synthesize_speakers
        from composite import composite_video

        import asyncio

        audio_path = extract_audio(input_path, "job", tmpdir)
        segments = diarize_speakers(audio_path, tmpdir)
        segments = transcribe_segments(segments)
        segments = translate_segments(segments, target_language)
        segments = asyncio.run(synthesize_speakers(segments, "job", tmpdir))
        output_path = composite_video(input_path, segments, "job", os.path.join(tmpdir, "output"))

        # Return output bytes
        with open(output_path, "rb") as f:
            return f.read()
```

### Updated `pipeline/orchestrator.py`

```python
import asyncio
from pathlib import Path
from models import JobStatus

def update_job(jobs, job_id, status, step, progress, error=None):
    jobs[job_id] = JobStatus(
        job_id=job_id, status=status, step=step,
        progress=progress, error=error,
        output_url=f"/download/{job_id}" if status == "done" else None,
    )

async def run_pipeline(job_id, input_path, target_language, jobs, output_dir):
    try:
        update_job(jobs, job_id, "running", "Uploading to cloud...", 5)

        # Read video file
        with open(input_path, "rb") as f:
            video_bytes = f.read()

        update_job(jobs, job_id, "running", "Processing on cloud (this takes a few minutes)...", 15)

        # Call Modal — entire pipeline runs remotely
        from pipeline.modal_jobs import run_pipeline_remote
        output_bytes = run_pipeline_remote.remote(video_bytes, target_language)

        # Save output locally
        update_job(jobs, job_id, "running", "Saving output...", 90)
        output_path = Path(output_dir) / f"{job_id}_dubbed.mp4"
        with open(output_path, "wb") as f:
            f.write(output_bytes)

        update_job(jobs, job_id, "done", "Complete!", 100)

    except Exception as e:
        update_job(jobs, job_id, "error", "Pipeline failed", 0, error=str(e))
        raise
```

> **Trade-off:** Running everything in one Modal function means you lose granular progress updates (the frontend will see "Processing on cloud..." for the whole duration). This is acceptable for a hackathon demo. To add granular progress, you'd need a webhook or polling mechanism from Modal back to your server, which adds complexity.

---

## 7. File Structure (Target)

```
syncr/
├── CLAUDE.md
├── CONCEPT.md
├── README.md
├── TECH_SPEC.md
├── MODAL_NOTES.md
├── SPENDING_LIMITS.md
├── backend/
│   ├── .env                    # API keys (git-ignored)
│   ├── .env.example            # template
│   ├── requirements.txt
│   ├── main.py                 # FastAPI server
│   ├── models.py               # Pydantic models (JobStatus, etc.)
│   └── pipeline/
│       ├── __init__.py
│       ├── modal_app.py        # Modal App, Image, Volume definitions
│       ├── modal_jobs.py       # Modal function: run_pipeline_remote
│       ├── orchestrator.py     # Local orchestrator (calls Modal)
│       ├── extract.py          # ffmpeg audio extraction
│       ├── diarize.py          # pyannote speaker diarization
│       ├── transcribe.py       # Whisper transcription
│       ├── translate.py        # GPT-4o-mini translation
│       ├── synthesize.py       # ElevenLabs voice cloning + TTS
│       └── composite.py        # ffmpeg video composition
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       └── App.jsx
└── tmp/                        # git-ignored, runtime files
    ├── uploads/
    └── outputs/
```

---

## 8. `requirements.txt`

```
fastapi>=0.104.0
uvicorn>=0.24.0
python-dotenv>=1.0.0
aiohttp>=3.9.0
aiofiles>=23.2.0
openai>=1.6.0
pydub>=0.25.1
modal>=0.64.0
pyannote.audio>=3.1.0
torch>=2.1.0
torchaudio>=2.1.0
```

> **Note:** `pyannote.audio` and `torch` are only needed inside the Modal container (they're in the image definition). If you want a lighter local install, split into `requirements.txt` (local) and let the Modal image handle the heavy deps.

---

## 9. Error Handling Strategy

Each pipeline step can fail independently. The orchestrator wraps the entire pipeline in try/except and updates the job status to `"error"` with the exception message.

| Step         | Likely failure                          | User-facing message              |
|--------------|----------------------------------------|----------------------------------|
| extract      | Corrupt/unsupported video format        | "Could not extract audio from video" |
| diarize      | Bad HF_TOKEN or model not accepted      | "Speaker identification failed"  |
| transcribe   | OpenAI API key invalid or rate limited  | "Transcription failed"           |
| translate    | OpenAI API key invalid or rate limited  | "Translation failed"             |
| synthesize   | ElevenLabs API key invalid or char limit | "Voice synthesis failed"        |
| composite    | ffmpeg error or disk full               | "Video composition failed"       |
| Modal        | Timeout, OOM, or no GPU available       | "Cloud processing failed"        |

For the hackathon, raw exception messages in the error field are fine. The frontend already displays `status.error`.
