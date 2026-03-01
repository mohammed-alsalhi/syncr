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
    # Set HF tokens BEFORE importing any huggingface/pyannote modules.
    # Some huggingface_hub versions read the token at import time.
    # Set both env var names for compatibility across library versions.
    hf_token = os.environ["HF_TOKEN"]
    os.environ["HUGGING_FACE_HUB_TOKEN"] = hf_token

    import torch
    import numpy as np
    from pyannote.audio import Pipeline, Inference
    from pydub import AudioSegment
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    pipeline.to(device)

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

    # ── Extract speaker embeddings ──
    # Use pyannote's embedding model to compute a representative vector
    # per speaker. The coordinator uses these for cross-chunk matching.
    # Average embeddings across up to 3 longest segments per speaker for
    # robustness — a single segment may be an outlier (whisper, shout, etc).
    try:
        embedding_model = Inference(
            "pyannote/wespeaker-voxceleb-resnet34-LM",
            window="whole",
        )
        embedding_model.to(device)

        # Collect top-3 longest segments per speaker (>= 1s to avoid noise)
        speaker_segs: dict[str, list[dict]] = {}
        for seg in segments:
            spk = seg["speaker"]
            if (seg["end"] - seg["start"]) >= 1.0:
                speaker_segs.setdefault(spk, []).append(seg)

        # Fallback: if no segments >= 1s, use all segments
        for seg in segments:
            spk = seg["speaker"]
            if spk not in speaker_segs:
                speaker_segs.setdefault(spk, []).append(seg)

        speaker_embeddings: dict[str, list[float]] = {}
        for spk, segs_list in speaker_segs.items():
            # Sort by duration, take top 3
            top_segs = sorted(segs_list, key=lambda s: s["end"] - s["start"], reverse=True)[:3]
            embeddings = []
            for seg in top_segs:
                emb = embedding_model(seg["audio_path"])
                if isinstance(emb, np.ndarray):
                    emb_list = emb.tolist()
                else:
                    emb_list = list(emb)
                embeddings.append(emb_list)

            # Average embeddings and normalize to unit length
            if embeddings:
                dim = len(embeddings[0])
                avg = [sum(e[d] for e in embeddings) / len(embeddings) for d in range(dim)]
                # Normalize to unit length
                norm = sum(x * x for x in avg) ** 0.5
                if norm > 0:
                    avg = [x / norm for x in avg]
                speaker_embeddings[spk] = avg

        # Attach embedding to each segment
        for seg in segments:
            seg["embedding"] = speaker_embeddings.get(seg["speaker"], [])

    except Exception:
        # Embedding extraction is best-effort — if it fails, segments
        # still work, just without cross-chunk matching capability
        for seg in segments:
            seg["embedding"] = []

    return segments
