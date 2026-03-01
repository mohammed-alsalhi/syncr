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


def _normalize_embedding(emb: list[float]) -> list[float]:
    """Normalize an embedding vector to unit length for reliable cosine similarity."""
    if not emb:
        return emb
    norm = sum(x * x for x in emb) ** 0.5
    if norm == 0:
        return emb
    return [x / norm for x in emb]


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


def _merge_similar_speakers(segments: list[dict], threshold: float = 0.78) -> list[dict]:
    """
    Merge over-segmented speakers within a single chunk using embedding similarity.

    Pyannote sometimes splits one real speaker into multiple labels (e.g. finding
    5 speakers when there are only 3). Uses agglomerative clustering with complete
    linkage — only merges two clusters when ALL pairs between them exceed the
    similarity threshold — to avoid cascading merge errors.

    Uses a lower threshold than cross-chunk matching (0.78 vs 0.80) because
    within-chunk embeddings come from identical audio conditions, so same-speaker
    pairs have naturally higher similarity scores.

    Args:
        segments: List of segment dicts from diarize_speakers(), each with
                  "speaker", "start", "end", "audio_path", "embedding" keys.
        threshold: Cosine similarity threshold for merging (default 0.78).

    Returns:
        Same segments with speaker labels renumbered after merging.
    """
    if not segments:
        return segments

    # Collect representative embedding per local speaker (normalized, from longest segment)
    speaker_embeddings: dict[str, list[float]] = {}
    speaker_durations: dict[str, float] = {}
    for seg in segments:
        spk = seg["speaker"]
        emb = seg.get("embedding", [])
        dur = seg["end"] - seg["start"]
        if emb and (spk not in speaker_embeddings or dur > speaker_durations.get(spk, 0)):
            speaker_embeddings[spk] = _normalize_embedding(emb)
            speaker_durations[spk] = dur

    if len(speaker_embeddings) <= 1:
        return segments  # Nothing to merge

    # Agglomerative clustering with complete linkage.
    # Start with each speaker in its own cluster. Repeatedly merge the two
    # most similar clusters, but only if ALL pairwise similarities exceed threshold.
    # This prevents cascading merges that drag embeddings away from true identity.
    speakers = list(speaker_embeddings.keys())
    # clusters: list of sets of speaker labels, with a fixed representative embedding
    # (the embedding of the longest-duration speaker in the cluster — no averaging/drift)
    clusters: list[dict] = []
    for spk in speakers:
        clusters.append({
            "members": {spk},
            "embedding": speaker_embeddings[spk],  # Fixed, no drift
        })

    # Iteratively merge most-similar pair above threshold
    changed = True
    while changed and len(clusters) > 1:
        changed = False
        best_sim = -1.0
        best_i, best_j = -1, -1

        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                # Complete linkage: minimum similarity across all pairs
                min_sim = float("inf")
                for spk_a in clusters[i]["members"]:
                    for spk_b in clusters[j]["members"]:
                        sim = _cosine_similarity(speaker_embeddings[spk_a], speaker_embeddings[spk_b])
                        min_sim = min(min_sim, sim)
                if min_sim > best_sim:
                    best_sim = min_sim
                    best_i, best_j = i, j

        if best_sim > threshold and best_i >= 0:
            # Merge j into i, keep the embedding of the longest-duration member
            merged_members = clusters[best_i]["members"] | clusters[best_j]["members"]
            # Pick embedding from the member with the most total speech
            best_spk = max(merged_members, key=lambda s: speaker_durations.get(s, 0))
            clusters[best_i]["members"] = merged_members
            clusters[best_i]["embedding"] = speaker_embeddings[best_spk]
            clusters.pop(best_j)
            changed = True

    # Build mapping: old speaker label → new merged label
    speaker_map: dict[str, str] = {}
    for idx, cluster in enumerate(clusters):
        label = f"SPEAKER_{idx:02d}"
        for member in cluster["members"]:
            speaker_map[member] = label

    # Relabel segments and update embeddings (use cluster's fixed embedding)
    for seg in segments:
        old_spk = seg["speaker"]
        seg["speaker"] = speaker_map.get(old_spk, old_spk)
        for cluster in clusters:
            if old_spk in cluster["members"]:
                seg["embedding"] = cluster["embedding"]
                break

    return segments


def _match_speakers_across_chunks(all_segments: list[dict], chunk_results: list[dict]) -> list[dict]:
    """
    Match speakers across chunks using embedding cosine similarity.

    Each chunk has its own local speaker labels (SPEAKER_00, SPEAKER_01, etc.).
    This function compares speaker embeddings across chunks and assigns a
    global speaker ID using optimal bipartite matching (Hungarian algorithm)
    rather than greedy first-match, preventing incorrect speaker merges.

    Falls back to chunk-prefixed speaker names if embeddings are unavailable.
    """
    SIMILARITY_THRESHOLD = 0.80

    # Collect one representative embedding per (chunk, local_speaker), normalized
    chunk_speaker_embeddings: dict[tuple[int, str], list[float]] = {}
    for cr in chunk_results:
        chunk_idx = cr["chunk_idx"]
        for seg in cr["segments"]:
            key = (chunk_idx, seg["speaker"])
            emb = seg.get("embedding", [])
            if key not in chunk_speaker_embeddings and emb:
                chunk_speaker_embeddings[key] = _normalize_embedding(emb)

    if not chunk_speaker_embeddings:
        # No embeddings available — prefix speaker names with chunk index to avoid collisions
        for seg in all_segments:
            for cr in chunk_results:
                if seg in cr["segments"]:
                    seg["speaker"] = f"chunk{cr['chunk_idx']}_{seg['speaker']}"
                    break
        return all_segments

    # Build global speaker clusters using iterative optimal matching.
    # Process chunks in order. For each new chunk, compute the full similarity
    # matrix between the chunk's speakers and existing global clusters, then
    # use the Hungarian algorithm to find the optimal assignment.
    from scipy.optimize import linear_sum_assignment

    # global_speakers: list of {global_id, embedding, members: [(chunk_idx, local_speaker)]}
    global_speakers: list[dict] = []

    # Group speakers by chunk
    speakers_by_chunk: dict[int, list[tuple[tuple[int, str], list[float]]]] = {}
    for (chunk_idx, local_speaker), emb in chunk_speaker_embeddings.items():
        speakers_by_chunk.setdefault(chunk_idx, []).append(((chunk_idx, local_speaker), emb))

    for chunk_idx in sorted(speakers_by_chunk.keys()):
        chunk_speakers = speakers_by_chunk[chunk_idx]

        if not global_speakers:
            # First chunk: all speakers become new global speakers
            for (key, emb) in chunk_speakers:
                global_speakers.append({
                    "global_id": f"SPEAKER_{len(global_speakers):02d}",
                    "embedding": emb,
                    "members": [key],
                })
            continue

        # Build cost matrix: rows = chunk speakers, cols = global speakers
        # Cost = 1 - similarity (lower = better match)
        n_chunk = len(chunk_speakers)
        n_global = len(global_speakers)

        cost_matrix = []
        for (key, emb) in chunk_speakers:
            row = []
            for gs in global_speakers:
                sim = _cosine_similarity(emb, gs["embedding"])
                row.append(1.0 - sim)
            cost_matrix.append(row)

        # Pad cost matrix to square if needed (more chunk speakers than global)
        # Extra columns represent "new speaker" with cost = 1 - threshold
        new_speaker_cost = 1.0 - SIMILARITY_THRESHOLD
        max_dim = max(n_chunk, n_global)
        padded_cost = []
        for i in range(max_dim):
            row = []
            for j in range(max_dim):
                if i < n_chunk and j < n_global:
                    row.append(cost_matrix[i][j])
                else:
                    row.append(new_speaker_cost)
            padded_cost.append(row)

        row_ind, col_ind = linear_sum_assignment(padded_cost)

        for r, c in zip(row_ind, col_ind):
            if r >= n_chunk:
                continue  # Padding row, skip
            key, emb = chunk_speakers[r]
            if c < n_global:
                sim = _cosine_similarity(emb, global_speakers[c]["embedding"])
                if sim > SIMILARITY_THRESHOLD:
                    global_speakers[c]["members"].append(key)
                    print(f"[match] {key} → {global_speakers[c]['global_id']} (sim={sim:.3f})")
                    continue
            # No match above threshold — create new global speaker
            global_speakers.append({
                "global_id": f"SPEAKER_{len(global_speakers):02d}",
                "embedding": emb,
                "members": [key],
            })
            print(f"[match] {key} → new {global_speakers[-1]['global_id']}")

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
    max_containers=6,
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
    import io
    import aiohttp

    ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"
    api_key = os.environ["ELEVENLABS_API_KEY"]

    async def _run():
        async with aiohttp.ClientSession() as session:
            headers = {"xi-api-key": api_key}

            # Pre-cleanup: delete cloned voices from PREVIOUS jobs only.
            # Free tier allows only ~3 cloned voices. If a prior job crashed
            # before cleanup, those voices are still on the account.
            # Only delete voices whose name does NOT start with the current
            # job_id — otherwise parallel containers would delete each other's voices.
            try:
                async with session.get(f"{ELEVENLABS_BASE}/voices", headers=headers) as resp:
                    if resp.status == 200:
                        voices_data = await resp.json()
                        for v in voices_data.get("voices", []):
                            if v.get("category") == "cloned" and not v.get("name", "").startswith(job_id):
                                await session.delete(
                                    f"{ELEVENLABS_BASE}/voices/{v['voice_id']}",
                                    headers=headers,
                                )
            except Exception:
                pass  # best-effort pre-cleanup

            # Validate and fix voice sample before sending to ElevenLabs.
            # Defense-in-depth: no matter what bytes arrive from the coordinator,
            # ensure the sample meets ElevenLabs' minimum requirements.
            from pydub import AudioSegment as _Seg
            try:
                sample_audio = _Seg.from_file(io.BytesIO(sample_bytes))
                sample_dur = len(sample_audio)
            except Exception:
                sample_dur = 0
                sample_audio = _Seg.silent(duration=0)

            print(f"[synth] {speaker}: received {len(sample_bytes)} bytes, decoded {sample_dur}ms")

            if sample_dur < 1500:
                # Pad with silence to reach 2 seconds
                pad_needed = 2000 - sample_dur
                sample_audio = sample_audio + _Seg.silent(duration=pad_needed)
                print(f"[synth] {speaker}: padded to {len(sample_audio)}ms")

            # Re-export as mono WAV at 44.1kHz for consistency
            sample_audio = sample_audio.set_channels(1).set_frame_rate(44100)
            fixed_buf = io.BytesIO()
            sample_audio.export(fixed_buf, format="wav")
            fixed_bytes = fixed_buf.getvalue()
            print(f"[synth] {speaker}: sending {len(fixed_bytes)} bytes ({len(sample_audio)}ms mono 44.1kHz)")

            # Clone voice
            form = aiohttp.FormData()
            form.add_field("name", f"{job_id}_{speaker}")
            form.add_field("files", fixed_bytes, filename=f"{speaker}.wav", content_type="audio/wav")

            async with session.post(f"{ELEVENLABS_BASE}/voices/add", headers=headers, data=form) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(
                        f"ElevenLabs voice clone failed ({resp.status}): {body}"
                    )
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
                    if resp.status != 200:
                        body = await resp.text()
                        raise RuntimeError(
                            f"ElevenLabs TTS failed ({resp.status}): {body}"
                        )
                    audio_bytes = await resp.read()

                results.append({
                    "speaker": seg["speaker"],
                    "start": seg["start"],
                    "end": seg["end"],
                    "translated_text": seg["translated_text"],
                    "dubbed_audio_bytes": audio_bytes,
                })

            # Cleanup: delete cloned voice (free tier has 3 voice limit)
            try:
                await session.delete(
                    f"{ELEVENLABS_BASE}/voices/{voice_id}", headers=headers,
                )
            except Exception:
                pass  # best-effort

            return results

    return asyncio.run(_run())


# ── Level 2: Self-hosted Whisper transcription (GPU) ──────────────────────────

@app.cls(
    image=whisper_image,
    gpu="T4",
    timeout=300,
    max_containers=4,
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
    max_containers=6,
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

        # Merge over-segmented speakers using embedding similarity.
        # pyannote often splits one real speaker into multiple labels;
        # this reduces e.g. 5 detected speakers to the actual 3.
        segments = _merge_similar_speakers(segments)
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


# ── Source separation (GPU, Demucs) ───────────────────────────────────────────

@app.function(
    image=gpu_image,
    gpu="T4",
    timeout=600,
    max_containers=2,
)
def separate_audio(audio_bytes: bytes) -> bytes:
    """
    Separate vocals from accompaniment using Meta's Demucs (htdemucs model).

    Takes the full original audio as bytes and returns only the accompaniment
    (no_vocals) as WAV bytes. The accompaniment preserves background music,
    sound effects, and ambient sound while removing the original speaker voices.

    This runs on the FULL audio (not per-chunk) because Demucs produces
    better separation with complete context.

    Uses the demucs CLI via subprocess because demucs.api is not available
    in the PyPI release (4.0.1) — it only exists on the unreleased GitHub main branch.
    """
    import tempfile
    import subprocess
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, "input.wav")
        with open(input_path, "wb") as f:
            f.write(audio_bytes)

        output_dir = os.path.join(tmpdir, "separated")

        # --two-stems=vocals: split into vocals + no_vocals (accompaniment)
        # More efficient than full 4-stem separation — gives us exactly what we need.
        subprocess.run([
            "python", "-m", "demucs",
            "--two-stems=vocals",
            "-n", "htdemucs",
            "-d", "cuda",
            "-o", output_dir,
            input_path,
        ], check=True)

        # Demucs outputs to: {output_dir}/htdemucs/{stem_name}/no_vocals.wav
        accompaniment_path = os.path.join(output_dir, "htdemucs", "input", "no_vocals.wav")

        with open(accompaniment_path, "rb") as f:
            return f.read()


# ── Level 1: Coordinator (CPU) ────────────────────────────────────────────────

@app.function(
    image=cpu_image,
    timeout=900,
    max_containers=2,
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
    import io
    import time

    with tempfile.TemporaryDirectory() as tmpdir:
        # Save input video
        input_path = os.path.join(tmpdir, "input.mp4")
        with open(input_path, "wb") as f:
            f.write(video_bytes)

        # ── Phase 1: Extract audio + chunk video + source separation (parallel) ──
        _update_progress(job_id, status="running", step="Analyzing video structure...", progress=2)

        # Extract full-quality audio (44.1kHz stereo) for Demucs source separation.
        # This is separate from the 16kHz mono extraction in process_chunk
        # which is optimized for speech recognition.
        import subprocess
        full_audio_path = os.path.join(tmpdir, "full_audio.wav")
        subprocess.run([
            "ffmpeg", "-y", "-i", input_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "44100",
            full_audio_path,
        ], check=True, capture_output=True)

        with open(full_audio_path, "rb") as f:
            full_audio_bytes = f.read()

        # Spawn Demucs source separation in parallel with chunking.
        # Demucs removes original voices, keeping only music/effects/ambient.
        _update_progress(job_id, step="Separating background audio...", progress=3)
        demucs_handle = separate_audio.spawn(full_audio_bytes)

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
            containers_total=total_chunks + 1,  # +1 for Demucs container
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

        # Extract voice samples from the 44.1kHz WAV already extracted in Phase 1.
        # ElevenLabs requires samples >= 1 second, so we concatenate segments
        # from the same speaker until we reach at least 1.5 seconds.
        from pydub import AudioSegment as _AudioSeg

        original_audio = _AudioSeg.from_wav(full_audio_path)
        print(f"[coordinator] Original audio loaded: {len(original_audio)}ms, "
              f"{original_audio.channels}ch, {original_audio.frame_rate}Hz")

        speaker_samples: dict[str, bytes] = {}
        for spk, segs in speakers.items():
            sorted_segs = sorted(segs, key=lambda s: s["end"] - s["start"], reverse=True)
            clip = _AudioSeg.empty()
            for s in sorted_segs:
                start_ms = int(s["start"] * 1000)
                end_ms = int(s["end"] * 1000)
                seg_clip = original_audio[start_ms:end_ms]
                print(f"[coordinator]   {spk} seg {s['start']:.1f}-{s['end']:.1f}s -> {len(seg_clip)}ms")
                clip += seg_clip
                if len(clip) >= 4000:  # 4s — ElevenLabs clones best at 3-5s
                    break

            # Write to a temp WAV file and read back (more reliable than BytesIO)
            sample_path = os.path.join(tmpdir, f"voice_sample_{spk}.wav")
            clip.export(sample_path, format="wav")
            with open(sample_path, "rb") as f:
                speaker_samples[spk] = f.read()
            print(f"[coordinator] Voice sample for {spk}: {len(clip)}ms, "
                  f"{len(speaker_samples[spk])} bytes, file={sample_path}")

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

        # ── Phase 5: Log synthesis results ──
        # Quality retry loop removed: it created new voice clones per retry,
        # causing voice inconsistency (same character sounding different across
        # segments). Timing mismatches are handled by merge.py's atempo speedup.
        _update_progress(
            job_id,
            step=f"Synthesis complete: {len(synthesized_segments)} segment(s)",
            progress=85,
            containers_active=0,
        )
        print(f"[coordinator] Synthesized {len(synthesized_segments)} segments "
              f"for {len(speakers)} speaker(s), language={target_language}")

        # ── Phase 6: Collect Demucs result + merge into final video ──
        _update_progress(
            job_id,
            step="Compositing final video...",
            progress=88,
        )

        # Collect accompaniment from Demucs (spawned in Phase 1).
        # If separation fails, merge falls back to ducking the original audio.
        accompaniment_bytes = None
        try:
            accompaniment_bytes = demucs_handle.get()
            print(f"[Demucs] Source separation complete — {len(accompaniment_bytes)} bytes")
        except Exception as e:
            print(f"[Demucs] Source separation failed, falling back to ducking: {e}")
            # Fallback: merge.py will duck the original audio instead

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
        output_path = merge_chunks(
            input_path, merge_input, job_id, output_dir,
            accompaniment_bytes=accompaniment_bytes,
        )

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
