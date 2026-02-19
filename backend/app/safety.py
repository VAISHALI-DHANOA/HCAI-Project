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
    sanitized = cleaned
    for term in BLOCKED_TERMS:
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        sanitized = pattern.sub("respectfully disagree", sanitized)
    if sanitized and sanitized[-1] not in ".!?":
        sanitized += "."
    return sanitized if sanitized else "I will stay constructive."


def truncate_to_words(text: str, max_words: int) -> str:
    words = text.strip().split()
    if len(words) <= max_words:
        return text.strip()
    shortened = " ".join(words[:max_words]).rstrip(",;:")
    if shortened and shortened[-1] not in ".!?":
        shortened += "."
    return shortened
