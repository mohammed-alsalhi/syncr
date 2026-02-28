# TODO

## Setup (do first)
- [ ] Fill in `backend/.env` with OPENAI_API_KEY, ELEVENLABS_API_KEY, HF_TOKEN
- [ ] Run `modal setup` to authenticate (opens browser)
- [ ] Run `modal token new` to confirm token
- [ ] Run `modal secret create mimic-secrets` with all 3 keys
- [ ] Accept HuggingFace model terms:
  - [ ] https://huggingface.co/pyannote/speaker-diarization-3.1
  - [ ] https://huggingface.co/pyannote/segmentation-3.0

## Spike Tests (do in order)
- [ ] Spike 1: Diarization — does pyannote correctly split speakers?
- [ ] Spike 2: Voice cloning — does ElevenLabs output sound like the speaker?
- [ ] Spike 3: End-to-end — 30-second 2-speaker clip through full API

## After Spikes Pass
- [ ] Run full pipeline through the UI (upload → dub → download)
- [ ] Tune diarization if segments are too fragmented (adjust min_duration_on)
- [ ] Tune translation if dubbed audio overruns timing (test Arabic/German)
- [ ] Test with 3+ speakers to verify parallel container spawning on Modal dashboard

## Demo Prep
- [ ] Pick a compelling 30-second demo clip (2-3 speakers, clear dialogue)
- [ ] Record before/after for each target language you want to show
- [ ] Verify Modal dashboard shows parallel containers during demo
- [ ] Prepare Devpost write-up
- [ ] Register for prize tracks: Modal Best AI Inference, Best Social Impact, Best UI/UX, ElevenLabs (MLH)
