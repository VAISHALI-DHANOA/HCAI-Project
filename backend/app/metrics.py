from __future__ import annotations

from collections import defaultdict

from app.models import Agent, State
from app.safety import BLOCKED_TERMS


def _stance_signature(stance: str) -> frozenset[str]:
    tokens = [w.strip(".,;:!?").lower() for w in stance.split()]
    return frozenset(t for t in tokens if len(t) >= 5)


def _latest_agent_text(state: State) -> dict[str, str]:
    latest = {agent.id: agent.stance for agent in state.agents if agent.role == "user"}
    user_ids = set(latest)
    for turn in state.public_history:
        if turn.speaker_id in user_ids:
            latest[turn.speaker_id] = turn.message
    return latest


def _pairwise_similarity(state: State) -> float:
    agents = state.agents
    users = [a for a in agents if a.role == "user"]
    if len(users) < 2:
        return 1.0
    latest_text = _latest_agent_text(state)
    scores: list[float] = []
    for i in range(len(users)):
        for j in range(i + 1, len(users)):
            a = _stance_signature(latest_text.get(users[i].id, users[i].stance))
            b = _stance_signature(latest_text.get(users[j].id, users[j].stance))
            if not a and not b:
                scores.append(1.0)
            else:
                union = len(a | b) or 1
                inter = len(a & b)
                scores.append(inter / union)
    return sum(scores) / len(scores)


def _coalition_ids(users: list[Agent], latest_text: dict[str, str]) -> list[str]:
    buckets: dict[frozenset[str], list[str]] = defaultdict(list)
    for user in users:
        buckets[_stance_signature(latest_text.get(user.id, user.stance))].append(user.id)
    coalitions = [members for members in buckets.values() if len(members) >= 2]
    if not coalitions:
        return []
    largest = max(coalitions, key=len)
    return sorted(largest)


def _civility_from_history(state: State) -> float:
    if not state.public_history:
        return 1.0
    combined = " ".join(turn.message.lower() for turn in state.public_history)
    hits = sum(combined.count(term) for term in BLOCKED_TERMS)
    penalty = min(0.8, hits * 0.1)
    return max(0.0, 1.0 - penalty)


def compute_emergent_metrics(state: State) -> dict:
    users = [a for a in state.agents if a.role == "user"]
    latest_text = _latest_agent_text(state)
    consensus = _pairwise_similarity(state)
    avg_energy = sum(a.energy for a in users) / max(len(users), 1)
    energy_spread = sum(abs(a.energy - avg_energy) for a in users) / max(len(users), 1)
    polarization = min(1.0, max(0.0, (1.0 - consensus) * 0.75 + energy_spread * 0.5))
    civility = _civility_from_history(state)
    return {
        "consensus_score": round(consensus, 3),
        "polarization_score": round(polarization, 3),
        "detected_coalitions": _coalition_ids(users, latest_text),
        "civility_score": round(civility, 3),
    }
