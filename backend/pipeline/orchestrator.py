"""
Pipeline Orchestrator
Calls Modal coordinator and polls real progress via modal.Dict.
"""

import time
import threading
from pathlib import Path
from models import JobStatus


def _update_job(jobs: dict, job_id: str, **kwargs):
    """Merge partial updates into the current job status."""
    current = jobs[job_id].model_dump()
    current.update(kwargs)
    # Set output_url when done
    if current.get("status") == "done":
        current["output_url"] = f"/download/{job_id}"
    jobs[job_id] = JobStatus(**current)


def _poll_modal_progress(jobs: dict, job_id: str, stop_event: threading.Event):
    """
    Poll modal.Dict for real progress updates written by Modal containers.
    Runs in a background thread. Stops when stop_event is set.
    """
    import modal

    progress_dict = modal.Dict.from_name("syncr-progress", create_if_missing=True)

    while not stop_event.is_set():
        try:
            data = progress_dict.get(job_id)
            if data and isinstance(data, dict):
                # Never propagate "done" status from Modal — only the
                # orchestrator should set "done" after the output file is
                # written to disk.  Otherwise the frontend requests the
                # download before the file exists (race condition).
                modal_status = data.get("status", "running")
                if modal_status == "done":
                    modal_status = "running"

                _update_job(
                    jobs, job_id,
                    status=modal_status,
                    step=data.get("step", "Processing..."),
                    progress=min(data.get("progress", jobs[job_id].progress), 97),
                    total_chunks=data.get("total_chunks"),
                    completed_chunks=data.get("completed_chunks"),
                    speakers_found=data.get("speakers_found"),
                    segments_found=data.get("segments_found"),
                    containers_active=data.get("containers_active"),
                    containers_total=data.get("containers_total"),
                    transcript_preview=data.get("transcript_preview"),
                    step_timings=data.get("step_timings"),
                )
        except Exception:
            pass  # Dict may not exist yet or container hasn't written yet
        time.sleep(1)


def run_pipeline(
    job_id: str,
    input_path: str,
    target_language: str,
    jobs: dict,
    output_dir: str,
):
    """
    Run the full dubbing pipeline. This is a sync function — FastAPI's
    BackgroundTasks runs it in a threadpool so it doesn't block the event loop.
    """
    stop_event = threading.Event()
    try:
        _update_job(jobs, job_id, status="running", step="Starting...", progress=1)

        with open(input_path, "rb") as f:
            video_bytes = f.read()

        # Start polling real progress from modal.Dict
        progress_thread = threading.Thread(
            target=_poll_modal_progress, args=(jobs, job_id, stop_event), daemon=True,
        )
        progress_thread.start()

        # Call the deployed Modal coordinator function
        import modal
        coordinator_fn = modal.Function.from_name("syncr", "coordinator")
        output_bytes = coordinator_fn.remote(video_bytes, target_language, job_id)

        # Stop progress polling
        stop_event.set()
        progress_thread.join(timeout=2)

        # Save output locally
        _update_job(jobs, job_id, status="running", step="Saving output...", progress=98)
        output_path = Path(output_dir) / f"{job_id}_dubbed.mp4"
        with open(output_path, "wb") as f:
            f.write(output_bytes)

        _update_job(jobs, job_id, status="done", step="Complete!", progress=100)

    except Exception as e:
        stop_event.set()
        _update_job(jobs, job_id, status="error", step="Pipeline failed", progress=0, error=str(e))
        raise
