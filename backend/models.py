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
