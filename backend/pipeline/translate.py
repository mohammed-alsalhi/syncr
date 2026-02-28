"""
Step 4: Translate transcribed segments using GPT-4o-mini.

Two modes:
  - translate_segments(): sequential, for local testing
  - translate_segments_with_context(): context-aware, groups nearby segments
    and passes surrounding dialogue for better translation quality
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
    Sequential mode — translates each segment independently.

    Args:
        segments:        List of dicts with keys: speaker, start, end, audio_path, text
        target_language: ISO 639-1 language code (e.g., "es", "fr", "de")

    Returns:
        Same list with added "translated_text" field.
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


def translate_segments_with_context(segments: list[dict], target_language: str) -> list[dict]:
    """
    Translate segments with surrounding dialogue context for better quality.

    Groups segments into batches of up to 5, passes the full batch as context
    to GPT, and asks for translations of each line. This dramatically improves
    translation quality for dialogue because the model understands the
    conversational flow.

    Args:
        segments:        List of dicts with keys: speaker, start, end, text
        target_language: ISO 639-1 language code

    Returns:
        Same list with added "translated_text" field.
    """
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    lang_name = LANGUAGE_NAMES.get(target_language, target_language)

    # Build context windows of up to 5 segments
    WINDOW_SIZE = 5
    result = []

    for i in range(0, len(segments), WINDOW_SIZE):
        batch = segments[i:i + WINDOW_SIZE]

        # Separate empty segments
        non_empty = [(j, seg) for j, seg in enumerate(batch) if seg.get("text", "").strip()]
        if not non_empty:
            for seg in batch:
                result.append({**seg, "translated_text": ""})
            continue

        # Build dialogue context block
        dialogue_lines = []
        for j, seg in non_empty:
            duration = seg["end"] - seg["start"]
            dialogue_lines.append(
                f"[{seg['speaker']}, {duration:.1f}s]: {seg['text']}"
            )
        dialogue_block = "\n".join(dialogue_lines)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a professional dubbing translator for film and television. "
                        f"Translate the following dialogue exchange into {lang_name}. "
                        f"Each line is labeled with its speaker and the duration it must fit into. "
                        f"Your translations must:\n"
                        f"1. Be speakable within the given duration for each line\n"
                        f"2. Sound natural as a conversation (maintain tone, register, and flow)\n"
                        f"3. Prefer shorter, natural phrasing over literal accuracy\n"
                        f"4. Preserve the emotional intent of each line\n\n"
                        f"Return ONLY the translations, one per line, in the same order. "
                        f"Format each line as: [SPEAKER]: translation"
                    ),
                },
                {"role": "user", "content": dialogue_block},
            ],
            max_tokens=1000,
            temperature=0.3,
        )

        # Parse response — one translation per line
        response_text = response.choices[0].message.content.strip()
        response_lines = [line.strip() for line in response_text.split("\n") if line.strip()]

        # Map translations back to segments
        translation_idx = 0
        for j, seg in enumerate(batch):
            if not seg.get("text", "").strip():
                result.append({**seg, "translated_text": ""})
                continue

            if translation_idx < len(response_lines):
                raw_line = response_lines[translation_idx]
                # Strip "[SPEAKER]: " prefix if present (bracket format takes priority)
                if raw_line.startswith("[") and "]: " in raw_line:
                    raw_line = raw_line.split("]: ", 1)[1]
                elif raw_line.startswith("SPEAKER") and ": " in raw_line:
                    raw_line = raw_line.split(": ", 1)[1]
                result.append({**seg, "translated_text": raw_line.strip()})
                translation_idx += 1
            else:
                # Fallback: if response has fewer lines than expected
                result.append({**seg, "translated_text": seg.get("text", "")})

    return result
