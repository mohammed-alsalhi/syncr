"""
Modal remote functions — 3-level container hierarchy.

Level 1: coordinator (CPU)       — chunks video, dispatches work, merges results
Level 2: process_chunk (GPU)     — per-chunk diarize + transcribe + translate
         WhisperTranscriber (GPU) — self-hosted faster-whisper, parallel segments
Level 3: synthesize_speaker (CPU) — per-speaker voice cloning + TTS
"""

import modal
from pipeline.modal_app import app, gpu_image, cpu_image, whisper_image


# ── Progress helper ───────────────────────────────────────────────────────────

_progress_dict = None


def _get_progress_dict():
    """Lazily initialize the modal.Dict reference (avoids crash at import time)."""
    global _progress_dict
    if _progress_dict is None:
        _progress_dict = modal.Dict.from_name("syncr-progress", create_if_missing=True)
    return _progress_dict


def _update_progress(job_id: str, **kwargs):
    """Write progress update to shared modal.Dict for the local orchestrator to poll."""
    try:
        progress_dict = _get_progress_dict()
        current = progress_dict.get(job_id, {})
    except Exception:
        current = {}
    current.update(kwargs)
    try:
        _get_progress_dict()[job_id] = current
    except Exception:
        pass  # Best-effort — progress updates are non-critical


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _match_speakers_across_chunks(all_segments: list[dict], chunk_results: list[dict]) -> list[dict]:
    """
    Match speakers across chunks using embedding cosine similarity.

    Each chunk has its own local speaker labels (SPEAKER_00, SPEAKER_01, etc.).
    This function compares speaker embeddings across chunks and assigns a
    global speaker ID when similarity > 0.85.

    Falls back to chunk-prefixed speaker names if embeddings are unavailable.
    """
    SIMILARITY_THRESHOLD = 0.85

    # Collect one representative embedding per (chunk, local_speaker)
    chunk_speaker_embeddings: dict[tuple[int, str], list[float]] = {}
    for cr in chunk_results:
        chunk_idx = cr["chunk_idx"]
        for seg in cr["segments"]:
            key = (chunk_idx, seg["speaker"])
            emb = seg.get("embedding", [])
            if key not in chunk_speaker_embeddings and emb:
                chunk_speaker_embeddings[key] = emb

    if not chunk_speaker_embeddings:
        # No embeddings available — prefix speaker names with chunk index to avoid collisions
        for seg in all_segments:
            for cr in chunk_results:
                if seg in cr["segments"]:
                    seg["speaker"] = f"chunk{cr['chunk_idx']}_{seg['speaker']}"
                    break
        return all_segments

    # Build global speaker clusters via greedy matching
    # global_speakers: list of {global_id, embedding, members: [(chunk_idx, local_speaker)]}
    global_speakers: list[dict] = []

    for (chunk_idx, local_speaker), emb in chunk_speaker_embeddings.items():
        matched = False
        for gs in global_speakers:
            sim = _cosine_similarity(emb, gs["embedding"])
            if sim > SIMILARITY_THRESHOLD:
                gs["members"].append((chunk_idx, local_speaker))
                matched = True
                break
        if not matched:
            global_speakers.append({
                "global_id": f"SPEAKER_{len(global_speakers):02d}",
                "embedding": emb,
                "members": [(chunk_idx, local_speaker)],
            })

    # Build lookup: (chunk_idx, local_speaker) → global_id
    speaker_map: dict[tuple[int, str], str] = {}
    for gs in global_speakers:
        for member in gs["members"]:
            speaker_map[member] = gs["global_id"]

    # Apply global IDs to all segments
    for cr in chunk_results:
        chunk_idx = cr["chunk_idx"]
        for seg in cr["segments"]:
            key = (chunk_idx, seg["speaker"])
            seg["speaker"] = speaker_map.get(key, f"chunk{chunk_idx}_{seg['speaker']}")

    # Also update the flattened list (same objects)
    return all_segments


# ── Level 3: Per-speaker synthesis (spawned in parallel) ──────────────────────

@app.function(
    image=cpu_image,
    timeout=300,
    concurrency_limit=6,
    secrets=[modal.Secret.from_name("mimic-secrets")],
)
def synthesize_speaker(
    speaker: str,
    segments: list[dict],
    sample_bytes: bytes,
    job_id: str,
) -> list[dict]:
    """
    Clone one speaker's voice and synthesize all their segments.
    Runs in its own container — one container per speaker, all in parallel.

    Returns list of dicts with dubbed_audio_bytes (bytes, not paths).
    """
    import asyncio
    import os
    import aiohttp

    ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"
    api_key = os.environ["ELEVENLABS_API_KEY"]

    async def _run():
        async with aiohttp.ClientSession() as session:
            # Clone voice
            headers = {"xi-api-key": api_key}
            form = aiohttp.FormData()
            form.add_field("name", f"{job_id}_{speaker}")
            form.add_field("files", sample_bytes, filename=f"{speaker}.wav", content_type="audio/wav")
            async with session.post(f"{ELEVENLABS_BASE}/voices/add", headers=headers, data=form) as resp:
                resp.raise_for_status()
                voice_id = (await resp.json())["voice_id"]

            # Synthesize all segments for this speaker
            results = []
            for seg in segments:
                if not seg.get("translated_text", "").strip():
                    continue

                payload = {
                    "text": seg["translated_text"],
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                }
                headers_tts = {
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                }
                async with session.post(
                    f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}",
                    headers=headers_tts, json=payload,
                ) as resp:
                    resp.raise_for_status()
                    audio_bytes = await resp.read()

                results.append({
                    "speaker": seg["speaker"],
                    "start": seg["start"],
                    "end": seg["end"],
                    "translated_text": seg["translated_text"],
                    "dubbed_audio_bytes": audio_bytes,
                })

            # Cleanup: delete cloned voice (free tier has 3 voice limit)
            async with session.delete(
                f"{ELEVENLABS_BASE}/voices/{voice_id}", headers={"xi-api-key": api_key}
            ) as resp:
                pass  # best-effort

            return results

    return asyncio.run(_run())


# ── Level 2: Self-hosted Whisper transcription (GPU) ──────────────────────────

@app.cls(
    image=whisper_image,
    gpu="T4",
    timeout=300,
    concurrency_limit=4,
)
class WhisperTranscriber:
    """
    Self-hosted faster-whisper on T4 GPU.
    Model loaded once via @modal.enter(), reused across segments.
    Called via .map() for parallel transcription across segments.
    """

    @modal.enter()
    def load_model(self):
        from faster_whisper import WhisperModel
        self.model = WhisperModel("medium", device="cuda", compute_type="float16")

    @modal.method()
    def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe a single audio segment. Accepts bytes, returns text."""
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        try:
            segments_iter, _info = self.model.transcribe(tmp_path, beam_size=5)
            text = " ".join(seg.text for seg in segments_iter)
            return text.strip()
        finally:
            os.unlink(tmp_path)


# ── Level 2: Per-chunk processing (GPU) ───────────────────────────────────────

@app.function(
    image=gpu_image,
    gpu="T4",
    timeout=600,
    concurrency_limit=6,
    secrets=[modal.Secret.from_name("mimic-secrets")],
)
def process_chunk(
    chunk_video_bytes: bytes,
    chunk_idx: int,
    chunk_start: float,
    total_chunks: int,
    target_language: str,
    job_id: str,
) -> dict:
    """
    Process one video chunk through diarize → transcribe → translate.

    Runs on GPU for pyannote diarization. Transcription dispatched to
    WhisperTranscriber containers via .map() for parallelism.

    Returns dict with:
      - chunk_idx, start, end
      - segments: list of dicts with speaker, start, end, text, translated_text,
        audio_bytes (voice sample for synthesis)
    """
    import tempfile
    import os
    import time

    with tempfile.TemporaryDirectory() as tmpdir:
        # Save chunk video
        input_path = os.path.join(tmpdir, f"chunk_{chunk_idx:04d}.mp4")
        with open(input_path, "wb") as f:
            f.write(chunk_video_bytes)

        # ── Step 1: Extract audio ──
        _update_progress(
            job_id,
            step=f"Extracting audio (chunk {chunk_idx + 1}/{total_chunks})...",
            current_chunk=chunk_idx,
        )
        from pipeline.extract import extract_audio
        audio_path = extract_audio(input_path, f"chunk{chunk_idx}", tmpdir)

        # ── Step 2: Diarize speakers ──
        t0 = time.time()
        _update_progress(
            job_id,
            step=f"Diarizing speakers (chunk {chunk_idx + 1}/{total_chunks})...",
        )
        from pipeline.diarize import diarize_speakers
        segments = diarize_speakers(audio_path, tmpdir)
        diarize_time = time.time() - t0

        _update_progress(
            job_id,
            segments_found=(segments and len(segments)) or 0,
            speakers_found=len(set(s["speaker"] for s in segments)) if segments else 0,
        )

        # ── Step 3: Transcribe via self-hosted Whisper ──
        t0 = time.time()
        _update_progress(
            job_id,
            step=f"Transcribing speech (chunk {chunk_idx + 1}/{total_chunks})...",
        )

        # Read all segment audio into bytes for cross-container transfer
        segment_audio_bytes = []
        for seg in segments:
            with open(seg["audio_path"], "rb") as f:
                segment_audio_bytes.append(f.read())

        # Parallel transcription across WhisperTranscriber GPU containers
        transcriber = WhisperTranscriber()
        transcriptions = list(transcriber.transcribe.map(segment_audio_bytes))

        for seg, text in zip(segments, transcriptions):
            seg["text"] = text

        transcribe_time = time.time() - t0

        # ── Step 4: Translate with context ──
        t0 = time.time()
        _update_progress(
            job_id,
            step=f"Translating dialogue (chunk {chunk_idx + 1}/{total_chunks})...",
        )
        from pipeline.translate import translate_segments_with_context
        segments = translate_segments_with_context(segments, target_language)
        translate_time = time.time() - t0

        # ── Prepare results ──
        # Convert timestamps from chunk-relative to absolute (original video time)
        # Also read audio samples for voice cloning
        result_segments = []
        for seg in segments:
            # Read audio bytes for voice cloning sample
            audio_bytes = b""
            if os.path.exists(seg.get("audio_path", "")):
                with open(seg["audio_path"], "rb") as f:
                    audio_bytes = f.read()

            result_segments.append({
                "speaker": seg["speaker"],
                "start": round(seg["start"] + chunk_start, 3),  # absolute time
                "end": round(seg["end"] + chunk_start, 3),
                "text": seg.get("text", ""),
                "translated_text": seg.get("translated_text", ""),
                "audio_bytes": audio_bytes,  # for voice cloning
                "embedding": seg.get("embedding", []),  # for cross-chunk speaker matching
            })

        return {
            "chunk_idx": chunk_idx,
            "start": chunk_start,
            "segments": result_segments,
            "timings": {
                "diarize": round(diarize_time, 1),
                "transcribe": round(transcribe_time, 1),
                "translate": round(translate_time, 1),
            },
        }


# ── Level 1: Coordinator (CPU) ────────────────────────────────────────────────

@app.function(
    image=cpu_image,
    timeout=900,
    concurrency_limit=2,
    secrets=[modal.Secret.from_name("mimic-secrets")],
)
def coordinator(video_bytes: bytes, target_language: str, job_id: str) -> bytes:
    """
    Top-level coordinator. Chunks video, dispatches parallel processing,
    matches speakers across chunks, runs synthesis, merges final output.

    Called by the local orchestrator via .remote().
    Returns the final dubbed video as bytes.
    """
    import tempfile
    import os
    import time

    with tempfile.TemporaryDirectory() as tmpdir:
        # Save input video
        input_path = os.path.join(tmpdir, "input.mp4")
        with open(input_path, "wb") as f:
            f.write(video_bytes)

        # ── Phase 1: Chunk the video ──
        _update_progress(job_id, status="running", step="Analyzing video structure...", progress=2)

        from pipeline.chunk import detect_scenes, split_video
        scenes = detect_scenes(input_path)
        chunks = split_video(input_path, scenes, max_chunk_duration=300.0, work_dir=tmpdir)

        total_chunks = len(chunks)
        _update_progress(
            job_id,
            step=f"Processing {total_chunks} chunk(s) in parallel...",
            progress=5,
            total_chunks=total_chunks,
            completed_chunks=0,
            containers_total=total_chunks,
        )

        # ── Phase 2: Dispatch chunks in parallel ──
        handles = []
        for chunk in chunks:
            with open(chunk["video_path"], "rb") as f:
                chunk_bytes = f.read()
            handle = process_chunk.spawn(
                chunk_bytes,
                chunk["chunk_idx"],
                chunk["start"],
                total_chunks,
                target_language,
                job_id,
            )
            handles.append((chunk, handle))

        # Collect results as they complete
        chunk_results = []
        for i, (chunk_info, handle) in enumerate(handles):
            result = handle.get()
            result["end"] = chunk_info["end"]
            chunk_results.append(result)

            _update_progress(
                job_id,
                completed_chunks=i + 1,
                progress=10 + int(50 * (i + 1) / total_chunks),
                step=f"Chunk {i + 1}/{total_chunks} complete",
            )

        # ── Phase 3: Match speakers across chunks via embeddings ──
        _update_progress(job_id, step="Matching speakers across chunks...", progress=62)

        # Flatten all segments
        all_segments = []
        for cr in sorted(chunk_results, key=lambda c: c["chunk_idx"]):
            all_segments.extend(cr["segments"])

        # Build global speaker identity via embedding cosine similarity
        all_segments = _match_speakers_across_chunks(all_segments, chunk_results)

        # Group by global speaker
        speakers: dict[str, list[dict]] = {}
        for seg in all_segments:
            speakers.setdefault(seg["speaker"], []).append(seg)

        # Find best voice sample per speaker (longest clip)
        speaker_samples: dict[str, bytes] = {}
        for spk, segs in speakers.items():
            best = max(segs, key=lambda s: s["end"] - s["start"])
            speaker_samples[spk] = best.get("audio_bytes", b"")

        # ── Phase 4: Synthesize per speaker (parallel) ──
        _update_progress(
            job_id,
            step=f"Cloning {len(speakers)} voice(s) and synthesizing...",
            progress=65,
            speakers_found=len(speakers),
            containers_active=len(speakers),
        )

        synth_handles = []
        for spk, segs in speakers.items():
            # Strip audio_bytes before sending to synth (not needed there)
            clean_segs = [
                {k: v for k, v in s.items() if k != "audio_bytes"}
                for s in segs
            ]
            handle = synthesize_speaker.spawn(spk, clean_segs, speaker_samples[spk], job_id)
            synth_handles.append(handle)

        # Collect synthesis results
        dub_dir = os.path.join(tmpdir, "dubbed")
        os.makedirs(dub_dir, exist_ok=True)

        synthesized_segments = []
        for handle in synth_handles:
            speaker_results = handle.get()
            for i, seg in enumerate(speaker_results):
                dub_path = os.path.join(dub_dir, f"dub_{seg['speaker']}_{i:04d}.mp3")
                with open(dub_path, "wb") as f:
                    f.write(seg["dubbed_audio_bytes"])
                synthesized_segments.append({
                    "speaker": seg["speaker"],
                    "start": seg["start"],
                    "end": seg["end"],
                    "translated_text": seg.get("translated_text", ""),
                    "dubbed_audio_path": dub_path,
                })

        # ── Phase 5: Quality verification + retry loop ──
        _update_progress(
            job_id,
            step="Verifying synthesis quality...",
            progress=80,
            containers_active=0,
        )

        from pipeline.quality import verify_segments, build_strict_retranslation_prompt
        from pipeline.translate import LANGUAGE_NAMES

        MAX_RETRIES = 2
        lang_name = LANGUAGE_NAMES.get(target_language, target_language)

        for retry_round in range(MAX_RETRIES):
            passed, failed = verify_segments(synthesized_segments)

            if not failed:
                break

            _update_progress(
                job_id,
                step=f"Re-processing {len(failed)} segment(s) (round {retry_round + 1})...",
                progress=82 + retry_round,
            )

            # Re-translate failed segments with stricter constraints
            from openai import OpenAI
            client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

            for seg in failed:
                # Look up original source text from all_segments for re-translation
                original_text = seg.get("translated_text", "")
                # Find the matching original segment to get source language text
                for orig in all_segments:
                    if orig["speaker"] == seg["speaker"] and abs(orig["start"] - seg["start"]) < 0.01:
                        original_text = orig.get("text", original_text)
                        break
                if not original_text:
                    continue

                prompt = build_strict_retranslation_prompt(seg, lang_name)
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": original_text},
                    ],
                    max_tokens=300,
                    temperature=0.2,
                )
                seg["translated_text"] = response.choices[0].message.content.strip()

            # Re-synthesize failed segments
            # Group by speaker, reuse existing voice samples
            failed_by_speaker: dict[str, list[dict]] = {}
            for seg in failed:
                failed_by_speaker.setdefault(seg["speaker"], []).append(seg)

            retry_handles = []
            for spk, segs in failed_by_speaker.items():
                clean_segs = [
                    {k: v for k, v in s.items() if k not in ("audio_bytes", "dubbed_audio_path", "failure_reason")}
                    for s in segs
                ]
                sample = speaker_samples.get(spk, b"")
                retry_handles.append(synthesize_speaker.spawn(spk, clean_segs, sample, job_id))

            # Collect retry results and update synthesized_segments
            retry_results = []
            for handle in retry_handles:
                speaker_results = handle.get()
                for i, seg in enumerate(speaker_results):
                    dub_path = os.path.join(dub_dir, f"retry_{seg['speaker']}_{retry_round}_{i:04d}.mp3")
                    with open(dub_path, "wb") as f:
                        f.write(seg["dubbed_audio_bytes"])
                    retry_results.append({
                        "speaker": seg["speaker"],
                        "start": seg["start"],
                        "end": seg["end"],
                        "translated_text": seg.get("translated_text", ""),
                        "dubbed_audio_path": dub_path,
                    })

            # Replace failed segments with retry results
            failed_keys = {(s["speaker"], s["start"]) for s in failed}
            synthesized_segments = [
                s for s in synthesized_segments
                if (s["speaker"], s["start"]) not in failed_keys
            ] + retry_results

        # Final verification for logging
        final_passed, final_failed = verify_segments(synthesized_segments)
        _update_progress(
            job_id,
            step=f"Quality check: {len(final_passed)}/{len(final_passed) + len(final_failed)} passed",
            progress=85,
        )

        # ── Phase 6: Merge chunks into final video ──
        _update_progress(
            job_id,
            step="Compositing final video...",
            progress=88,
        )
        # Build chunk_results format expected by merge_chunks
        merge_input = []
        for cr in sorted(chunk_results, key=lambda c: c["chunk_idx"]):
            # Find synthesized segments that belong to this chunk's time range
            chunk_synth = [
                s for s in synthesized_segments
                if s["start"] >= cr["start"] and s["start"] < cr.get("end", float("inf"))
            ]
            merge_input.append({
                "chunk_idx": cr["chunk_idx"],
                "start": cr["start"],
                "end": cr.get("end", 0),
                "segments": chunk_synth,
            })

        from pipeline.merge import merge_chunks
        output_dir = os.path.join(tmpdir, "output")
        output_path = merge_chunks(input_path, merge_input, job_id, output_dir)

        _update_progress(job_id, step="Done!", progress=100, status="done")

        # Build transcript preview for frontend
        transcript = [
            {
                "speaker": s["speaker"],
                "start": s["start"],
                "end": s["end"],
                "text": s.get("text", ""),
                "translated_text": s.get("translated_text", ""),
            }
            for s in all_segments
        ]
        _update_progress(job_id, transcript_preview=transcript)

        with open(output_path, "rb") as f:
            return f.read()
