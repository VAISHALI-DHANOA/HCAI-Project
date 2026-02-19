from __future__ import annotations

import re


BLOCKED_TERMS = {
    "idiot",
    "stupid",
    "hate",
    "shut up",
    "dumb",
    "worthless",
}


def enforce_civility(text: str) -> str:
    cleaned = " ".join(text.strip().split())
    lowered = cleaned.lower()
    for term in BLOCKED_TERMS:
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        lowered = pattern.sub("respectfully disagree", lowered)
    if lowered and lowered[-1] not in ".!?":
        lowered += "."
    return lowered[0].upper() + lowered[1:] if lowered else "I will stay constructive."


def truncate_to_words(text: str, max_words: int) -> str:
    words = text.strip().split()
    if len(words) <= max_words:
        return text.strip()
    shortened = " ".join(words[:max_words]).rstrip(",;:")
    if shortened and shortened[-1] not in ".!?":
        shortened += "."
    return shortened

