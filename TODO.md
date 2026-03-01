# TODO

## Setup
- [x] Fill in `backend/.env` with OPENAI_API_KEY, ELEVENLABS_API_KEY, HF_TOKEN
- [x] Run `modal setup` to authenticate (opens browser)
- [x] Run `modal token new` to confirm token
- [x] Run `modal secret create mimic-secrets` with all 3 keys
- [x] Accept HuggingFace model terms:
  - [x] https://huggingface.co/pyannote/speaker-diarization-3.1
  - [x] https://huggingface.co/pyannote/segmentation-3.0

## Spike Tests
- [x] Spike 1: Diarization — does pyannote correctly split speakers?
- [x] Spike 2: Voice cloning — does ElevenLabs output sound like the speaker?
- [x] Spike 3: End-to-end — 30-second 2-speaker clip through full API

## After Spikes Pass
- [x] Run full pipeline through the UI (upload → dub → download)
- [x] Tune diarization if segments are too fragmented (adjust min_duration_on)
- [x] Tune translation if dubbed audio overruns timing (test Arabic/German)
- [x] Test with 3+ speakers to verify parallel container spawning on Modal dashboard

## Demo Prep
- [ ] Pick a compelling 30-second demo clip (2-3 speakers, clear dialogue)
- [ ] Record before/after for each target language you want to show
- [ ] Verify Modal dashboard shows parallel containers during demo
- [ ] Prepare Devpost write-up
- [ ] Register for prize tracks: Modal Best AI Inference, Best Social Impact, Best UI/UX, ElevenLabs (MLH)
