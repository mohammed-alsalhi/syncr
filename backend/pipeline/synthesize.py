"""
Step 5: Voice cloning and TTS synthesis using ElevenLabs.
Used as a local fallback. The primary path runs via Modal (see modal_jobs.py).
"""

import os
import asyncio
import aiohttp
import aiofiles

ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"


async def synthesize_speakers(segments: list[dict], job_id: str, work_dir: str = "/tmp") -> list[dict]:
    """
    Clone voices and synthesize dubbed audio for all segments.
    Processes speakers in parallel via asyncio.gather.

    Args:
        segments: List of dicts with keys: speaker, start, end, audio_path, text, translated_text
        job_id:   Job identifier (used for voice clone naming)
        work_dir: Directory to write synthesized audio files

    Returns:
        List of dicts with "dubbed_audio_path" field added.
    """
    api_key = os.environ["ELEVENLABS_API_KEY"]
    dub_dir = os.path.join(work_dir, "dubbed")
    os.makedirs(dub_dir, exist_ok=True)

    # Group segments by speaker
    speakers: dict[str, list[dict]] = {}
    for seg in segments:
        speakers.setdefault(seg["speaker"], []).append(seg)

    # Find longest audio clip per speaker (best sample for cloning)
    speaker_samples = {}
    for spk, segs in speakers.items():
        best = max(segs, key=lambda s: s["end"] - s["start"])
        speaker_samples[spk] = best["audio_path"]

    async with aiohttp.ClientSession() as session:
        # Clone each speaker's voice (parallel)
        voice_ids = {}
        clone_tasks = [
            _clone_voice(session, api_key, spk, sample_path, job_id)
            for spk, sample_path in speaker_samples.items()
        ]
        clone_results = await asyncio.gather(*clone_tasks)
        for spk, voice_id in clone_results:
            voice_ids[spk] = voice_id

        # Synthesize each segment (parallel)
        synth_tasks = []
        for i, seg in enumerate(segments):
            if not seg.get("translated_text", "").strip():
                continue
            synth_tasks.append(
                _synthesize_segment(session, api_key, seg, voice_ids[seg["speaker"]], i, dub_dir)
            )
        synth_results = await asyncio.gather(*synth_tasks)

        # Cleanup cloned voices (free tier has voice limit)
        for voice_id in voice_ids.values():
            await _delete_voice(session, api_key, voice_id)

    return synth_results


async def _clone_voice(session, api_key, speaker, sample_path, job_id):
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


async def _synthesize_segment(session, api_key, segment, voice_id, index, output_dir):
    url = f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": segment["translated_text"],
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
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


async def _delete_voice(session, api_key, voice_id):
    url = f"{ELEVENLABS_BASE}/voices/{voice_id}"
    headers = {"xi-api-key": api_key}
    async with session.delete(url, headers=headers) as resp:
        pass  # best-effort cleanup
