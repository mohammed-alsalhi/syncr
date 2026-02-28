from pydantic import BaseModel
from typing import Optional


class DubRequest(BaseModel):
    target_language: str = "es"


class JobStatus(BaseModel):
    job_id: str
    status: str           # "queued" | "running" | "done" | "error"
    step: str             # human-readable current step
    progress: int         # 0-100
    error: Optional[str] = None
    output_url: Optional[str] = None
    # Pipeline metrics (populated by real modal.Dict progress)
    total_chunks: Optional[int] = None
    completed_chunks: Optional[int] = None
    speakers_found: Optional[int] = None
    segments_found: Optional[int] = None
    containers_active: Optional[int] = None
    containers_total: Optional[int] = None
    transcript_preview: Optional[list[dict]] = None
    step_timings: Optional[dict] = None
