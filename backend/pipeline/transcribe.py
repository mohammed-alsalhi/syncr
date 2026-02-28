"""
Step 3: Transcribe audio segments using OpenAI Whisper API.
"""

import os
from openai import OpenAI


def transcribe_segments(segments: list[dict]) -> list[dict]:
    """
    Transcribe each segment's audio to text using Whisper.

    Args:
        segments: List of dicts with keys: speaker, start, end, audio_path

    Returns:
        Same list with added "text" field containing transcribed text.

    Raises:
        openai.APIError: If Whisper API call fails
    """
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    result = []

    for seg in segments:
        with open(seg["audio_path"], "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text",
            )

        result.append({
            **seg,
            "text": transcript.strip(),
        })

    return result
