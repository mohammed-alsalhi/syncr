# Modal Notes — Track Introduction

## What is Modal?

Modal is a serverless GPU cloud. You write normal Python, decorate functions, and Modal runs them in containers in the cloud. No Docker, no Kubernetes, no YAML. Everything is defined in code.

**You pay per second.** When nothing runs, you pay nothing (scale to zero).

## Core Concepts

### Containers
A container is an isolated environment that runs your function in the cloud. Think of it as a lightweight virtual machine that Modal spins up on demand. Key things:
- Modal creates containers automatically when your function is called
- Containers spin up in ~1 second (cold start)
- Multiple containers can run in parallel (one per concurrent call)
- Containers shut down when idle — **scale to zero** means you stop paying when nothing is running
- You control how many containers can exist at once (this is how you control spending)

### Images
An image is the blueprint for a container — it defines what software is installed. Instead of writing a Dockerfile, you define it in Python:

```python
import modal

# Start from a slim Debian base, add Python packages
image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "torch",
    "transformers",
    "pyannote.audio",
)
```

**Important:** Import heavy libraries (transformers, torch, pyannote) **inside** your functions, not at the top of the file. These packages only exist inside the remote container, not on your local machine.

```python
# WRONG — will fail locally
import transformers

# RIGHT — import inside the function that runs remotely
@app.function(image=image, gpu="A10G")
def run_model(text):
    import transformers  # only imported in the container
    pipeline = transformers.pipeline("translation")
    return pipeline(text)
```

### Functions
Decorate a Python function with `@app.function()` to make it run remotely:

```python
app = modal.App("syncr")

@app.function(image=image, gpu="A10G", timeout=600)
def diarize(audio_path: str):
    import torch
    from pyannote.audio import Pipeline
    # ... runs on a GPU in the cloud
```

Call it with `.remote()` to run in the cloud:
```python
result = diarize.remote("path/to/audio.wav")
```

Or `.local()` to run on your machine (for testing):
```python
result = diarize.local("path/to/audio.wav")
```

### Container Lifecycle (Classes)
For models that are expensive to load, use a class with `@modal.enter()` so the model loads once and serves many requests:

```python
@app.cls(image=image, gpu="A10G")
class Diarizer:
    @modal.enter()
    def load_model(self):
        # Runs ONCE when the container starts
        from pyannote.audio import Pipeline
        self.pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1")

    @modal.method()
    def run(self, audio_path):
        # Runs on EACH call — model is already loaded
        return self.pipeline(audio_path)
```

## Scaling and Spending Control

### How to not overspend
```python
@app.function(
    gpu="A10G",              # $1.10/hr — cheapest GPU that works for pyannote
    timeout=300,             # kill after 5 minutes (prevents runaway jobs)
    concurrency_limit=2,     # max 2 containers at once
    allow_concurrent_inputs=1,  # 1 request per container at a time
)
```

### GPU options for Syncr (cheapest → most expensive)
| GPU      | $/hr  | VRAM  | Use case                        |
|----------|-------|-------|---------------------------------|
| T4       | $0.59 | 16 GB | Light inference, testing        |
| L4       | $0.80 | 24 GB | Good balance for diarization    |
| A10      | $1.10 | 24 GB | Reliable for pyannote + whisper |
| A100 40G | $2.10 | 40 GB | Only if A10 is too slow         |

### Scale to zero
Containers automatically shut down when idle. You only pay while code is actually executing. This is the default — you don't need to configure it.

To explicitly scale GPUs to zero between jobs, just don't keep containers alive. Avoid `keep_warm=1` in production unless you need instant response times.

```python
# This keeps 1 container always running (costs money 24/7!)
@app.function(gpu="A10G", keep_warm=1)  # AVOID unless needed

# This scales to zero (default, free when idle)
@app.function(gpu="A10G")  # GOOD
```

## Running Modal

```bash
# One-time setup
pip install modal
modal setup          # authenticate via browser
modal token new      # confirm token

# Run a function
modal run pipeline/modal_jobs.py

# Deploy as a persistent endpoint
modal deploy pipeline/modal_jobs.py
```

## Sandboxes vs Functions
- **Sandboxes**: Interactive environments for experimentation (notebooks, vibe coding). Higher per-second cost (3x CPU, 3x memory). Good for prototyping.
- **Functions**: Production inference. Lower cost, auto-scaling. Use this for the actual pipeline.

For Syncr: prototype in a sandbox/notebook, then move to `@app.function()` for the real pipeline.

## Secrets (API keys in containers)
Containers don't have access to your local `.env`. Create Modal secrets:

```bash
modal secret create mimic-secrets \
  HF_TOKEN=hf_... \
  OPENAI_API_KEY=sk-... \
  ELEVENLABS_API_KEY=...
```

Then reference in your function:
```python
@app.function(
    image=image,
    gpu="A10G",
    secrets=[modal.Secret.from_name("mimic-secrets")],
)
def diarize(audio_path):
    import os
    hf_token = os.environ["HF_TOKEN"]  # available inside the container
```

## Fine-tuning / RL on Modal
Modal supports training workloads too — same pattern, just bigger GPUs and longer timeouts. Use `modal.Volume` to persist model checkpoints across runs. Not needed for Syncr's hackathon scope.
