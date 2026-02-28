"""
Pipeline Orchestrator
Coordinates: extract → diarize → transcribe → translate → clone+synth → composite
"""

import asyncio
from pathlib import Path
from models import JobStatus

from pipeline.extract import extract_audio
from pipeline.diarize import diarize_speakers
from pipeline.transcribe import transcribe_segments
from pipeline.translate import translate_segments
from pipeline.synthesize import synthesize_speakers
from pipeline.composite import composite_video


def update_job(jobs: dict, job_id: str, status: str, step: str, progress: int, error: str = None):
    jobs[job_id] = JobStatus(
        job_id=job_id,
        status=status,
        step=step,
        progress=progress,
        error=error,
        output_url=f"/download/{job_id}" if status == "done" else None,
    )


async def run_pipeline(
    job_id: str,
    input_path: str,
    target_language: str,
    jobs: dict,
    output_dir: str,
):
    try:
        # ── Step 1: Extract audio ──────────────────────────────────────────
        update_job(jobs, job_id, "running", "Extracting audio from video...", 5)
        audio_path = extract_audio(input_path, job_id)

        # ── Step 2: Diarize speakers ───────────────────────────────────────
        update_job(jobs, job_id, "running", "Identifying speakers...", 15)
        speaker_segments = diarize_speakers(audio_path)
        # speaker_segments: List[{speaker, start, end, audio_path}]

        # ── Step 3: Transcribe each segment ───────────────────────────────
        update_job(jobs, job_id, "running", "Transcribing speech...", 30)
        transcribed = transcribe_segments(speaker_segments)
        # transcribed: List[{speaker, start, end, text, audio_path}]

        # ── Step 4: Translate ──────────────────────────────────────────────
        update_job(jobs, job_id, "running", f"Translating to {target_language}...", 45)
        translated = translate_segments(transcribed, target_language)
        # translated: List[{speaker, start, end, original_text, translated_text, audio_path}]

        # ── Step 5: Voice clone + synthesize (parallel per speaker) ────────
        update_job(jobs, job_id, "running", "Cloning voices and synthesizing speech...", 60)
        synthesized = await synthesize_speakers(translated, job_id)
        # synthesized: List[{speaker, start, end, dubbed_audio_path}]

        # ── Step 6: Composite back onto video ─────────────────────────────
        update_job(jobs, job_id, "running", "Compositing final video...", 85)
        output_path = composite_video(
            input_video=input_path,
            synthesized_segments=synthesized,
            job_id=job_id,
            output_dir=output_dir,
        )

        # ── Done ───────────────────────────────────────────────────────────
        update_job(jobs, job_id, "done", "Complete!", 100)

    except Exception as e:
        update_job(jobs, job_id, "error", "Pipeline failed", 0, error=str(e))
        raise
