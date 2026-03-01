## Inspiration

Every year, Hollywood spends billions on dubbing — and the results still sound wrong. Lip-sync is off, voices feel generic, and the soul of the original performance gets lost in translation. We watched a Spanish dub of *Breaking Bad* and couldn't stop laughing — not because of the script, but because Walter White sounded like a telenovela host. That moment sparked a question: **what if AI could dub any video, in any language, and every actor kept their own voice?**

Traditional dubbing costs studios upward of \$20,000 *per minute* of content and takes weeks of studio time with voice actors, sound engineers, and translators coordinating across time zones. Meanwhile, billions of people worldwide can't access content in their native language. Educational videos, indie films, corporate training, YouTube creators — all locked behind a language barrier.

We set out to build **Syncr**: an AI dubbing studio that takes any video — from a 30-second clip to a full-length feature film — and produces a dubbed version where every speaker's voice is cloned, every translation respects the rhythm of natural speech, and the background audio (music, sound effects, ambient noise) is surgically preserved. Not a toy demo. A system that actually scales.

---

## How We Built It

### The Pipeline: From Upload to Dubbed Video

Syncr is a full-stack application: a **React/Vite** frontend for upload, real-time monitoring, and synced playback, backed by a **FastAPI** server that orchestrates a massively parallel GPU pipeline on **Modal**.

The pipeline follows seven stages, each solving a distinct problem:

#### Stage 1 — Scene-Aware Chunking

Feature-length videos can't be processed as a monolith. We use FFmpeg's scene detection filter to find natural cut points:

```
ffmpeg -filter:v "select='gt(scene, 0.3)', showinfo" -f null -
```

Scenes with a frame-difference score exceeding $0.3$ (30% pixel change) trigger a boundary. Contiguous scenes are grouped into chunks of up to $T_{\max} = 300\text{s}$ (5 minutes), with a $\pm 2\text{s}$ overlap at boundaries to preserve speaker continuity across cuts.

#### Stage 2 — Speaker Diarization

Each chunk is diarized using **pyannote/speaker-diarization-3.1** on a T4 GPU. The model segments audio into speaker turns, but has a well-known over-segmentation problem — splitting one real speaker into multiple labels.

We solve this with **agglomerative clustering using complete linkage**. For each detected speaker, we extract embedding vectors using `pyannote/wespeaker-voxceleb-resnet34-LM`, averaging up to 3 of the longest segments ($\geq 1.0\text{s}$) per speaker and normalizing to unit length:

$$\mathbf{e}_{\text{speaker}} = \frac{1}{|\mathcal{S}|} \sum_{s \in \mathcal{S}} \mathbf{e}_s, \quad \hat{\mathbf{e}} = \frac{\mathbf{e}}{||\mathbf{e}||_2}$$

Two clusters merge only if **all** pairwise cosine similarities exceed $\tau_{\text{intra}} = 0.78$. Complete linkage prevents cascading merge errors that plague single-linkage approaches.

#### Stage 3 — Cross-Chunk Speaker Matching

After all chunks are processed, the coordinator must assign globally consistent speaker IDs. We frame this as a **bipartite matching problem**, solved via the **Hungarian algorithm**.

For each new chunk's speakers against the existing global speaker set, we construct a cost matrix:

$$C_{ij} = 1 - \text{cos}(\mathbf{e}_i^{\text{chunk}},\; \mathbf{e}_j^{\text{global}})$$

The matrix is padded with a "new speaker" cost of $1 - \tau_{\text{inter}}$ where $\tau_{\text{inter}} = 0.80$. The optimal assignment minimizes total cost, and any match with similarity $< 0.80$ spawns a new global speaker. This threshold is intentionally stricter than intra-chunk merging ($0.78$) because cross-chunk embeddings come from different acoustic environments.

#### Stage 4 — Self-Hosted Whisper Transcription

Rather than calling an external API, we run **faster-whisper** ("medium" model) directly on T4 GPUs inside Modal:

- **Precision:** float16 on CUDA
- **Beam search:** $\text{beam\_size} = 5$
- **Parallelism:** Up to 4 GPU containers via `.map()`, transcribing segments concurrently

The model is loaded once per container via `@modal.enter()`, amortizing the ~3s startup cost across all segments routed to that container.

#### Stage 5 — Context-Aware Translation

Translation isn't just word substitution — dubbed dialogue must fit within precise time windows. We use **GPT-4o** with a word-budget system calibrated per language:

| Language | Words/Second | Rationale |
|----------|:---:|-----------|
| Japanese | 4.0 | Compact syllabic structure |
| Mandarin | 3.5 | Tonal, dense information per syllable |
| Spanish, French, Korean, Italian, Portuguese | 3.0 | Romance/agglutinative avg |
| Arabic, Hindi | 2.5 | Longer morphological forms |
| German | 2.2 | Compound words, slower cadence |

For a segment of duration $d$ seconds in target language $\ell$:

$$W_{\max} = \lfloor d \times \text{WPS}_\ell \times 0.85 \rfloor$$

The $0.85$ safety factor ensures synthesized speech fits the time slot after TTS. Translations are batched in windows of 5 segments for dialogue context — GPT-4o sees the surrounding conversation, producing translations that flow naturally as spoken dialogue, not stilted written text.

If a translation exceeds $1.5 \times W_{\max}$, a stricter retry fires at temperature $0.2$.

#### Stage 6 — Voice Cloning and Synthesis

Each globally-identified speaker gets a single cloned voice via **ElevenLabs** instant voice cloning. The defense-in-depth pipeline:

1. **Sample validation:** Decode audio bytes, check duration
2. **Padding:** If sample $< 1.5\text{s}$, pad with silence to $2.0\text{s}$
3. **Normalization:** Re-export as mono WAV at 44.1 kHz
4. **Clone:** `POST /v1/voices/add` with the prepared sample
5. **Synthesize:** All segments for that speaker using `eleven_multilingual_v2` (stability: 0.5, similarity boost: 0.75)
6. **Cleanup:** Delete the cloned voice after job completion

All synthesis happens on CPU containers — ElevenLabs handles the heavy lifting via API.

#### Stage 7 — Audio Merging and Video Compositing

The final merge is where everything comes together. **Meta's Demucs** (`htdemucs`) performs source separation on the original audio, isolating the accompaniment track (music, sound effects, ambient) from the vocals. The background is then center-trimmed to correct for Demucs' symmetric padding:

$$\text{trim\_start} = \frac{|\text{bg}| - T_{\text{total}}}{2}, \quad \text{bg}_{\text{trimmed}} = \text{bg}[\text{trim\_start} : \text{trim\_start} + T_{\text{total}}]$$

Each dubbed segment is overlaid with:

- **Speed adjustment** via `atempo` filters (capped at $3.0\times$, chained at $2.0\times$ each per FFmpeg limitation)
- **Volume matching:** Gain $= \text{dBFS}_{\text{orig}} - \text{dBFS}_{\text{dubbed}}$, clamped to $\pm 6\text{ dB}$
- **100ms crossfades** (fade-in and fade-out) to eliminate boundary artifacts

Final encoding: H.264 (`libx264`, CRF 22, preset fast) + AAC audio + `-movflags +faststart` for progressive browser playback.

### Container Architecture at Scale

The system uses a **3-level Modal container hierarchy**:

```
Level 1: Coordinator (CPU)           — 1 container
Level 2: process_chunk (T4 GPU)      — N containers (1 per chunk)
Level 2: WhisperTranscriber (T4 GPU) — up to 4 containers
Level 2: separate_audio (T4 GPU)     — 1 container (Demucs)
Level 3: synthesize_speaker (CPU)    — N containers (1 per speaker)
```

| Content Length | Chunks | Total Containers |
|:---:|:---:|:---:|
| 30 seconds | 1 | 8–10 |
| 10 minutes | 3–4 | 15–20 |
| 2 hours (feature film) | 20–30 | 40–60+ |

### Frontend: Real-Time Pipeline Dashboard

The React frontend provides a live window into the pipeline:

- **Step visualization** with animated status indicators (scissors, mic, globe, waveform icons)
- **Metrics pills** showing chunks completed, speakers found, segments processed, active containers
- **Waveform animation** (36 staggered bars) that reacts to pipeline state
- **Live transcript panel** with speaker-colored original + translated text
- **Synced dual video player** — original (muted) and dubbed (unmuted) side-by-side, auto-resyncing if drift exceeds $0.3\text{s}$

### Real-Time Progress Without Race Conditions

Progress updates flow through `modal.Dict` — all containers write their status, and the local orchestrator polls every 1 second. A critical invariant: **Modal containers never write `status: "done"`**. Progress is capped at 97%. Only the local orchestrator sets "done" after confirming the output file exists on disk. This eliminates the race condition where the frontend requests a download before the file is written.

---

## Challenges We Faced

### 1. The Pickle Problem

Modal serializes function arguments across container boundaries using Python's `pickle`. We discovered that `aiohttp`'s `ClientResponseError` contains `CIMultiDictProxy` headers — which are unpicklable. Every API error in a child container crashed the parent. We replaced all `resp.raise_for_status()` calls with explicit status checks raising plain `RuntimeError`s.

### 2. Speaker Over-Segmentation

Pyannote consistently detected 5 speakers in a 3-speaker video. We explored several solutions before landing on agglomerative clustering with complete linkage — the key insight being that single-linkage (greedy merging) caused cascading errors where distinct speakers got merged through a chain of marginally-similar segments.

### 3. The Voice Consistency Paradox

Our quality verification loop (retry synthesis if timing was off) seemed like a good idea — until we realized each retry created a **new** voice clone. Three retries meant three different-sounding voices for the same character. The fix was counterintuitive: remove the retry loop entirely and let `atempo` handle timing in post-processing.

### 4. Demucs Desync

After integrating Demucs for clean background audio, dubbed videos were consistently ~1 second behind. Hours of debugging revealed that Demucs adds symmetric zero-padding for its sliding-window STFT. Our original code trimmed only from the end — preserving the start padding and shifting everything forward. The center-trim formula above was the fix.

### 5. The 1-Second Voice Cliff

ElevenLabs rejects voice samples under 1 second, but speaker diarization frequently produces sub-second segments. Our defense-in-depth approach — detect short samples, pad to 2 seconds with silence, normalize to mono 44.1 kHz — handles this transparently without degrading clone quality.

### 6. Scaling from Demo to Movie

The hardest challenge was architectural: making a pipeline that works on a 30-second clip also work on a 2-hour film. Scene-aware chunking, parallel GPU containers, cross-chunk speaker matching, and the coordinator pattern were all built specifically to solve this scaling problem. No single design decision was sufficient — it required all of them working together.

---

## What We Learned

- **Distributed systems are hard, distributed ML systems are harder.** Every container has its own filesystem, its own GPU memory, and its own failure modes. Passing data as bytes (not file paths) between containers was a fundamental architectural decision that saved us from countless bugs.

- **The Hungarian algorithm isn't just textbook material.** Using optimal bipartite matching for cross-chunk speaker assignment was dramatically better than greedy matching — it considers the global assignment quality rather than making locally optimal choices that conflict later.

- **Safety margins compound.** The 85% word budget for translation, the $\pm 6\text{ dB}$ gain clamp, the 100ms crossfades, the 2-second overlap at chunk boundaries — each is a small margin, but together they're the difference between "sounds like AI" and "sounds like dubbing."

- **Remove features to fix bugs.** The quality retry loop was our most engineered feature, and removing it fixed two bugs simultaneously (voice consistency and timing). Sometimes the best code is deleted code.

- **Real progress tracking changes everything.** The jump from "processing... please wait" to a live dashboard with chunk maps, container counts, and transcript previews transformed the user experience from anxiety-inducing to genuinely exciting.

---

## Built With

`Python` `FastAPI` `React` `Vite` `Tailwind CSS` `Modal` `PyTorch` `pyannote.audio` `faster-whisper` `Meta Demucs` `ElevenLabs API` `OpenAI GPT-4o` `FFmpeg` `pydub` `SciPy`
