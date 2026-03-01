"""
Merge dubbed audio from multiple processed chunks back onto the original video.

After the coordinator splits a long video into chunks and processes each one
through the pipeline (diarize -> transcribe -> translate -> synthesize), this
module stitches all the dubbed audio segments into a single full-length audio
track and muxes it with the original video.

When Demucs source separation is available, the dubbed speech is overlaid onto
a clean accompaniment track (music + effects + ambient, original voices removed).
When not available, falls back to ducking the original audio during speech.
"""

import io
import subprocess
import os
from pydub import AudioSegment

from pipeline.composite import _build_atempo_chain

DUCK_DB = -15  # dB reduction for fallback ducking during dubbed segments


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


def _build_background_track(
    original_video: str,
    total_duration_ms: int,
    segments: list[dict],
    accompaniment_bytes: bytes | None = None,
) -> AudioSegment:
    """
    Build the background audio track for the dubbed video.

    If accompaniment_bytes is provided (from Demucs source separation), uses
    the clean accompaniment at full volume — original voices are already removed.

    If not available, falls back to the original audio with ducking: reduces
    volume by DUCK_DB during dubbed speech segments to suppress original voices
    while preserving background sounds.
    """
    if accompaniment_bytes:
        # Demucs path: clean accompaniment with original voices removed
        bg = AudioSegment.from_file(io.BytesIO(accompaniment_bytes))

        # Demucs adds symmetric padding (extra samples at start and end)
        # for its sliding-window processing. If we just trim from the end,
        # the start padding stays and shifts the entire background audio late.
        # Center-trim: remove equal padding from both ends to stay in sync.
        if len(bg) > total_duration_ms:
            excess = len(bg) - total_duration_ms
            trim_start = excess // 2
            bg = bg[trim_start:trim_start + total_duration_ms]
            print(f"[merge] Demucs center-trim: removed {excess}ms padding "
                  f"({trim_start}ms from start, {excess - trim_start}ms from end)")
    else:
        # Fallback path: original audio with ducking during speech
        bg = AudioSegment.from_file(original_video)

    # Ensure background matches expected duration (trim or pad)
    if len(bg) < total_duration_ms:
        bg += AudioSegment.silent(duration=total_duration_ms - len(bg))
    elif len(bg) > total_duration_ms:
        bg = bg[:total_duration_ms]

    # If using fallback (no Demucs), duck original audio during dubbed segments
    if not accompaniment_bytes:
        for seg in segments:
            start_ms = int(seg["start"] * 1000)
            end_ms = min(int(seg["end"] * 1000), len(bg))
            if start_ms >= end_ms:
                continue
            before = bg[:start_ms]
            during = bg[start_ms:end_ms].apply_gain(DUCK_DB)
            after = bg[end_ms:]
            bg = before + during + after

    return bg


def merge_chunks(
    original_video: str,
    chunk_results: list[dict],
    job_id: str,
    output_dir: str,
    accompaniment_bytes: bytes | None = None,
) -> str:
    """
    Merge dubbed audio from multiple chunks onto the original video.

    Each chunk has already been through diarize -> transcribe -> translate,
    and the coordinator has handled synthesis globally. This function flattens
    all segment results, builds a full-length dubbed audio track, and muxes
    it with the original video stream.

    Args:
        original_video:      Path to the original full-length video file.
        chunk_results:       List of chunk result dicts. Each dict contains:
                             - chunk_idx (int): chunk ordering index
                             - start (float): chunk start time in original video
                             - end (float): chunk end time in original video
                             - segments (list[dict]): synthesized segments with
                               absolute timing in original video and
                               dubbed_audio_path for each segment.
        job_id:              Job identifier for naming output files.
        output_dir:          Directory to write final output video and
                             intermediate files.
        accompaniment_bytes: Optional WAV bytes of the accompaniment track from
                             Demucs source separation (music + effects, no vocals).
                             If None, falls back to ducking the original audio.

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

    # 2. Flatten all segments, filtering out overlap duplicates
    segments = _filter_overlap_duplicates(chunk_results)
    print(f"[merge] {len(segments)} segments, video duration {total_duration_ms}ms, "
          f"accompaniment={'yes' if accompaniment_bytes else 'no'}")

    # 3. Build background audio track (Demucs accompaniment or ducked original)
    mixed = _build_background_track(
        original_video, total_duration_ms, segments, accompaniment_bytes,
    )
    print(f"[merge] Background track: {len(mixed)}ms, {mixed.channels}ch, {mixed.frame_rate}Hz")

    # Load original audio once for per-segment volume matching
    original_audio = AudioSegment.from_file(original_video)

    # 4. Overlay each dubbed segment at its absolute timestamp
    FADE_MS = 100   # Crossfade duration — long enough to mask gain discontinuities
    MAX_GAIN_DB = 6  # Clamp gain adjustment to avoid amplitude spikes at boundaries
    MAX_SPEEDUP = 3.0  # Cap speedup to avoid quality degradation

    for seg in segments:
        dubbed_path = seg["dubbed_audio_path"]
        dubbed_clip = AudioSegment.from_file(dubbed_path)
        position_ms = int(seg["start"] * 1000)
        target_duration_ms = int((seg["end"] - seg["start"]) * 1000)

        # Speed up if dubbed audio is longer than its time slot
        if len(dubbed_clip) > target_duration_ms and target_duration_ms > 0:
            speed_factor = len(dubbed_clip) / target_duration_ms
            speed_factor = min(speed_factor, MAX_SPEEDUP)  # Cap to avoid artifacts
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

        # Truncate if still too long after speedup
        dubbed_clip = dubbed_clip[:target_duration_ms]

        # Match dubbed volume to original scene volume.
        # In the original video, voice loudness varies naturally: close-ups
        # are louder, distant shots quieter, whispers vs shouts, etc.
        # ElevenLabs synthesizes at a uniform level, so we adjust each
        # dubbed clip to match the loudness of the original at that timestamp.
        # Gain is clamped to ±MAX_GAIN_DB to prevent harsh amplitude jumps
        # at segment boundaries that cause pops/clicks.
        orig_clip = original_audio[position_ms:position_ms + target_duration_ms]
        if orig_clip.dBFS > -50 and dubbed_clip.dBFS > -50:
            gain_db = orig_clip.dBFS - dubbed_clip.dBFS
            gain_db = max(-MAX_GAIN_DB, min(MAX_GAIN_DB, gain_db))
            dubbed_clip = dubbed_clip.apply_gain(gain_db)

        # Apply fade-in/fade-out AFTER gain to smooth any remaining
        # amplitude discontinuities at segment boundaries.
        if len(dubbed_clip) > FADE_MS * 2:
            dubbed_clip = dubbed_clip.fade_in(FADE_MS).fade_out(FADE_MS)

        mixed = mixed.overlay(dubbed_clip, position=position_ms)

    # 5. Export the mixed audio as WAV
    print(f"[merge] Final mixed track: {len(mixed)}ms after overlaying {len(segments)} segments")
    mixed_audio_path = os.path.join(output_dir, f"{job_id}_merged_mixed.wav")
    mixed.export(mixed_audio_path, format="wav")

    # 6. Mux with original video — re-encode to h264 for universal browser playback.
    # -movflags +faststart enables progressive playback (browser can start playing
    # before the full download completes, prevents apparent "black screen").
    output_path = os.path.join(output_dir, f"{job_id}_dubbed.mp4")
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", original_video,
            "-i", mixed_audio_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            "-movflags", "+faststart",
            output_path,
        ],
        check=True, capture_output=True,
    )

    return output_path
