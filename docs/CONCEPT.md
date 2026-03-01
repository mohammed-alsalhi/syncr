# Syncr — Real-Time AI Dubbing Studio That Rewrites Films Into Any Language, Preserving Every Actor's Voice

## The One-Liner

Upload any video. In minutes, every actor is speaking fluent Mandarin, Arabic, or Spanish — in their own voice, with lip-sync-aware pacing.

## Why Judges Will Gasp

The demo is the product. You play 30 seconds of an English movie clip, hit a button, and play back the same clip — same actors, same emotion, same cadence — but in Arabic. That's a jaw-drop moment that needs zero explanation. It's also a problem everyone on the planet viscerally understands: dubbing is terrible, and it costs studios millions per film.

## What It Does

1. You upload a video via the web UI
2. A coordinator on Modal splits the video into scene-aware chunks (~5 min each) and spawns parallel GPU containers
3. Each chunk runs diarization (pyannote), transcription (self-hosted Whisper on T4 GPU), and context-aware translation (GPT-4o) — all in parallel
4. Demucs source separation removes original vocals while preserving music/effects/ambient audio
5. Speaker embeddings are matched across chunks so each actor gets one consistent cloned voice (ElevenLabs)
6. Dubbed audio is merged with crossfades, per-segment volume matching, and the Demucs background track
7. **Output:** a fully dubbed video (h264 + AAC), downloadable, in ~5-10 minutes for a short clip

The parallelism is real and necessary — chunks process on separate GPU containers, each speaker's voice is cloned independently, and Demucs runs in parallel with everything else. Modal's ephemeral GPU containers are load-bearing, not decorative.

## What Makes It Technically Impressive

Voice cloning + speaker diarization + timing-aware TTS + parallel processing is a genuinely hard pipeline. Judges who are technical will respect the orchestration. Judges who aren't technical will be floored by the demo. That's the sweet spot.

## Prize Alignment

### Primary Track

- **Modal Best AI Inference** — GPU-intensive voice cloning and synthesis running across parallel containers is exactly what Modal is built for.

### Sponsor Prizes (pick 3)

- **ElevenLabs (MLH)** — voice cloning is the core of the product, this is the most natural MLH prize integration possible
- **OpenAI API** — translation and script adaptation between languages
- **Supermemory** — remember user's previously dubbed projects and voice profiles across sessions

### General Prizes (pick 2)

- **Best Social Impact** — access to content across language barriers is a genuine equity issue; billions of people are locked out of English-language media and education
- **Best UI/UX Design** — a clean studio interface with waveform visualization and a before/after player is very designable and judges can interact with it directly

### MLH Freebies

- Best Use of ElevenLabs (practically guaranteed if you win this track)
- Best .Tech Domain
- Best Use of DigitalOcean

## Why It's Realistic in 36 Hours

The pieces all exist as APIs — you're not building a voice cloner from scratch. The work is in the orchestration:

- **pyannote.audio** for speaker diarization (open source, well-documented)
- **ElevenLabs** voice cloning API for each speaker
- **OpenAI** for translation with timing constraints in the prompt
- **Modal** to run all speaker pipelines simultaneously
- **ffmpeg** for video/audio composition

The hardest part is timing reconciliation — making dubbed speech fit lip movements — but even an approximate solution is impressive enough for a hackathon.
