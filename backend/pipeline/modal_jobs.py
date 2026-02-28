"""
Modal remote functions.
- run_pipeline_remote: main orchestrator (GPU, sequential steps + spawn synthesis)
- synthesize_speaker: per-speaker voice cloning + TTS (CPU, one container per speaker)
"""

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

    Returns list of dicts with dubbed_audio_bytes (bytes, not paths).
    """
    import asyncio
    import os
    import aiohttp

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
    Spawns parallel containers for per-speaker synthesis.
    """
    import tempfile
    import os

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
