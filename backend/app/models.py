from __future__ import annotations

import re
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.personality import AgentPersonality
from app.moderator import DEFAULT_MODERATOR_STRATEGY_ID

Role = Literal["user", "mediator"]


class Agent(BaseModel):
    id: str
    name: str
    persona_text: str
    role: Role
    personality: AgentPersonality | None = None


class VisualSpec(BaseModel):
    """A visual contribution from an agent, rendered in the dashboard."""
    visual_type: str  # bar_chart, table, scatter, line_chart, stat_card, heatmap
    title: str
    data: dict | list
    description: str = ""


class CellHighlight(BaseModel):
    row_start: int
    row_end: int
    columns: list[str]
    color: str  # hex with alpha, e.g. "#38bdf844"
    agent_id: str


class CellAnnotation(BaseModel):
    row: int
    column: str
    text: str = Field(max_length=40)
    agent_id: str


class TableAction(BaseModel):
    navigate_to: dict  # {"row": int, "column": str}
    highlights: list[CellHighlight] = Field(default_factory=list)
    annotations: list[CellAnnotation] = Field(default_factory=list)


class GenerationMetadata(BaseModel):
    source: Literal["llm", "fallback"]
    operation: Literal["discussion", "summary", "chat"]
    model: str
    max_tokens: int
    temperature: float
    timeout_seconds: float
    error_type: str | None = None


class DataContributionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
    analysis_request: dict | None = None


class AnalysisFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operator: Literal["eq", "gt", "gte", "lt", "lte"]
    value: str | int | float | bool


class AnalysisSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: str
    x_column: str | None = None
    y_column: str | None = None
    group_by: str | None = None
    filters: dict[str, str | int | float | bool | AnalysisFilter] = Field(default_factory=dict)
    columns: list[str] = Field(default_factory=list)
    aggregation: str = "mean"
    grouping: Literal["categories", "quartiles"] = "categories"
    limit: int = Field(default=10, ge=1, le=30)

    @field_validator("filters", mode="before")
    @classmethod
    def empty_filters(cls, value):
        if value is None:
            return {}
        if isinstance(value, dict):
            value = value.copy()
            operators = {">": "gt", ">=": "gte", "<": "lt", "<=": "lte"}
            for column, condition in value.items():
                if isinstance(condition, str):
                    match = re.fullmatch(r"\s*(>=|<=|>|<)\s*(-?\d+(?:\.\d+)?)\s*", condition)
                    if match:
                        value[column] = {"operator": operators[match[1]], "value": float(match[2])}
        return value

    @field_validator("columns", mode="before")
    @classmethod
    def empty_columns(cls, value):
        return [] if value is None else value


class AnalysisResult(BaseModel):
    status: Literal["completed", "not_performed"]
    spec: AnalysisSpec | None = None
    sample_size: int = 0
    pearson_r: float | None = None
    groups: list[dict] = Field(default_factory=list)
    chart_data: dict | None = None
    error: str | None = None
    values: dict = Field(default_factory=dict)
    dataset_version: str = ""
    reused: bool = False
    request: dict | None = None


TurnType = Literal["moderator_opening", "participant", "moderator_summary", "human"]


class PublicTurn(BaseModel):
    speaker_id: str
    message: str
    turn_type: TurnType
    round_number: int = Field(ge=0)
    moderator_strategy_id: str | None
    visual: VisualSpec | None = None
    table_action: TableAction | None = None
    generation: GenerationMetadata | None = None
    analysis: AnalysisResult | None = None
    additional_analyses: list[AnalysisResult] = Field(default_factory=list)


class Reaction(BaseModel):
    agent_id: str
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
    thesis_metrics: dict = Field(default_factory=dict)
    experiment: dict = Field(default_factory=dict)


class State(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid4().hex)
    revision: int = 0
    topic: str
    round_number: int = 0
    agents: list[Agent] = Field(default_factory=list)
    public_history: list[PublicTurn] = Field(default_factory=list)
    reactions: list[Reaction] = Field(default_factory=list)
    rounds: list[RoundResult] = Field(default_factory=list)
    world_state: dict = Field(default_factory=dict)
    dataset_summary: str = ""
    dataset_columns: list[str] = Field(default_factory=list)
    dataset_preview: dict | None = None
    human_request: str = ""
    moderator_strategy_id: str = DEFAULT_MODERATOR_STRATEGY_ID


class UserAgentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    persona_text: str = Field(min_length=1, max_length=500)
    personality: AgentPersonality


class TopicRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=240)


class AddAgentsRequest(BaseModel):
    user_agents: list[UserAgentInput] = Field(min_length=1, max_length=25)


class DraftAgentInput(UserAgentInput):
    id: str | None = None


class SyncAgentsRequest(BaseModel):
    run_id: str
    revision: int
    user_agents: list[DraftAgentInput] = Field(max_length=25)


class RunRequest(BaseModel):
    rounds: int = Field(default=1, ge=1, le=50)


class ModeratorStrategyRequest(BaseModel):
    strategy_id: str = Field(min_length=1, max_length=80)


class ChatMessageInput(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(min_length=1, max_length=80)
    agent_persona: str = Field(min_length=1, max_length=500)
    personality: AgentPersonality
    messages: list[ChatMessageInput] = Field(default_factory=list)
    user_message: str = Field(min_length=1, max_length=500)


class ResetRequest(BaseModel):
    topic: str | None = None


class EndSessionRequest(BaseModel):
    duration_seconds: int = Field(ge=0, le=31_536_000)


class DisplayTimeRequest(BaseModel):
    seconds: int = Field(ge=1, le=300)


class InterveneRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice: str = Field(default="alloy")
