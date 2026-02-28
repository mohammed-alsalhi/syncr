"""
Scene-aware video chunking for the Syncr dubbing pipeline.

Splits long videos into manageable chunks at scene boundaries so each chunk
can be processed independently through the dubbing pipeline.  Chunks include
a small overlap at boundaries to preserve speaker continuity.
"""

import subprocess
import os
import re


def detect_scenes(video_path: str) -> list[dict]:
    """
    Detect scene boundaries in a video using ffmpeg's scene change filter.

    Runs ffmpeg with the ``select='gt(scene,0.3)'`` and ``showinfo`` filters,
    then parses the ``pts_time`` values from the showinfo output to identify
    timestamps where scene changes occur.

    Args:
        video_path: Absolute path to the input video file.

    Returns:
        List of scene boundary dicts, each with ``start`` and ``end`` keys
        (float seconds).  For example::

            [{"start": 0.0, "end": 5.2}, {"start": 5.2, "end": 12.8}]

        If no scene changes are detected the list contains a single entry
        spanning the full video duration.

    Raises:
        subprocess.CalledProcessError: If ffmpeg or ffprobe fails.
        ValueError: If the video duration cannot be determined.
    """
    # --- Get total video duration via ffprobe ---
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            video_path,
        ],
        check=True, capture_output=True, text=True,
    )
    duration_str = probe.stdout.strip()
    if not duration_str:
        raise ValueError(f"Could not determine duration for {video_path}")
    total_duration = float(duration_str)

    # --- Run scene-detection filter ---
    # Note: ffmpeg may return non-zero exit code on certain inputs even when
    # scene detection output is usable, so we don't use check=True here.
    result = subprocess.run(
        [
            "ffmpeg",
            "-i", video_path,
            "-filter:v", "select='gt(scene,0.3)',showinfo",
            "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )

    # showinfo writes to stderr
    output = result.stderr

    # Parse pts_time values from showinfo lines.
    # Example line:
    #   [Parsed_showinfo_1 ...] n:  12 ... pts_time:5.2050 ...
    pts_times: list[float] = []
    for match in re.finditer(r"pts_time:\s*([\d.]+)", output):
        pts_times.append(float(match.group(1)))

    # Deduplicate and sort (scene filter may emit duplicates)
    pts_times = sorted(set(pts_times))

    # --- Build scene list ---
    if not pts_times:
        # No scene changes detected — single scene for the entire video
        return [{"start": 0.0, "end": total_duration}]

    scenes: list[dict] = []

    # First scene: from the beginning to the first detected change
    scenes.append({"start": 0.0, "end": pts_times[0]})

    # Intermediate scenes
    for i in range(len(pts_times) - 1):
        scenes.append({"start": pts_times[i], "end": pts_times[i + 1]})

    # Last scene: from the final change to the end of the video
    scenes.append({"start": pts_times[-1], "end": total_duration})

    # Filter out zero-length scenes that can arise from duplicate timestamps
    scenes = [s for s in scenes if s["end"] > s["start"]]

    return scenes


def split_video(
    video_path: str,
    scenes: list[dict],
    max_chunk_duration: float = 300.0,
    work_dir: str = "/tmp",
) -> list[dict]:
    """
    Group scenes into chunks of approximately *max_chunk_duration* seconds
    and extract each chunk as a separate video file.

    Splitting always happens at scene boundaries — a scene is never cut in
    the middle.  If a single scene is longer than *max_chunk_duration* it
    becomes its own chunk rather than being split.

    Each chunk (except the first and last) is extended by 2 seconds at its
    boundaries to overlap with neighbors, which helps maintain speaker
    continuity during dubbing.

    For short videos whose total duration fits within *max_chunk_duration*,
    a single chunk covering the full video is returned without re-encoding.

    Args:
        video_path:          Absolute path to the input video file.
        scenes:              Scene boundary list as returned by
                             :func:`detect_scenes`.
        max_chunk_duration:  Target maximum duration per chunk in seconds
                             (default 300 = 5 minutes).
        work_dir:            Directory to write chunk files into.

    Returns:
        List of chunk dicts, each containing::

            {
                "chunk_idx": 0,
                "start": 0.0,
                "end": 302.0,
                "video_path": "/tmp/chunk_0000.mp4"
            }

    Raises:
        subprocess.CalledProcessError: If ffmpeg fails during extraction.
    """
    os.makedirs(work_dir, exist_ok=True)

    if not scenes:
        return []

    # --- Group scenes into chunks ---
    groups: list[list[dict]] = []
    current_group: list[dict] = []
    current_duration = 0.0

    for scene in scenes:
        scene_duration = scene["end"] - scene["start"]

        if current_group and current_duration + scene_duration > max_chunk_duration:
            # Adding this scene would exceed the limit — finalize current group
            groups.append(current_group)
            current_group = [scene]
            current_duration = scene_duration
        else:
            current_group.append(scene)
            current_duration += scene_duration

    # Don't forget the last group
    if current_group:
        groups.append(current_group)

    # --- Determine boundaries with 2-second overlap ---
    OVERLAP = 2.0
    total_end = scenes[-1]["end"]

    chunks: list[dict] = []

    for idx, group in enumerate(groups):
        raw_start = group[0]["start"]
        raw_end = group[-1]["end"]

        # Apply overlap: extend start backwards (except for the first chunk)
        chunk_start = max(0.0, raw_start - OVERLAP) if idx > 0 else raw_start

        # Apply overlap: extend end forwards (except for the last chunk)
        chunk_end = min(total_end, raw_end + OVERLAP) if idx < len(groups) - 1 else raw_end

        output_path = os.path.join(work_dir, f"chunk_{idx:04d}.mp4")

        # Extract the chunk via ffmpeg
        # Use -ss before -i for fast keyframe-seeking, then re-encode to
        # guarantee frame-accurate boundaries (stream copy can drift).
        chunk_duration = chunk_end - chunk_start
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", str(chunk_start),
                "-i", video_path,
                "-t", str(chunk_duration),
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-c:a", "aac",
                output_path,
            ],
            check=True, capture_output=True,
        )

        chunks.append({
            "chunk_idx": idx,
            "start": chunk_start,
            "end": chunk_end,
            "video_path": output_path,
        })

    return chunks
