from __future__ import annotations

from collections import defaultdict

from app.models import Agent, SimulationState
from app.safety import BLOCKED_TERMS


def _stance_signature(stance: str) -> frozenset[str]:
    tokens = [w.strip(".,;:!?").lower() for w in stance.split()]
    return frozenset(t for t in tokens if len(t) >= 5)


def _pairwise_similarity(agents: list[Agent]) -> float:
    users = [a for a in agents if a.role == "user"]
    if len(users) < 2:
        return 1.0
    scores: list[float] = []
    for i in range(len(users)):
        for j in range(i + 1, len(users)):
            a = _stance_signature(users[i].stance)
            b = _stance_signature(users[j].stance)
            if not a and not b:
                scores.append(1.0)
            else:
                union = len(a | b) or 1
                inter = len(a & b)
                scores.append(inter / union)
    return sum(scores) / len(scores)


def _coalition_ids(users: list[Agent]) -> list[str]:
    buckets: dict[frozenset[str], list[str]] = defaultdict(list)
    for user in users:
        buckets[_stance_signature(user.stance)].append(user.id)
    coalitions = [members for members in buckets.values() if len(members) >= 2]
    if not coalitions:
        return []
    largest = max(coalitions, key=len)
    return sorted(largest)


def _civility_from_history(state: SimulationState) -> float:
    if not state.public_history:
        return 1.0
    combined = " ".join(turn.message.lower() for turn in state.public_history)
    hits = sum(combined.count(term) for term in BLOCKED_TERMS)
    penalty = min(0.8, hits * 0.1)
    return max(0.0, 1.0 - penalty)


def compute_emergent_metrics(state: SimulationState) -> dict:
    users = [a for a in state.agents if a.role == "user"]
    consensus = _pairwise_similarity(state.agents)
    avg_energy = sum(a.energy for a in users) / max(len(users), 1)
    energy_spread = sum(abs(a.energy - avg_energy) for a in users) / max(len(users), 1)
    polarization = min(1.0, max(0.0, (1.0 - consensus) * 0.75 + energy_spread * 0.5))
    civility = _civility_from_history(state)
    return {
        "consensus_score": round(consensus, 3),
        "polarization_score": round(polarization, 3),
        "detected_coalitions": _coalition_ids(users),
        "civility_score": round(civility, 3),
    }

