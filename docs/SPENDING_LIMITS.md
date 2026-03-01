# Spending Limits & Token Safety

## Budget Overview

| Service       | Credits Available      | Rate                                    | Hard Limit Action                |
|---------------|------------------------|-----------------------------------------|----------------------------------|
| Modal         | $250 (HackIllinois)   | $0.59–$3.95/hr per GPU                  | Set concurrency_limit in code    |
| ElevenLabs    | Free tier: 10k chars   | ~$0.30 per 1k chars on paid             | Track chars sent per job         |
| OpenAI        | Per-token billing      | GPT-4o: ~$2.50/1M input, $10/1M output   | Track token count per job        |

## Modal Guardrails

Every `@app.function()` MUST include these parameters:

```python
@app.function(
    gpu="T4",                # use cheapest GPU that works — upgrade only if needed
    timeout=300,             # 5 min max — prevents stuck containers billing forever
    concurrency_limit=2,     # max 2 containers at once
)
```

### Spending estimates per run (30-second clip)
| Step              | GPU  | Est. time | Est. cost |
|-------------------|------|-----------|-----------|
| Diarization       | T4   | ~60s      | ~$0.01    |
| Transcription     | T4   | ~15s      | ~$0.01    |
| Demucs separation | T4   | ~30s      | ~$0.01    |
| Translation       | CPU  | ~5s       | <$0.01    |
| Voice synthesis   | CPU  | ~30s      | <$0.01    |
| Merge + composite | CPU  | ~15s      | <$0.01    |
| **Total per run** |      |           | **~$0.03–0.06** |

With $250 credits, that's ~5,000+ runs. Plenty for a hackathon. The danger is leaving containers running or forgetting timeouts.

### What burns money fast
- `keep_warm=1` on GPU functions → $0.59–$3.95/hr even with zero traffic
- No `timeout` → a stuck container bills indefinitely
- No `concurrency_limit` → a bug that spawns 50 containers costs 50x
- Using A100 when T4 works → 4x cost for no benefit

### Safety checklist before every `modal deploy`
- [ ] Every function has `timeout` set (max 600s for hackathon)
- [ ] Every GPU function has `concurrency_limit` (max 3)
- [ ] No `keep_warm` unless intentional
- [ ] Using the cheapest GPU that passes tests (start with T4, upgrade only if OOM or too slow)
- [ ] Check Modal dashboard after first run: https://modal.com/apps

## ElevenLabs Guardrails

Voice cloning creates a voice profile per speaker. Each clone + synthesis call costs characters.

### Rules
- **Clone once per speaker per job** — never re-clone the same speaker
- **Cache voice IDs** — store the voice_id after cloning, reuse for all that speaker's segments
- **Delete cloned voices after job completes** — free tier has a voice limit
- **Log character count** — print total chars sent to ElevenLabs per job

```python
# Track usage in synthesize.py
total_chars = 0
for segment in segments:
    total_chars += len(segment["translated_text"])
print(f"[ElevenLabs] Total characters synthesized: {total_chars}")
```

### Free tier limits
- 10,000 characters/month
- 3 custom voices at a time
- Delete voices after each job to stay under limit

## OpenAI Guardrails

### Rules
- **Using `gpt-4o` for translation** — upgraded from 4o-mini for better translation quality, especially for context-aware dialogue
- **Batch segments** — send nearby segments in a single API call with dialogue context instead of one-by-one
- **Set `max_tokens`** — always cap response length to prevent runaway output
- **Whisper is self-hosted** — runs on our own T4 GPU containers via faster-whisper, no OpenAI Whisper API cost

```python
response = client.chat.completions.create(
    model="gpt-4o",            # upgraded for translation quality
    messages=[...],
    max_tokens=2000,           # cap output
)
```

### Cost per 30-second clip (estimated)
- Whisper transcription: **$0 (self-hosted on Modal GPU)**
- GPT-4o translation: ~500 tokens → <$0.01
- **Total OpenAI per run: <$0.01**

## Monitoring

After each test run, check:
1. **Modal**: https://modal.com/apps → check container runtime and cost
2. **ElevenLabs**: https://elevenlabs.io/subscription → check character usage
3. **OpenAI**: https://platform.openai.com/usage → check token usage
