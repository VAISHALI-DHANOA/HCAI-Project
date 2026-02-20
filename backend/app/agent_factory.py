from __future__ import annotations

import re

from app.ids import deterministic_agent_id
from app.models import Agent, UserAgentInput

QUIRK_FALLBACKS = [
    "asks unusual questions",
    "connects distant concepts",
    "prefers practical experiments",
]


def _extract_candidate_phrases(persona_text: str) -> list[str]:
    chunks = re.split(r"[.,;:!?]| and | but | while | because ", persona_text)
    phrases: list[str] = []
    for chunk in chunks:
        phrase = " ".join(chunk.strip().split())
        if not phrase:
            continue
        words = phrase.split()
        if len(words) > 6:
            phrase = " ".join(words[:6])
        phrases.append(phrase.lower())
    return phrases


def extract_quirks(persona_text: str) -> list[str]:
    candidates = _extract_candidate_phrases(persona_text)
    selected: list[str] = []
    for phrase in candidates:
        if phrase not in selected:
            selected.append(phrase)
        if len(selected) == 3:
            break
    for fallback in QUIRK_FALLBACKS:
        if len(selected) == 3:
            break
        if fallback not in selected:
            selected.append(fallback)
    return selected[:3]


def build_initial_stance(topic: str, quirks: list[str], name: str) -> str:
    lead = quirks[0]
    return f"{name} approaches {topic} by emphasizing {lead} to find constructive progress."


def create_mediators() -> list[Agent]:
    chair = Agent(
        id=deterministic_agent_id("mediator", "The Chair", "turn-taking civility summaries", 0),
        name="The Chair",
        persona_text="Ensures turn-taking, summarizes discussions, keeps civility.",
        quirks=[
            "counts speaking turns",
            "reframes conflict calmly",
            "summarizes with neutral language",
        ],
        stance="I prioritize fair turn-taking and clear summaries so the group stays constructive.",
        energy=0.7,
        role="mediator",
    )
    return [chair]


def create_agents_from_user(topic: str, user_agents: list[dict | UserAgentInput]) -> list[Agent]:
    created: list[Agent] = []
    for idx, raw in enumerate(user_agents):
        if isinstance(raw, UserAgentInput):
            payload = raw
        else:
            payload = UserAgentInput.model_validate(raw)
        quirks = extract_quirks(payload.persona_text)
        created.append(
            Agent(
                id=deterministic_agent_id("user", payload.name, payload.persona_text, idx),
                name=payload.name.strip(),
                persona_text=payload.persona_text.strip(),
                quirks=quirks,
                stance=build_initial_stance(topic, quirks, payload.name.strip()),
                energy=payload.energy,
                role="user",
                mbti_type=payload.mbti_type,
            )
        )
    return created
