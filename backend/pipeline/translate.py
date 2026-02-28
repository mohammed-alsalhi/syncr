"""
Step 4: Translate transcribed segments using GPT-4o-mini with timing-aware prompts.
"""

import os
from openai import OpenAI

LANGUAGE_NAMES = {
    "es": "Spanish", "fr": "French", "de": "German", "ar": "Arabic",
    "zh": "Mandarin Chinese", "ja": "Japanese", "pt": "Portuguese",
    "hi": "Hindi", "ko": "Korean", "it": "Italian",
}


def translate_segments(segments: list[dict], target_language: str) -> list[dict]:
    """
    Translate transcribed text to target language with timing awareness.

    Args:
        segments:        List of dicts with keys: speaker, start, end, audio_path, text
        target_language: ISO 639-1 language code (e.g., "es", "fr", "de")

    Returns:
        Same list with added "translated_text" field.

    Raises:
        openai.APIError: If GPT API call fails
    """
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    lang_name = LANGUAGE_NAMES.get(target_language, target_language)
    result = []

    for seg in segments:
        if not seg["text"].strip():
            result.append({**seg, "translated_text": ""})
            continue

        duration = seg["end"] - seg["start"]

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a professional dubbing translator. "
                        f"Translate the following dialogue line into {lang_name}. "
                        f"The original line is spoken in {duration:.1f} seconds. "
                        f"Your translation must be speakable in approximately the same duration. "
                        f"Prefer shorter, natural phrasing over literal accuracy. "
                        f"Return ONLY the translated text, nothing else."
                    ),
                },
                {"role": "user", "content": seg["text"]},
            ],
            max_tokens=500,
            temperature=0.3,
        )

        translated = response.choices[0].message.content.strip()
        result.append({**seg, "translated_text": translated})

    return result
