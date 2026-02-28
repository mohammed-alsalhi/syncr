"""
Pipeline Orchestrator
Calls Modal for the full pipeline and simulates progress locally.
"""

import time
import threading
from pathlib import Path
from models import JobStatus


def update_job(jobs: dict, job_id: str, status: str, step: str, progress: int, error: str = None):
    jobs[job_id] = JobStatus(
        job_id=job_id,
        status=status,
        step=step,
        progress=progress,
        error=error,
        output_url=f"/download/{job_id}" if status == "done" else None,
    )


# Simulated progress steps: (label, start_pct, end_pct, estimated_seconds)
PROGRESS_STEPS = [
    ("Extracting audio...",           5,  10,  3),
    ("Identifying speakers...",      10,  25, 15),
    ("Transcribing speech...",       25,  40, 10),
    ("Translating dialogue...",      40,  55,  8),
    ("Cloning voices (parallel)...", 55,  75, 20),
    ("Compositing final video...",   75,  90, 10),
]


def _simulate_progress(jobs: dict, job_id: str, stop_event: threading.Event):
    """
    Advance the progress bar through estimated step timings.
    Runs in a background thread. Stops when stop_event is set
    (i.e., when the Modal call returns).
    """
    for step_name, start_pct, end_pct, duration_s in PROGRESS_STEPS:
        if stop_event.is_set():
            return
        update_job(jobs, job_id, "running", step_name, start_pct)
        intervals = max(duration_s, 1)
        for tick in range(intervals):
            if stop_event.is_set():
                return
            time.sleep(1)
            pct = start_pct + int((end_pct - start_pct) * (tick + 1) / intervals)
            update_job(jobs, job_id, "running", step_name, pct)


async def run_pipeline(
    job_id: str,
    input_path: str,
    target_language: str,
    jobs: dict,
    output_dir: str,
):
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
