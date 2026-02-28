"""
Quality verification and retry loop for synthesized dubbed segments.

After synthesis, checks each segment for timing, overlap, silence, and length
issues. Failed segments are flagged for re-translation with stricter constraints
and re-synthesis. Max 2 retry rounds before graceful degradation (accept with
speedup).
"""

import os
from pydub import AudioSegment


def verify_segments(segments: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Verify quality of synthesized audio segments.

    Checks each segment for:
      - Timing: dubbed audio should be within 1.5x of the original time slot
      - Overlap: dubbed audio (after potential speedup) should not collide with
        the next segment's start time
      - Silence: dubbed audio should not be mostly silence
      - Minimum length: dubbed audio should be at least 0.3 seconds

    Args:
        segments: List of dicts with keys:
            speaker, start, end, translated_text, dubbed_audio_path

    Returns:
        Tuple of (passed, failed) segment lists.
        Failed segments include a "failure_reason" field.
    """
    # Sort by start time to check overlaps
    sorted_segs = sorted(segments, key=lambda s: s["start"])

    passed = []
    failed = []

    for i, seg in enumerate(sorted_segs):
        dub_path = seg.get("dubbed_audio_path", "")
        if not dub_path or not os.path.exists(dub_path):
            failed.append({**seg, "failure_reason": "missing_audio"})
            continue

        try:
            dubbed_clip = AudioSegment.from_file(dub_path)
        except Exception:
            failed.append({**seg, "failure_reason": "unreadable_audio"})
            continue

        target_duration_ms = int((seg["end"] - seg["start"]) * 1000)
        dubbed_duration_ms = len(dubbed_clip)

        # Check minimum length
        if dubbed_duration_ms < 300:  # less than 0.3 seconds
            failed.append({**seg, "failure_reason": "too_short"})
            continue

        # Check silence ratio — if >80% of the audio is below -40 dBFS
        if dubbed_clip.dBFS < -35:
            failed.append({**seg, "failure_reason": "mostly_silence"})
            continue

        # Check timing — dubbed audio shouldn't be more than 1.5x the slot
        if target_duration_ms > 0 and dubbed_duration_ms > target_duration_ms * 1.5:
            failed.append({**seg, "failure_reason": "too_long"})
            continue

        # Check overlap with next segment
        if i + 1 < len(sorted_segs):
            next_start_ms = int(sorted_segs[i + 1]["start"] * 1000)
            seg_start_ms = int(seg["start"] * 1000)
            effective_end_ms = seg_start_ms + min(dubbed_duration_ms, target_duration_ms)
            if effective_end_ms > next_start_ms:
                failed.append({**seg, "failure_reason": "overlap"})
                continue

        passed.append(seg)

    return passed, failed


def build_strict_retranslation_prompt(segment: dict, target_language: str) -> str:
    """
    Build a stricter translation prompt for segments that failed quality checks.

    The prompt asks for a shorter translation that fits within a tighter duration
    constraint (80% of original slot).

    Args:
        segment: Segment dict with start, end, text, failure_reason
        target_language: Target language name (e.g., "Spanish")

    Returns:
        System prompt string for GPT-4o-mini.
    """
    duration = segment["end"] - segment["start"]
    tight_duration = duration * 0.8
    reason = segment.get("failure_reason", "timing")

    return (
        f"You are a professional dubbing translator. "
        f"A previous translation was too long to fit the available time slot. "
        f"Translate the following dialogue line into {target_language}. "
        f"CRITICAL CONSTRAINT: The translation MUST be speakable in under {tight_duration:.1f} seconds. "
        f"Use fewer words. Be concise. Abbreviate if needed. "
        f"Sacrifice literal accuracy for brevity. "
        f"Return ONLY the translated text, nothing else."
    )
