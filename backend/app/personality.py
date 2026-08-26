from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

OCEAN_TRAITS = (
    "openness",
    "conscientiousness",
    "extraversion",
    "agreeableness",
    "neuroticism",
)

OCEAN_SCALE_MIN = 1
OCEAN_SCALE_MAX = 9
OCEAN_SCALE_MID = 5
OCEAN_SCALE_VERSION = "ocean-1-9-v1"
PERSONALITY_PRESET_VERSION = "research-presets-v1"
PERSONALITY_PROMPT_MAPPING_VERSION = "ocean-prompt-map-v1"


class OceanTraits(BaseModel):
    openness: int = Field(default=OCEAN_SCALE_MID, ge=OCEAN_SCALE_MIN, le=OCEAN_SCALE_MAX)
    conscientiousness: int = Field(default=OCEAN_SCALE_MID, ge=OCEAN_SCALE_MIN, le=OCEAN_SCALE_MAX)
    extraversion: int = Field(default=OCEAN_SCALE_MID, ge=OCEAN_SCALE_MIN, le=OCEAN_SCALE_MAX)
    agreeableness: int = Field(default=OCEAN_SCALE_MID, ge=OCEAN_SCALE_MIN, le=OCEAN_SCALE_MAX)
    neuroticism: int = Field(default=OCEAN_SCALE_MID, ge=OCEAN_SCALE_MIN, le=OCEAN_SCALE_MAX)


class AgentPersonality(BaseModel):
    preset_id: str = "custom"
    role_name: str = Field(default="Custom", min_length=1, max_length=80)
    role_goal: str = Field(default="Bring a distinctive, useful perspective to the discussion.", max_length=500)
    ocean: OceanTraits = Field(default_factory=OceanTraits)
    behavioral_rules: list[str] = Field(default_factory=list, max_length=12)
    custom_instructions: str = Field(default="", max_length=1000)
    scale_version: str = OCEAN_SCALE_VERSION
    preset_version: str = PERSONALITY_PRESET_VERSION
    prompt_mapping_version: str = PERSONALITY_PROMPT_MAPPING_VERSION

    @field_validator("behavioral_rules")
    @classmethod
    def clean_behavioral_rules(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for rule in value:
            compact = " ".join(str(rule).strip().split())
            if compact:
                cleaned.append(compact)
        return cleaned


class PersonalityPreset(BaseModel):
    id: str
    name: str
    description: str
    role_goal: str
    ocean: OceanTraits
    behavioral_rules: list[str]


PERSONALITY_PRESETS: dict[str, PersonalityPreset] = {
    "explorer": PersonalityPreset(
        id="explorer",
        name="Explorer",
        description="Surfaces new hypotheses, alternative explanations, and perspectives not yet considered.",
        role_goal="Explore alternative explanations, introduce new hypotheses, and surface neglected perspectives.",
        ocean=OceanTraits(openness=8, conscientiousness=5, extraversion=6, agreeableness=5, neuroticism=4),
        behavioral_rules=[
            "Actively propose alternative interpretations.",
            "Explore uncertainty and unresolved possibilities.",
            "Introduce perspectives not yet discussed.",
            "Avoid repeating arguments already made by others.",
        ],
    ),
    "analyst": PersonalityPreset(
        id="analyst",
        name="Analyst",
        description="Tests claims against evidence, structure, definitions, and measurable implications.",
        role_goal="Clarify evidence, identify patterns, and test whether claims follow from the available information.",
        ocean=OceanTraits(openness=6, conscientiousness=8, extraversion=4, agreeableness=5, neuroticism=4),
        behavioral_rules=[
            "Ask what evidence would support or weaken a claim.",
            "Separate observations from interpretations.",
            "Look for assumptions, definitions, and measurable criteria.",
            "Prefer precise reasoning over rhetorical force.",
        ],
    ),
    "critic": PersonalityPreset(
        id="critic",
        name="Critic",
        description="Challenges assumptions, searches for weak points, and prevents premature acceptance.",
        role_goal="Challenge assumptions, identify weaknesses, and prevent premature convergence on weak conclusions.",
        ocean=OceanTraits(openness=6, conscientiousness=8, extraversion=6, agreeableness=3, neuroticism=5),
        behavioral_rules=[
            "Challenge weak claims directly but constructively.",
            "Point out missing evidence and possible counterexamples.",
            "Prioritize correctness over social agreement.",
            "Do not agree merely to preserve harmony.",
        ],
    ),
    "integrator": PersonalityPreset(
        id="integrator",
        name="Integrator",
        description="Connects partial insights, resolves tensions, and builds coherent shared framing.",
        role_goal="Integrate competing arguments into a coherent synthesis without flattening important differences.",
        ocean=OceanTraits(openness=7, conscientiousness=6, extraversion=5, agreeableness=8, neuroticism=3),
        behavioral_rules=[
            "Connect compatible ideas from different agents.",
            "Name productive tensions instead of ignoring them.",
            "Translate disagreement into shared questions.",
            "Preserve minority concerns while building synthesis.",
        ],
    ),
    "solver": PersonalityPreset(
        id="solver",
        name="Solver",
        description="Moves discussion toward workable actions, decisions, and concrete next steps.",
        role_goal="Turn discussion into practical options, decisions, and next steps that can be tested.",
        ocean=OceanTraits(openness=5, conscientiousness=8, extraversion=6, agreeableness=6, neuroticism=3),
        behavioral_rules=[
            "Convert abstract ideas into concrete next steps.",
            "Identify tradeoffs and implementation constraints.",
            "Push for decisions when enough evidence is available.",
            "Suggest small tests before broad commitments.",
        ],
    ),
}

CUSTOM_PERSONALITY = PersonalityPreset(
    id="custom",
    name="Custom",
    description="A fully customized personality configured by the user.",
    role_goal="Bring a distinctive, useful perspective to the discussion.",
    ocean=OceanTraits(),
    behavioral_rules=[],
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


MBTI_TO_OCEAN_HINTS: dict[str, dict[str, int]] = {
    "E": {"extraversion": 7},
    "I": {"extraversion": 3},
    "S": {"openness": 4},
    "N": {"openness": 7},
    "T": {"agreeableness": 4},
    "F": {"agreeableness": 7},
    "J": {"conscientiousness": 7},
    "P": {"conscientiousness": 4},
}


def list_personality_presets() -> list[PersonalityPreset]:
    return list(PERSONALITY_PRESETS.values())


def personality_from_preset(preset_id: str) -> AgentPersonality:
    preset = PERSONALITY_PRESETS.get(preset_id, CUSTOM_PERSONALITY)
    return AgentPersonality(
        preset_id=preset.id,
        role_name=preset.name,
        role_goal=preset.role_goal,
        ocean=preset.ocean.model_copy(),
        behavioral_rules=list(preset.behavioral_rules),
    )


def build_legacy_personality(persona_text: str, mbti_type: str | None = None) -> AgentPersonality:
    values = OceanTraits().model_dump()
    if mbti_type:
        for letter in mbti_type:
            values.update(MBTI_TO_OCEAN_HINTS.get(letter.upper(), {}))
    return AgentPersonality(
        preset_id="custom",
        role_name="Custom",
        role_goal=persona_text.strip()[:500] or CUSTOM_PERSONALITY.role_goal,
        ocean=OceanTraits(**values),
        custom_instructions=(
            f"Legacy MBTI input: {mbti_type}. Preserve the user's persona text as the primary role context."
            if mbti_type else ""
        ),
    )


def normalize_personality(
    raw: AgentPersonality | dict | None,
    persona_text: str,
    mbti_type: str | None = None,
) -> AgentPersonality:
    if raw is None:
        return build_legacy_personality(persona_text, mbti_type)
    personality = raw if isinstance(raw, AgentPersonality) else AgentPersonality.model_validate(raw)
    preset = PERSONALITY_PRESETS.get(personality.preset_id)
    if preset:
        if not personality.role_name:
            personality.role_name = preset.name
        if not personality.role_goal:
            personality.role_goal = preset.role_goal
    return personality


def _intensity(value: int) -> Literal["low", "medium", "high"]:
    if value <= 3:
        return "low"
    if value >= 7:
        return "high"
    return "medium"


def build_personality_prompt(personality: AgentPersonality) -> str:
    lines = [
        "FUNCTIONAL ROLE",
        f"- Role: {personality.role_name}",
        f"- Goal: {personality.role_goal}",
        "",
        "PERSONALITY EXPRESSION",
        "- Express the following tendencies through behavior; do not name trait scores or labels.",
    ]
    trait_values = personality.ocean.model_dump()
    for trait in OCEAN_TRAITS:
        level = _intensity(trait_values[trait])
        for behavior in TRAIT_BEHAVIOR_MAP[trait][level]:
            lines.append(f"- {behavior}")

    if personality.behavioral_rules:
        lines.extend(["", "BEHAVIORAL RULES"])
        lines.extend(f"- {rule}" for rule in personality.behavioral_rules)

    if personality.custom_instructions.strip():
        lines.extend(["", "CUSTOM INSTRUCTIONS", personality.custom_instructions.strip()])

    return "\n".join(lines)
