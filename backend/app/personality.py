from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

OCEAN_TRAITS = (
    "openness",
    "conscientiousness",
    "extraversion",
    "agreeableness",
    "neuroticism",
)

OceanLevel = Literal["low", "medium", "high"]
OCEAN_LEVELS: tuple[OceanLevel, ...] = ("low", "medium", "high")
OCEAN_LEVEL_VERSION = "ocean-low-medium-high-v1"
PERSONALITY_PRESET_VERSION = "research-presets-v2"
PERSONALITY_PROMPT_MAPPING_VERSION = "ocean-prompt-map-v3"


class OceanTraits(BaseModel):
    openness: OceanLevel = "medium"
    conscientiousness: OceanLevel = "medium"
    extraversion: OceanLevel = "medium"
    agreeableness: OceanLevel = "medium"
    neuroticism: OceanLevel = "medium"


class AgentPersonality(BaseModel):
    preset_id: str = "custom"
    role_goal: str = Field(default="", max_length=500)
    ocean: OceanTraits = Field(default_factory=OceanTraits)
    custom_instructions: str = Field(default="", max_length=1000)
    scale_version: str = OCEAN_LEVEL_VERSION
    preset_version: str = PERSONALITY_PRESET_VERSION
    prompt_mapping_version: str = PERSONALITY_PROMPT_MAPPING_VERSION

class PersonalityPreset(BaseModel):
    id: str
    name: str
    role_goal: str
    ocean: OceanTraits


PERSONALITY_PRESETS: dict[str, PersonalityPreset] = {
    "explorer": PersonalityPreset(
        id="explorer",
        name="Explorer",
        role_goal="Generate alternative interpretations, hypotheses, and relevant perspectives.",
        ocean=OceanTraits(openness="high", conscientiousness="medium", extraversion="medium", agreeableness="medium", neuroticism="medium"),
    ),
    "analyst": PersonalityPreset(
        id="analyst",
        name="Analyst",
        role_goal="Examine the available evidence, assumptions, and logical consistency of claims.",
        ocean=OceanTraits(openness="medium", conscientiousness="high", extraversion="medium", agreeableness="medium", neuroticism="medium"),
    ),
    "critic": PersonalityPreset(
        id="critic",
        name="Critic",
        role_goal="Identify weaknesses, counterarguments, and unsupported assumptions.",
        ocean=OceanTraits(openness="medium", conscientiousness="high", extraversion="medium", agreeableness="low", neuroticism="medium"),
    ),
    "integrator": PersonalityPreset(
        id="integrator",
        name="Integrator",
        role_goal="Connect competing contributions into a coherent synthesis while preserving relevant disagreement.",
        ocean=OceanTraits(openness="high", conscientiousness="medium", extraversion="medium", agreeableness="high", neuroticism="low"),
    ),
    "solver": PersonalityPreset(
        id="solver",
        name="Solver",
        role_goal="Develop concrete solutions, decisions, and actionable next steps from the discussion.",
        ocean=OceanTraits(openness="medium", conscientiousness="high", extraversion="medium", agreeableness="medium", neuroticism="low"),
    ),
}

CUSTOM_PERSONALITY = PersonalityPreset(
    id="custom",
    name="Custom",
    role_goal="",
    ocean=OceanTraits(),
)


TRAIT_BEHAVIOR_MAP: dict[str, dict[Literal["low", "medium", "high"], list[str]]] = {
    "openness": {
        "low": [
            "stay grounded in familiar, proven approaches",
            "ask whether novel ideas are necessary before adopting them",
        ],
        "medium": [
            "balance established approaches with selective exploration",
            "consider alternatives when they clarify the problem",
        ],
        "high": [
            "explore alternative explanations and competing hypotheses",
            "introduce unconventional but relevant perspectives",
        ],
    },
    "conscientiousness": {
        "low": [
            "keep the discussion flexible and avoid over-planning too early",
            "notice opportunities that rigid procedures might miss",
        ],
        "medium": [
            "combine structure with room for adaptation",
            "track key details without letting process dominate",
        ],
        "high": [
            "check claims carefully for completeness and consistency",
            "push for clear criteria, evidence, and actionable structure",
        ],
    },
    "extraversion": {
        "low": [
            "respond thoughtfully and prioritize considered contributions",
            "make concise points after weighing what others have said",
        ],
        "medium": [
            "engage others directly while leaving space for reflection",
            "alternate between proposing ideas and responding to others",
        ],
        "high": [
            "speak up actively and energize the exchange",
            "invite direct responses and keep the discussion moving",
        ],
    },
    "agreeableness": {
        "low": [
            "challenge weak claims directly while staying respectful",
            "prioritize accuracy over easy consensus",
        ],
        "medium": [
            "balance critique with constructive acknowledgment",
            "support useful ideas while questioning gaps",
        ],
        "high": [
            "seek common ground and reduce unnecessary friction",
            "frame disagreement in ways others can productively engage",
        ],
    },
    "neuroticism": {
        "low": [
            "stay calm under uncertainty and avoid overstating risks",
            "keep attention on solvable problems",
        ],
        "medium": [
            "notice risks without letting them dominate the discussion",
            "treat uncertainty as something to examine carefully",
        ],
        "high": [
            "surface risks, tensions, and failure modes early",
            "ask what could go wrong before the group commits",
        ],
    },
}


def list_personality_presets() -> list[PersonalityPreset]:
    return list(PERSONALITY_PRESETS.values())


def personality_from_preset(preset_id: str) -> AgentPersonality:
    preset = PERSONALITY_PRESETS.get(preset_id, CUSTOM_PERSONALITY)
    return AgentPersonality(
        preset_id=preset.id,
        role_goal=preset.role_goal,
        ocean=preset.ocean.model_copy(),
    )


def normalize_personality(raw: AgentPersonality | dict) -> AgentPersonality:
    """Validate the effective configuration without deriving behavior from preset_id."""
    return raw if isinstance(raw, AgentPersonality) else AgentPersonality.model_validate(raw)


def get_personality_catalog() -> dict:
    presets = [CUSTOM_PERSONALITY, *list_personality_presets()]
    return {
        "default_preset_id": "custom",
        "traits": [{"key": trait, "label": trait.capitalize()} for trait in OCEAN_TRAITS],
        "levels": list(OCEAN_LEVELS),
        "level_version": OCEAN_LEVEL_VERSION,
        "presets": [
            {**preset.model_dump(), "personality": personality_from_preset(preset.id).model_dump()}
            for preset in presets
        ],
    }


def build_personality_prompt(personality: AgentPersonality) -> str:
    lines: list[str] = []
    role_goal = personality.role_goal.strip()
    if role_goal:
        lines.extend(["FUNCTIONAL ROLE", role_goal, ""])

    lines.extend([
        "OCEAN PERSONALITY",
        "- Express the following tendencies through behavior; do not name trait levels or labels.",
    ])
    trait_values = personality.ocean.model_dump()
    for trait in OCEAN_TRAITS:
        level = trait_values[trait]
        for behavior in TRAIT_BEHAVIOR_MAP[trait][level]:
            lines.append(f"- {behavior}")

    if personality.custom_instructions.strip():
        lines.extend(["", "CUSTOM INSTRUCTIONS", personality.custom_instructions.strip()])

    return "\n".join(lines)
