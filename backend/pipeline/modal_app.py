"""
Modal App, Image, and shared definitions.
"""

import modal

app = modal.App("syncr")

# CPU image — lightweight, used by most steps and synthesis containers
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

# GPU image — heavy, used by the orchestrator container (diarization needs GPU)
gpu_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "torch",
        "torchaudio",
        "pyannote.audio",
        "openai",
        "aiohttp",
        "aiofiles",
        "python-dotenv",
        "pydub",
    )
)
