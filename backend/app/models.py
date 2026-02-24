from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Role = Literal["user", "mediator"]


class Agent(BaseModel):
    id: str
    name: str
    persona_text: str
    quirks: list[str] = Field(min_length=3, max_length=3)
    stance: str
    energy: float = Field(ge=0.0, le=1.0)
    role: Role
    mbti_type: str | None = None

    @field_validator("stance")
    @classmethod
    def stance_is_single_sentence(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("stance cannot be empty")
        if cleaned[-1] not in ".!?":
            cleaned += "."
        return cleaned

    @field_validator("quirks")
    @classmethod
    def quirks_are_clean(cls, value: list[str]) -> list[str]:
        cleaned = [" ".join(q.strip().split()) for q in value if q.strip()]
        if len(cleaned) != 3:
            raise ValueError("quirks must contain exactly 3 non-empty items")
        return cleaned


class VisualSpec(BaseModel):
    """A visual contribution from an agent, rendered in the dashboard."""
    visual_type: str  # bar_chart, table, scatter, line_chart, stat_card, heatmap
    title: str
    data: dict | list
    description: str = ""


class PublicTurn(BaseModel):
    speaker_id: str
    message: str
    visual: VisualSpec | None = None


class Reaction(BaseModel):
    agent_id: str
    emoji: str
    micro_comment: str = Field(max_length=60)

    @field_validator("micro_comment")
    @classmethod
    def max_words(cls, value: str) -> str:
        compact = " ".join(value.strip().split())
        words = compact.split()
        if len(words) > 6:
            compact = " ".join(words[:6])
        return compact


class RoundResult(BaseModel):
    round_number: int
    speaker_ids: list[str]
    turns: list[PublicTurn]
    reactions: list[Reaction]
    emergent_pattern: str
    metrics: dict


class State(BaseModel):
    topic: str
    round_number: int = 0
    agents: list[Agent] = Field(default_factory=list)
    public_history: list[PublicTurn] = Field(default_factory=list)
    reactions: list[Reaction] = Field(default_factory=list)
    world_state: dict = Field(default_factory=dict)
    dataset_summary: str = ""


class UserAgentInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    persona_text: str = Field(min_length=1, max_length=500)
    energy: float = Field(default=0.6, ge=0.0, le=1.0)
    mbti_type: str | None = None


class TopicRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=240)


class AddAgentsRequest(BaseModel):
    user_agents: list[UserAgentInput] = Field(min_length=1, max_length=25)


class RunRequest(BaseModel):
    rounds: int = Field(default=1, ge=1, le=50)


class ChatMessageInput(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    agent_name: str = Field(min_length=1, max_length=80)
    agent_persona: str = Field(min_length=1, max_length=500)
    mbti_type: str = Field(default="", max_length=4)
    messages: list[ChatMessageInput] = Field(default_factory=list)
    user_message: str = Field(min_length=1, max_length=500)


class ResetRequest(BaseModel):
    topic: str | None = None


class InterveneRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice: str = Field(default="alloy")
