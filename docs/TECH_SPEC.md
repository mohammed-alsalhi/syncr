# Syncr — Technical Specification

## 1. System Overview

Syncr is a video dubbing pipeline that takes an input video and produces a dubbed version where every speaker's voice is cloned and speaks the target language. The entire compute-heavy pipeline runs on Modal (serverless GPU cloud). A local FastAPI server handles uploads, job tracking, and serves results.

```
┌──────────┐       POST /dub       ┌─────────────┐     .remote()     ┌──────────────────────────────┐
│ Frontend │ ───────────────────→  │ FastAPI      │ ────────────────→ │ Modal Cloud                  │
│ (React)  │ ←── GET /status ────  │ (local)      │ ←── return ─────  │                              │
│          │ ←── GET /download ──  │              │                   │ ┌────────────────────────┐   │
└──────────┘                       └─────────────┘                   │ │ Orchestrator container │   │
                                                                     │ │ (GPU — T4)             │   │
                                                                     │ │ extract → diarize →    │   │
                                                                     │ │ transcribe → translate  │   │
                                                                     │ └──────────┬─────────────┘   │
                                                                     │            │ .spawn() per     │
                                                                     │            │ speaker          │
                                                                     │  ┌─────────▼──────────┐      │
                                                                     │  │ Synth containers   │      │
                                                                     │  │ (CPU, 1 per speaker)│      │
                                                                     │  │ clone + synthesize  │      │
                                                                     │  └─────────┬──────────┘      │
                                                                     │            │                  │
                                                                     │  ┌─────────▼──────────┐      │
                                                                     │  │ Composite (CPU)    │      │
                                                                     │  └────────────────────┘      │
                                                                     └──────────────────────────────┘
```

**Data flow:** Video file → FastAPI saves to disk → orchestrator calls Modal function → Modal runs pipeline (extract → diarize → transcribe → translate on one GPU container, then spawns parallel CPU containers for per-speaker voice synthesis) → composite → output video returned as bytes → FastAPI saves to disk and serves download.

**Why this architecture matters for judging:** The synthesis step spawns N containers simultaneously (one per speaker). For a clip with 3 speakers, judges see 3 containers fire in parallel on the Modal dashboard. This is genuinely load-bearing — synthesis is the slowest step and the parallelism produces a real speedup. The rest of the pipeline runs sequentially because each step depends on the previous one's output.

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

**Architecture: hybrid approach (recommended).** One orchestrator function runs on a GPU container and handles the sequential steps (extract, diarize, transcribe, translate). It then spawns separate CPU containers for voice synthesis — one per speaker, running in parallel. Finally, composite runs in the orchestrator container.

This gives you the best of both worlds: simple sequential flow where needed, visible parallelism for the Modal track judges, and a real speedup on the slowest step.

```python
# pipeline/modal_jobs.py — see Section 6 for full implementation
@app.function(image=gpu_image, gpu="T4", ...)
def run_pipeline_remote(video_bytes: bytes, target_language: str) -> bytes:
    # sequential: extract → diarize → transcribe → translate
    # parallel:   spawn synthesize_speaker.spawn() per speaker
    # sequential: composite
    ...

@app.function(image=cpu_image, ...)
def synthesize_speaker(speaker: str, segments: list[dict], sample_bytes: bytes, ...) -> list[dict]:
    # clone voice + synthesize all segments for one speaker
    ...
```

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
            # Build atempo filter chain — each atempo filter maxes at 2.0,
            # so chain them for higher ratios (e.g., 3x = atempo=2.0,atempo=1.5)
            atempo_chain = _build_atempo_chain(speed_factor)
            sped_up_path = seg["dubbed_audio_path"] + ".speed.wav"
            subprocess.run([
                "ffmpeg", "-y",
                "-i", seg["dubbed_audio_path"],
                "-filter:a", atempo_chain,
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

**`_build_atempo_chain` helper:**
```python
def _build_atempo_chain(speed_factor: float) -> str:
    """
    Build an ffmpeg atempo filter chain for arbitrary speedup.
    Each atempo filter is capped at 2.0x, so we chain multiple
    for higher ratios. E.g., 3.0x → "atempo=2.0,atempo=1.5"
    Cap total speedup at 4.0x to avoid unintelligible audio.
    """
    speed_factor = min(speed_factor, 4.0)
    filters = []
    remaining = speed_factor
    while remaining > 1.0:
        chunk = min(remaining, 2.0)
        filters.append(f"atempo={chunk:.4f}")
        remaining /= chunk
    return ",".join(filters) if filters else "atempo=1.0"
```

**Key decisions:**
- **Silent base track:** Start with silence, overlay dubbed clips at their timestamps. Gaps between segments are naturally silent.
- **Speed adjustment:** If the dubbed audio is longer than the original segment's time window, speed it up using chained `atempo` filters. Each `atempo` maxes at 2.0x, so we chain them (e.g., 3x = `atempo=2.0,atempo=1.5`). Total speedup is capped at 4.0x — beyond that, speech becomes unintelligible anyway. This matters for Arabic and German translations, which tend to be wordier than English.
- **Video passthrough:** `-c:v copy` copies the video stream without re-encoding. This is fast and lossless.
- **Output format:** MP4 with original video + new audio.

---

## 6. Orchestrator — Modal Integration

The orchestrator uses a hybrid approach: one GPU container runs the sequential steps, then spawns parallel CPU containers for per-speaker synthesis.

### `pipeline/modal_jobs.py`

```python
import modal
from pipeline.modal_app import app, gpu_image, cpu_image

# ── Per-speaker synthesis (spawned in parallel) ─────────────────────────────

@app.function(
    image=cpu_image,
    timeout=300,
    concurrency_limit=6,
    secrets=[modal.Secret.from_name("mimic-secrets")],
)
def synthesize_speaker(
    speaker: str,
    segments: list[dict],
    sample_bytes: bytes,
    job_id: str,
) -> list[dict]:
    """
    Clone one speaker's voice and synthesize all their segments.
    Runs in its own container — one container per speaker, all in parallel.

    Args:
        speaker:      Speaker label ("SPEAKER_00")
        segments:     All translated segments for this speaker
        sample_bytes: Raw audio bytes of the best voice sample for cloning
        job_id:       Job identifier for voice clone naming

    Returns:
        List of segment dicts with dubbed_audio_bytes added (bytes, not paths —
        since each container has its own filesystem).
    """
    import asyncio
    import os
    import aiohttp
    import tempfile

    ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"
    api_key = os.environ["ELEVENLABS_API_KEY"]

    async def _run():
        async with aiohttp.ClientSession() as session:
            # Clone voice
            headers = {"xi-api-key": api_key}
            form = aiohttp.FormData()
            form.add_field("name", f"{job_id}_{speaker}")
            form.add_field("files", sample_bytes, filename=f"{speaker}.wav", content_type="audio/wav")
            async with session.post(f"{ELEVENLABS_BASE}/voices/add", headers=headers, data=form) as resp:
                resp.raise_for_status()
                voice_id = (await resp.json())["voice_id"]

            # Synthesize all segments for this speaker
            results = []
            for seg in segments:
                if not seg.get("translated_text", "").strip():
                    continue

                payload = {
                    "text": seg["translated_text"],
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                }
                headers_tts = {
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                }
                async with session.post(
                    f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}",
                    headers=headers_tts, json=payload,
                ) as resp:
                    resp.raise_for_status()
                    audio_bytes = await resp.read()

                results.append({
                    "speaker": seg["speaker"],
                    "start": seg["start"],
                    "end": seg["end"],
                    "dubbed_audio_bytes": audio_bytes,
                })

            # Cleanup: delete cloned voice
            async with session.delete(
                f"{ELEVENLABS_BASE}/voices/{voice_id}", headers={"xi-api-key": api_key}
            ) as resp:
                pass  # best-effort

            return results

    return asyncio.run(_run())


# ── Main orchestrator (GPU container) ────────────────────────────────────────

@app.function(
    image=gpu_image,
    gpu="T4",
    timeout=600,
    concurrency_limit=2,
    secrets=[modal.Secret.from_name("mimic-secrets")],
)
def run_pipeline_remote(video_bytes: bytes, target_language: str) -> bytes:
    """
    Main pipeline orchestrator. Runs on GPU for diarization.
    Spawns parallel containers for synthesis.
    """
    import tempfile, os, asyncio

    with tempfile.TemporaryDirectory() as tmpdir:
        # Save input
        input_path = os.path.join(tmpdir, "input.mp4")
        with open(input_path, "wb") as f:
            f.write(video_bytes)

        # ── Sequential steps (all in this container) ──
        from pipeline.extract import extract_audio
        from pipeline.diarize import diarize_speakers
        from pipeline.transcribe import transcribe_segments
        from pipeline.translate import translate_segments
        from pipeline.composite import composite_video

        audio_path = extract_audio(input_path, "job", tmpdir)
        segments = diarize_speakers(audio_path, tmpdir)
        segments = transcribe_segments(segments)
        segments = translate_segments(segments, target_language)

        # ── Parallel synthesis (spawn one container per speaker) ──
        speakers = {}
        for seg in segments:
            speakers.setdefault(seg["speaker"], []).append(seg)

        # Read voice samples (longest clip per speaker)
        speaker_samples = {}
        for spk, segs in speakers.items():
            best = max(segs, key=lambda s: s["end"] - s["start"])
            with open(best["audio_path"], "rb") as f:
                speaker_samples[spk] = f.read()

        # Spawn parallel containers
        handles = []
        for spk, segs in speakers.items():
            # Strip audio_path (not accessible from synth container)
            clean_segs = [
                {k: v for k, v in s.items() if k != "audio_path"} for s in segs
            ]
            handle = synthesize_speaker.spawn(spk, clean_segs, speaker_samples[spk], "job")
            handles.append(handle)

        # Collect results from all containers
        synthesized = []
        dub_dir = os.path.join(tmpdir, "dubbed")
        os.makedirs(dub_dir, exist_ok=True)

        for handle in handles:
            speaker_results = handle.get()
            for i, seg in enumerate(speaker_results):
                # Write audio bytes to disk for compositing
                dub_path = os.path.join(dub_dir, f"dub_{seg['speaker']}_{i:04d}.mp3")
                with open(dub_path, "wb") as f:
                    f.write(seg["dubbed_audio_bytes"])
                synthesized.append({
                    "speaker": seg["speaker"],
                    "start": seg["start"],
                    "end": seg["end"],
                    "dubbed_audio_path": dub_path,
                })

        # ── Composite (back in this container) ──
        output_path = composite_video(input_path, synthesized, "job", os.path.join(tmpdir, "output"))

        with open(output_path, "rb") as f:
            return f.read()
```

**Key detail: `.spawn()` vs `.remote()`.** Using `synthesize_speaker.spawn()` returns a handle immediately without blocking. This launches all speaker containers simultaneously. Then `handle.get()` collects each result. For a 3-speaker clip, the Modal dashboard shows 1 GPU container + 3 CPU containers running at the same time.

**Why bytes instead of paths:** Each spawned container has its own filesystem. The synth containers can't read files from the orchestrator container. So we pass `sample_bytes` in and return `dubbed_audio_bytes` out. The orchestrator writes them to disk for the composite step.

### Updated `pipeline/orchestrator.py`

The local orchestrator calls Modal and simulates progress on the client side.

```python
import asyncio
import time
import threading
from pathlib import Path
from models import JobStatus


def update_job(jobs, job_id, status, step, progress, error=None):
    jobs[job_id] = JobStatus(
        job_id=job_id, status=status, step=step,
        progress=progress, error=error,
        output_url=f"/download/{job_id}" if status == "done" else None,
    )


# Simulated progress steps with estimated durations (seconds)
PROGRESS_STEPS = [
    ("Extracting audio...",              5,  10,  3),
    ("Identifying speakers...",         10,  25, 15),
    ("Transcribing speech...",          25,  40, 10),
    ("Translating dialogue...",         40,  55,  8),
    ("Cloning voices (parallel)...",    55,  75, 20),
    ("Compositing final video...",      75,  90, 10),
]


def _simulate_progress(jobs, job_id, stop_event: threading.Event):
    """
    Advance the progress bar through estimated step timings.
    Runs in a background thread. Stops when stop_event is set
    (i.e., when the Modal call returns).
    """
    for step_name, start_pct, end_pct, duration_s in PROGRESS_STEPS:
        if stop_event.is_set():
            return
        update_job(jobs, job_id, "running", step_name, start_pct)
        # Interpolate progress within this step
        intervals = max(duration_s, 1)
        for tick in range(intervals):
            if stop_event.is_set():
                return
            time.sleep(1)
            pct = start_pct + int((end_pct - start_pct) * (tick + 1) / intervals)
            update_job(jobs, job_id, "running", step_name, pct)


async def run_pipeline(job_id, input_path, target_language, jobs, output_dir):
    try:
        update_job(jobs, job_id, "running", "Starting...", 2)

        with open(input_path, "rb") as f:
            video_bytes = f.read()

        # Start simulated progress in background thread
        stop_event = threading.Event()
        progress_thread = threading.Thread(
            target=_simulate_progress, args=(jobs, job_id, stop_event), daemon=True,
        )
        progress_thread.start()

        # Call Modal — blocks until pipeline completes
        from pipeline.modal_jobs import run_pipeline_remote
        output_bytes = run_pipeline_remote.remote(video_bytes, target_language)

        # Stop simulated progress
        stop_event.set()
        progress_thread.join(timeout=2)

        # Save output locally
        update_job(jobs, job_id, "running", "Saving output...", 95)
        output_path = Path(output_dir) / f"{job_id}_dubbed.mp4"
        with open(output_path, "wb") as f:
            f.write(output_bytes)

        update_job(jobs, job_id, "done", "Complete!", 100)

    except Exception as e:
        stop_event.set()
        update_job(jobs, job_id, "error", "Pipeline failed", 0, error=str(e))
        raise
```

**Progress simulation:** The Modal call is a single blocking `.remote()` call. While it blocks, a background thread walks through the expected pipeline steps with timed increments. The frontend sees the progress bar advance through "Extracting audio..." → "Identifying speakers..." → etc. When Modal returns, the thread stops and progress jumps to 100%. The step durations are estimates — if the actual pipeline is faster or slower, the progress bar will either jump forward or pause at the last reached step. This is cosmetic, not functional, but it makes the UI/UX prize demo significantly more compelling.

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

**Local requirements** (what you `pip install` on your machine):
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

> `python-multipart` is required by FastAPI for `UploadFile` handling. Without it, `POST /dub` silently fails.

**Heavy deps** (`pyannote.audio`, `torch`, `torchaudio`) are NOT in local requirements — they're installed inside the Modal GPU image definition (see Section 4). This keeps local install fast and avoids GPU driver issues on dev machines.

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
