from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

MODERATOR_STRATEGY_VERSION = "moderator-strategies-v2"
DEFAULT_MODERATOR_STRATEGY_ID = "consensus"


class ModeratorStrategy(BaseModel):
    id: str
    name: str
    description: str
    opening_rules: list[str]
    summary_rules: list[str]
    summary_request: str
    version: str = MODERATOR_STRATEGY_VERSION


MODERATOR_STRATEGIES: dict[str, ModeratorStrategy] = {
    "consensus": ModeratorStrategy(
        id="consensus",
        name="Consensus",
        description="Finds shared conclusions and workable next steps while acknowledging unresolved concerns.",
        opening_rules=[
            "Identify common ground and invite the group to work toward a shared conclusion.",
            "Ask what evidence or tradeoffs could help resolve remaining differences.",
            "Do not present agreement as established when objections remain unresolved.",
        ],
        summary_rules=[
            "Synthesize areas of agreement into a shared conclusion and practical next steps.",
            "Acknowledge unresolved objections and distinguish tentative agreement from settled conclusions.",
            "Focus on themes and next steps, not listing who said what.",
        ],
        summary_request="Summarize shared conclusions, unresolved concerns, and next steps in 30 words or fewer.",
    ),
    "facilitator": ModeratorStrategy(
        id="facilitator",
        name="Facilitator",
        description="Keeps different perspectives visible and invites underrepresented viewpoints.",
        opening_rules=[
            "Keep different perspectives visible throughout the round.",
            "Encourage participation from agents whose viewpoints are underrepresented.",
            "Ask for overlooked or minority perspectives before the group settles.",
            "Avoid premature consensus and do not advocate your own position.",
            "If several rounds remain within the same conceptual frame, deliberately reopen the discussion with a substantially different perspective or framing.",
            "Avoid turning the discussion into assignments, deadlines, ownership, or implementation planning unless the topic explicitly requires it.",
        ],
        summary_rules=[
            "Map the distinct perspectives expressed, including minority views and unresolved tensions.",
            "Identify perspectives, assumptions, or questions that remain underexplored.",
            "Do not merge disagreement into a shared conclusion or push for a decision.",
        ],
        summary_request="Summarize distinct perspectives, unresolved tensions, and an open question in 30 words or fewer.",
    ),
    "devils_advocate": ModeratorStrategy(
        id="devils_advocate",
        name="Devil's Advocate",
        description="Challenges emerging consensus by asking for counterarguments and alternatives.",
        opening_rules=[
            "Challenge emerging consensus when it appears under-examined.",
            "Request counterarguments and alternative explanations.",
            "Question weak assumptions, missing evidence, and fragile reasoning.",
            "Do not disagree randomly; target claims that need stronger support.",
            "If several rounds remain within the same conceptual frame, challenge the framing itself rather than producing increasingly detailed objections to the same proposal.",
            "Ask whether the group may be solving the wrong problem when the discussion becomes narrowly focused.",
        ],
        summary_rules=[
            "Identify the strongest unresolved counterargument and the assumption most in need of testing.",
            "Name missing evidence or an alternative explanation that could overturn the leading claim.",
            "Do not conclude with consensus or endorse the leading position merely because it is popular.",
            "Highlight when the discussion itself may be trapped in an overly narrow framing."
        ],
        summary_request="Summarize the strongest counterargument, missing evidence, and a test of the leading claim in 30 words or fewer.",
    ),
}


def get_moderator_strategy(strategy_id: str | None = None) -> ModeratorStrategy:
    key = strategy_id or DEFAULT_MODERATOR_STRATEGY_ID
    if key not in MODERATOR_STRATEGIES:
        raise ValueError(f"Unknown moderator strategy: {key}")
    return MODERATOR_STRATEGIES[key]


def build_moderator_strategy_prompt(
    strategy_id: str | None, phase: Literal["opening", "summary"] = "opening",
) -> str:
    strategy = get_moderator_strategy(strategy_id)
    rules = strategy.opening_rules if phase == "opening" else strategy.summary_rules
    return "\n".join([
        "", "MODERATOR STRATEGY", f"- Strategy: {strategy.name}",
        *[f"- {rule}" for rule in rules],
    ])
