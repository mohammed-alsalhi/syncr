"""
Step 2: Speaker diarization using pyannote.audio.
Identifies who speaks when, splits audio into per-segment clips,
and extracts speaker embeddings for cross-chunk matching.
"""

import os


def diarize_speakers(audio_path: str, work_dir: str = "/tmp") -> list[dict]:
    """
    Run speaker diarization on audio and split into per-segment clips.

    Also computes a representative embedding per speaker using pyannote's
    embedding model, stored in the segment dicts for cross-chunk speaker
    matching by the coordinator.

    Args:
        audio_path: Path to WAV audio file (16kHz mono)
        work_dir:   Directory to write segment audio files

    Returns:
        List of segment dicts sorted by start time:
        [{"speaker": "SPEAKER_00", "start": 0.5, "end": 3.2,
          "audio_path": "...", "embedding": [0.1, 0.2, ...]}]
    """
    import torch
    import numpy as np
    from pyannote.audio import Pipeline, Inference
    from pydub import AudioSegment

    hf_token = os.environ["HF_TOKEN"]

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=hf_token,
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    pipeline.to(device)

    diarization = pipeline(audio_path)

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

    # ── Extract speaker embeddings ──
    # Use pyannote's embedding model to compute a representative vector
    # per speaker. The coordinator uses these for cross-chunk matching.
    try:
        embedding_model = Inference(
            "pyannote/wespeaker-voxceleb-resnet34-LM",
            token=hf_token,
            window="whole",
        )
        embedding_model.to(device)

        # Compute embedding from the longest segment per speaker
        speaker_best_seg: dict[str, dict] = {}
        for seg in segments:
            spk = seg["speaker"]
            if spk not in speaker_best_seg or (seg["end"] - seg["start"]) > (speaker_best_seg[spk]["end"] - speaker_best_seg[spk]["start"]):
                speaker_best_seg[spk] = seg

        speaker_embeddings: dict[str, list[float]] = {}
        for spk, seg in speaker_best_seg.items():
            emb = embedding_model(seg["audio_path"])
            # pyannote returns a numpy array
            if isinstance(emb, np.ndarray):
                speaker_embeddings[spk] = emb.tolist()
            else:
                speaker_embeddings[spk] = list(emb)

        # Attach embedding to each segment
        for seg in segments:
            seg["embedding"] = speaker_embeddings.get(seg["speaker"], [])

    except Exception:
        # Embedding extraction is best-effort — if it fails, segments
        # still work, just without cross-chunk matching capability
        for seg in segments:
            seg["embedding"] = []

    return segments
