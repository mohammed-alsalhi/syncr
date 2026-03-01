from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn
import uuid
import os
from pathlib import Path

from pipeline.orchestrator import run_pipeline
from models import DubRequest, JobStatus

app = FastAPI(title="Mimic API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://synr.tech",
        "https://www.synr.tech",
        "http://localhost:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store (swap for Redis in production)
jobs: dict[str, JobStatus] = {}

UPLOAD_DIR = Path("tmp/uploads")
OUTPUT_DIR = Path("tmp/outputs")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@app.post("/dub")
async def create_dub_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target_language: str = Form("es"),
):
    job_id = str(uuid.uuid4())
    input_path = UPLOAD_DIR / f"{job_id}_{file.filename}"

    # Save uploaded file
    with open(input_path, "wb") as f:
        f.write(await file.read())

    # Initialize job status
    jobs[job_id] = JobStatus(
        job_id=job_id,
        status="queued",
        step="Waiting to start",
        progress=0,
    )

    # Run pipeline in background
    background_tasks.add_task(
        run_pipeline,
        job_id=job_id,
        input_path=str(input_path),
        target_language=target_language,
        jobs=jobs,
        output_dir=str(OUTPUT_DIR),
    )

    return {"job_id": job_id}


@app.get("/status/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in jobs:
        return {"error": "Job not found"}
    return jobs[job_id]


@app.get("/download/{job_id}")
async def download_result(job_id: str):
    output_path = OUTPUT_DIR / f"{job_id}_dubbed.mp4"
    if not output_path.exists():
        return {"error": "Output not ready"}
    return FileResponse(str(output_path), media_type="video/mp4", filename="dubbed.mp4")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
