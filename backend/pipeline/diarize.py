"""
Step 2: Speaker diarization using pyannote.audio.
Identifies who speaks when and splits audio into per-segment clips.
"""

import os


def diarize_speakers(audio_path: str, work_dir: str = "/tmp") -> list[dict]:
    """
    Run speaker diarization on audio and split into per-segment clips.

    Args:
        audio_path: Path to WAV audio file (16kHz mono)
        work_dir:   Directory to write segment audio files

    Returns:
        List of segment dicts sorted by start time:
        [{"speaker": "SPEAKER_00", "start": 0.5, "end": 3.2, "audio_path": "..."}]

    Raises:
        RuntimeError: If pyannote model fails to load (bad HF_TOKEN or no model access)
    """
    import torch
    from pyannote.audio import Pipeline
    from pydub import AudioSegment

    hf_token = os.environ["HF_TOKEN"]

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=hf_token,
    )

    if torch.cuda.is_available():
        pipeline.to(torch.device("cuda"))

    output = pipeline(audio_path)

    # pyannote 4.x returns DiarizeOutput; extract the Annotation object
    if hasattr(output, "speaker_diarization"):
        diarization = output.speaker_diarization
    else:
        diarization = output

    full_audio = AudioSegment.from_wav(audio_path)

    segments = []
    seg_dir = os.path.join(work_dir, "segments")
    os.makedirs(seg_dir, exist_ok=True)

    for i, (turn, _, speaker) in enumerate(diarization.itertracks(yield_label=True)):
        start = turn.start
        end = turn.end

        # Skip very short segments (< 0.5s) — usually noise
        if end - start < 0.5:
            continue

        clip = full_audio[int(start * 1000):int(end * 1000)]
        seg_path = os.path.join(seg_dir, f"seg_{i:04d}_{speaker}.wav")
        clip.export(seg_path, format="wav")

        segments.append({
            "speaker": speaker,
            "start": round(start, 3),
            "end": round(end, 3),
            "audio_path": seg_path,
        })

    segments.sort(key=lambda s: s["start"])
    return segments
