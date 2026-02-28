"""
Step 1: Extract audio from video using ffmpeg.
"""

import subprocess
import os


def extract_audio(input_video_path: str, job_id: str, work_dir: str = "/tmp") -> str:
    """
    Extract audio from video as WAV (16kHz mono, 16-bit PCM).

    Args:
        input_video_path: Absolute path to input video file (mp4, mov, avi)
        job_id:           Unique job identifier (used for output filename)
        work_dir:         Directory to write output files

    Returns:
        Absolute path to extracted audio file (.wav)

    Raises:
        subprocess.CalledProcessError: If ffmpeg fails
    """
    output_path = os.path.join(work_dir, f"{job_id}_audio.wav")

    subprocess.run([
        "ffmpeg", "-y",
        "-i", input_video_path,
        "-vn",                    # no video
        "-acodec", "pcm_s16le",   # 16-bit PCM
        "-ar", "16000",           # 16kHz (required by Whisper and pyannote)
        "-ac", "1",               # mono
        output_path,
    ], check=True, capture_output=True)

    return output_path
