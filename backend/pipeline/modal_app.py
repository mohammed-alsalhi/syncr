"""
Modal App, Image, and shared definitions.

Three image tiers:
  cpu_image     — lightweight: coordinator, synthesis, translation containers
  gpu_image     — heavy: process_chunk containers (pyannote diarization needs GPU)
  whisper_image — self-hosted faster-whisper for parallel transcription on GPU
"""

import modal

app = modal.App("syncr")

# CPU image — lightweight, used by coordinator, synthesis, and translation containers
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
    .add_local_python_source("pipeline")
)

# GPU image — heavy, used by process_chunk containers (diarization needs GPU)
gpu_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "torch==2.2.0",
        "torchaudio==2.2.0",
        "pyannote.audio",
        "openai",
        "aiohttp",
        "aiofiles",
        "python-dotenv",
        "pydub",
        "numpy",
    )
    .add_local_python_source("pipeline")
)

# Whisper image — self-hosted faster-whisper for real GPU inference
# Uses debian_slim + pip ctranslate2 which bundles CUDA runtime
whisper_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "faster-whisper",
        "pydub",
        "ctranslate2",
    )
    .add_local_python_source("pipeline")
)
