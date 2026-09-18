"""Generation settings shared by provider calls and their logged metadata."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class GenerationSettings:
    model: str
    max_tokens: int
    temperature: float
    timeout_seconds: float = 15.0

    def to_dict(self) -> dict:
        return asdict(self)


MODEL = "claude-haiku-4-5-20251001"
DISCUSSION_SETTINGS = GenerationSettings(MODEL, max_tokens=100, temperature=0.85)
DATA_CONTRIBUTION_SETTINGS = GenerationSettings(MODEL, max_tokens=500, temperature=0.85)
SUMMARY_SETTINGS = GenerationSettings(MODEL, max_tokens=80, temperature=0.7)
CHAT_SETTINGS = GenerationSettings(MODEL, max_tokens=100, temperature=0.85)
VISUAL_SETTINGS = GenerationSettings(MODEL, max_tokens=500, temperature=0.7)
TTS_MODEL = "tts-1"
