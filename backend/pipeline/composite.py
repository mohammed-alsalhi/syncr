"""
Step 6: Composite dubbed audio back onto the original video using ffmpeg.
"""

import subprocess
import os
from pydub import AudioSegment


def _build_atempo_chain(speed_factor: float) -> str:
    """
    Build an ffmpeg atempo filter chain for arbitrary speedup.
    Each atempo filter is capped at 2.0x, so we chain multiple
    for higher ratios. E.g., 3.0x -> "atempo=2.0,atempo=1.5"
    Cap total speedup at 4.0x to avoid unintelligible audio.
    """
    speed_factor = min(speed_factor, 4.0)
    filters = []
    remaining = speed_factor
    while remaining > 1.0:
        chunk = min(remaining, 2.0)
        filters.append(f"atempo={chunk:.4f}")
        remaining /= chunk
    return ",".join(filters) if filters else "atempo=1.0"


def composite_video(
    input_video: str,
    synthesized_segments: list[dict],
    job_id: str,
    output_dir: str,
) -> str:
    """
    Composite dubbed audio segments back onto the original video.

    Args:
        input_video:           Path to original video file
        synthesized_segments:  List of dicts with keys: speaker, start, end, dubbed_audio_path
        job_id:                Job identifier (used for output filename)
        output_dir:            Directory to write final video

    Returns:
        Path to dubbed video file (MP4)

    Raises:
        subprocess.CalledProcessError: If ffmpeg fails
    """
    os.makedirs(output_dir, exist_ok=True)

    # Get original video duration
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", input_video],
        capture_output=True, text=True, check=True,
    )
    total_duration_ms = int(float(probe.stdout.strip()) * 1000)

    # Build a full-length silent audio track
    mixed = AudioSegment.silent(duration=total_duration_ms)

    # Overlay each dubbed segment at its timestamp
    for seg in synthesized_segments:
        dubbed_clip = AudioSegment.from_file(seg["dubbed_audio_path"])
        position_ms = int(seg["start"] * 1000)
        target_duration_ms = int((seg["end"] - seg["start"]) * 1000)

        # If dubbed audio is longer than the original slot, speed it up
        if len(dubbed_clip) > target_duration_ms and target_duration_ms > 0:
            speed_factor = len(dubbed_clip) / target_duration_ms
            atempo_chain = _build_atempo_chain(speed_factor)
            sped_up_path = seg["dubbed_audio_path"] + ".speed.wav"
            subprocess.run([
                "ffmpeg", "-y",
                "-i", seg["dubbed_audio_path"],
                "-filter:a", atempo_chain,
                sped_up_path,
            ], check=True, capture_output=True)
            dubbed_clip = AudioSegment.from_file(sped_up_path)

        # Truncate if still too long
        dubbed_clip = dubbed_clip[:target_duration_ms]

        mixed = mixed.overlay(dubbed_clip, position=position_ms)

    # Export mixed audio
    mixed_audio_path = os.path.join(output_dir, f"{job_id}_mixed.wav")
    mixed.export(mixed_audio_path, format="wav")

    # Combine original video (no audio) with new audio
    output_path = os.path.join(output_dir, f"{job_id}_dubbed.mp4")
    subprocess.run([
        "ffmpeg", "-y",
        "-i", input_video,
        "-i", mixed_audio_path,
        "-c:v", "copy",         # keep original video codec (fast, no re-encoding)
        "-map", "0:v:0",        # video from first input
        "-map", "1:a:0",        # audio from second input
        "-shortest",
        output_path,
    ], check=True, capture_output=True)

    return output_path
