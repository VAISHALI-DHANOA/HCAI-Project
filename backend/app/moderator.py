from __future__ import annotations

from pydantic import BaseModel

MODERATOR_STRATEGY_VERSION = "moderator-strategies-v1"
BASELINE_MODERATOR_STRATEGY_ID = "baseline"


class ModeratorStrategy(BaseModel):
    id: str
    name: str
    description: str
    prompt_rules: list[str]
    version: str = MODERATOR_STRATEGY_VERSION


MODERATOR_STRATEGIES: dict[str, ModeratorStrategy] = {
    "baseline": ModeratorStrategy(
        id="baseline",
        name="Current Chair",
        description="Existing Chair behavior used as the baseline condition.",
        prompt_rules=[],
    ),
    "facilitator": ModeratorStrategy(
        id="facilitator",
        name="Facilitator",
        description="Keeps different perspectives visible and invites underrepresented viewpoints.",
        prompt_rules=[
            "Keep different perspectives visible throughout the round.",
            "Encourage participation from agents whose viewpoints are underrepresented.",
            "Ask for overlooked or minority perspectives before the group settles.",
            "Avoid premature consensus and do not advocate your own position.",
        ],
    ),
    "devils_advocate": ModeratorStrategy(
        id="devils_advocate",
        name="Devil's Advocate",
        description="Challenges emerging consensus by asking for counterarguments and alternatives.",
        prompt_rules=[
            "Challenge emerging consensus when it appears under-examined.",
            "Request counterarguments and alternative explanations.",
            "Question weak assumptions, missing evidence, and fragile reasoning.",
            "Do not disagree randomly; target claims that need stronger support.",
        ],
    ),
}


def get_moderator_strategy(strategy_id: str | None) -> ModeratorStrategy:
    if not strategy_id:
        return MODERATOR_STRATEGIES[BASELINE_MODERATOR_STRATEGY_ID]
    return MODERATOR_STRATEGIES.get(strategy_id, MODERATOR_STRATEGIES[BASELINE_MODERATOR_STRATEGY_ID])


def build_moderator_strategy_prompt(strategy_id: str | None) -> str:
    strategy = get_moderator_strategy(strategy_id)
    if strategy.id == BASELINE_MODERATOR_STRATEGY_ID:
        return ""
    lines = [
        "",
        "MODERATOR STRATEGY",
        f"- Strategy: {strategy.name}",
        *[f"- {rule}" for rule in strategy.prompt_rules],
    ]
    return "\n".join(lines)
