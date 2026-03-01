"""
Step 4: Translate transcribed segments using GPT-4o.

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

# Approximate words-per-second when spoken naturally, by target language.
# Used to compute a concrete word budget for the translator.
# Source languages (like English) average ~2.5 wps.
WORDS_PER_SECOND = {
    "es": 3.0, "fr": 3.0, "de": 2.2, "ar": 2.5,
    "zh": 3.5, "ja": 4.0, "pt": 3.0,
    "hi": 2.5, "ko": 3.0, "it": 3.0,
}
DEFAULT_WPS = 2.5


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
    wps = WORDS_PER_SECOND.get(target_language, DEFAULT_WPS)
    result = []

    for seg in segments:
        if not seg["text"].strip():
            result.append({**seg, "translated_text": ""})
            continue

        duration = seg["end"] - seg["start"]
        max_words = max(2, int(duration * wps * 0.85))

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a professional dubbing translator. "
                        f"Translate the following dialogue line into {lang_name}. "
                        f"The original line is spoken in {duration:.1f} seconds. "
                        f"Your translation MUST be {max_words} words or fewer. "
                        f"Shorter is always better. Use natural spoken phrasing, "
                        f"not written text. Return ONLY the translated text."
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
    to GPT, and asks for translations of each line. Each line gets a concrete
    word budget based on the target language's speaking rate to prevent
    translations that are too long for the time slot.

    Args:
        segments:        List of dicts with keys: speaker, start, end, text
        target_language: ISO 639-1 language code

    Returns:
        Same list with added "translated_text" field.
    """
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    lang_name = LANGUAGE_NAMES.get(target_language, target_language)
    wps = WORDS_PER_SECOND.get(target_language, DEFAULT_WPS)

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

        # Build dialogue context block with word budgets
        dialogue_lines = []
        for j, seg in non_empty:
            duration = seg["end"] - seg["start"]
            max_words = max(2, int(duration * wps * 0.85))  # 85% of budget for safety margin
            dialogue_lines.append(
                f"[{seg['speaker']}, {duration:.1f}s, max {max_words} words]: {seg['text']}"
            )
        dialogue_block = "\n".join(dialogue_lines)

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a professional dubbing translator for film and television. "
                        f"Translate the following dialogue exchange into {lang_name}. "
                        f"Each line is labeled with its speaker, duration, and MAXIMUM word count. "
                        f"CRITICAL RULES:\n"
                        f"1. NEVER exceed the max word count for any line — this is a hard limit\n"
                        f"2. Shorter is ALWAYS better. Use contractions, drop filler words, "
                        f"simplify phrasing aggressively\n"
                        f"3. Sound natural as spoken dialogue (not written text)\n"
                        f"4. Preserve the emotional intent and meaning, not literal words\n"
                        f"5. If a line can be said in fewer words, use fewer words\n\n"
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

        # Map translations back to segments, with length validation
        translation_idx = 0
        for j, seg in enumerate(batch):
            if not seg.get("text", "").strip():
                result.append({**seg, "translated_text": ""})
                continue

            if translation_idx < len(response_lines):
                raw_line = response_lines[translation_idx]
                # Strip "[SPEAKER]: " prefix if present
                if raw_line.startswith("[") and "]: " in raw_line:
                    raw_line = raw_line.split("]: ", 1)[1]
                elif raw_line.startswith("SPEAKER") and ": " in raw_line:
                    raw_line = raw_line.split(": ", 1)[1]

                translated = raw_line.strip()
                duration = seg["end"] - seg["start"]
                max_words = max(2, int(duration * wps * 0.85))
                word_count = len(translated.split())

                # If translation is way over budget (>1.5x), retry with stricter prompt
                if word_count > max_words * 1.5 and max_words >= 3:
                    try:
                        retry_resp = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {
                                    "role": "system",
                                    "content": (
                                        f"Shorten this {lang_name} translation to AT MOST "
                                        f"{max_words} words. Keep meaning, drop filler. "
                                        f"Return ONLY the shortened translation."
                                    ),
                                },
                                {"role": "user", "content": translated},
                            ],
                            max_tokens=200,
                            temperature=0.2,
                        )
                        shortened = retry_resp.choices[0].message.content.strip()
                        if len(shortened.split()) < word_count:
                            translated = shortened
                    except Exception:
                        pass  # Keep original translation if retry fails

                result.append({**seg, "translated_text": translated})
                translation_idx += 1
            else:
                # Fallback: if response has fewer lines than expected
                result.append({**seg, "translated_text": seg.get("text", "")})

    return result
