from __future__ import annotations

from app.models import Agent


def _stance_tokens(stance: str) -> set[str]:
    keep = []
    for raw in stance.lower().replace(".", "").split():
        token = raw.strip(",;:!?")
        if len(token) >= 4:
            keep.append(token)
    return set(keep)


def _distance(a: Agent, b: Agent) -> float:
    tokens_a = _stance_tokens(a.stance)
    tokens_b = _stance_tokens(b.stance)
    if not tokens_a and not tokens_b:
        stance_gap = 0.0
    else:
        union = len(tokens_a | tokens_b) or 1
        overlap = len(tokens_a & tokens_b)
        stance_gap = 1.0 - (overlap / union)
    return stance_gap


def _pick_most_distant(pool: list[Agent], anchors: list[Agent]) -> Agent:
    def score(agent: Agent) -> tuple[float, str]:
        avg_distance = sum(_distance(agent, ref) for ref in anchors) / max(len(anchors), 1)
        return avg_distance, agent.id

    return max(pool, key=score)


def select_speakers(agents: list[Agent]) -> list[Agent]:
    mediators = [a for a in agents if a.role == "mediator"]
    users = [a for a in agents if a.role == "user"]
    if len(mediators) != 1:
        raise ValueError("Exactly 1 mediator (The Chair) is required")
    if len(users) < 4:
        raise ValueError("At least 4 user agents are required to run a round")

    ordered_users = sorted(users, key=lambda a: a.id)
    selected: list[Agent] = [ordered_users[0]]

    remaining = [u for u in users if u.id not in {a.id for a in selected}]
    while remaining:
        pick = _pick_most_distant(remaining, selected)
        selected.append(pick)
        remaining = [u for u in remaining if u.id != pick.id]

    return mediators + selected
