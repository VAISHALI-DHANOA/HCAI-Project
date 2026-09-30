from __future__ import annotations

from app.ids import deterministic_agent_id
from app.models import Agent, UserAgentInput
from app.personality import normalize_personality


def create_mediators() -> list[Agent]:
    chair = Agent(
        id=deterministic_agent_id("mediator", "The Chair", "turn-taking civility summaries", 0),
        name="The Chair",
        persona_text="Ensures turn-taking, summarizes discussions, keeps civility.",
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
        personality = normalize_personality(payload.personality)
        created.append(
            Agent(
                id=deterministic_agent_id(
                    "user",
                    payload.name,
                    f"{payload.persona_text}|{personality.model_dump_json()}",
                    idx,
                ),
                name=payload.name.strip(),
                persona_text=payload.persona_text.strip(),
                role="user",
                personality=personality,
            )
        )
    return created
