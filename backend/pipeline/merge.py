"""
Merge dubbed audio from multiple processed chunks back onto the original video.

After the coordinator splits a long video into chunks and processes each one
through the pipeline (diarize -> transcribe -> translate -> synthesize), this
module stitches all the dubbed audio segments into a single full-length audio
track and muxes it with the original video.
"""

import subprocess
import os
from pydub import AudioSegment

from pipeline.composite import _build_atempo_chain


def _filter_overlap_duplicates(
    chunk_results: list[dict],
) -> list[dict]:
    """
    Remove duplicate segments that appear in overlapping chunk boundaries.

    When chunks overlap, segments near the boundary may appear in both chunk N
    and chunk N+1. We keep only the segment from the earlier chunk: for each
    pair of adjacent chunks, drop any segment from the later chunk whose start
    time falls before the earlier chunk's end time.

    Args:
        chunk_results: List of chunk dicts sorted by chunk_idx.

    Returns:
        Flat list of segment dicts with boundary duplicates removed.
    """
    sorted_chunks = sorted(chunk_results, key=lambda c: c["chunk_idx"])
    all_segments: list[dict] = []

    for i, chunk in enumerate(sorted_chunks):
        if i == 0:
            # First chunk: keep all segments
            all_segments.extend(chunk.get("segments", []))
        else:
            prev_end = sorted_chunks[i - 1]["end"]
            for seg in chunk.get("segments", []):
                # Skip segments from this chunk that start within the
                # previous chunk's time range (overlap zone)
                if seg["start"] < prev_end:
                    continue
                all_segments.append(seg)

    return all_segments


def merge_chunks(
    original_video: str,
    chunk_results: list[dict],
    job_id: str,
    output_dir: str,
) -> str:
    """
    Merge dubbed audio from multiple chunks onto the original video.

    Each chunk has already been through diarize -> transcribe -> translate,
    and the coordinator has handled synthesis globally. This function flattens
    all segment results, builds a full-length dubbed audio track, and muxes
    it with the original video stream.

    Args:
        original_video:  Path to the original full-length video file.
        chunk_results:   List of chunk result dicts. Each dict contains:
                         - chunk_idx (int): chunk ordering index
                         - start (float): chunk start time in original video
                         - end (float): chunk end time in original video
                         - segments (list[dict]): synthesized segments with
                           absolute timing in original video and
                           dubbed_audio_path for each segment.
        job_id:          Job identifier for naming output files.
        output_dir:      Directory to write final output video and
                         intermediate files.

    Returns:
        Path to the final dubbed video file (MP4).

    Raises:
        subprocess.CalledProcessError: If ffprobe or ffmpeg fails.
        FileNotFoundError: If original_video or a dubbed audio file is missing.
    """
    os.makedirs(output_dir, exist_ok=True)

    # 1. Get original video duration via ffprobe
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            original_video,
        ],
        capture_output=True, text=True, check=True,
    )
    total_duration_ms = int(float(probe.stdout.strip()) * 1000)

    # 2. Build a full-length silent audio track
    mixed = AudioSegment.silent(duration=total_duration_ms)

    # 3. Flatten all segments, filtering out overlap duplicates
    segments = _filter_overlap_duplicates(chunk_results)

    # 4-6. Overlay each dubbed segment at its absolute timestamp
    for seg in segments:
        dubbed_path = seg["dubbed_audio_path"]
        dubbed_clip = AudioSegment.from_file(dubbed_path)
        position_ms = int(seg["start"] * 1000)
        target_duration_ms = int((seg["end"] - seg["start"]) * 1000)

        # 5. If dubbed audio is longer than its time slot, speed it up
        if len(dubbed_clip) > target_duration_ms and target_duration_ms > 0:
            speed_factor = len(dubbed_clip) / target_duration_ms
            atempo_chain = _build_atempo_chain(speed_factor)
            sped_up_path = dubbed_path + ".speed.wav"
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", dubbed_path,
                    "-filter:a", atempo_chain,
                    sped_up_path,
                ],
                check=True, capture_output=True,
            )
            dubbed_clip = AudioSegment.from_file(sped_up_path)

        # 6. Truncate if still too long after speedup
        dubbed_clip = dubbed_clip[:target_duration_ms]

        mixed = mixed.overlay(dubbed_clip, position=position_ms)

    # 7. Export the mixed audio as WAV
    mixed_audio_path = os.path.join(output_dir, f"{job_id}_merged_mixed.wav")
    mixed.export(mixed_audio_path, format="wav")

    # 8. Mux with original video — copy video stream, replace audio
    output_path = os.path.join(output_dir, f"{job_id}_dubbed.mp4")
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", original_video,
            "-i", mixed_audio_path,
            "-c:v", "copy",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            output_path,
        ],
        check=True, capture_output=True,
    )

    # 9. Return output path
    return output_path
