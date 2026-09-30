from __future__ import annotations

from collections import defaultdict

from app.models import Agent, State
from app.safety import BLOCKED_TERMS

METRICS_POLICY_VERSION = "exclude-marked-fallback-v2"


def _text_signature(text: str) -> frozenset[str]:
    tokens = [w.strip(".,;:!?").lower() for w in text.split()]
    return frozenset(t for t in tokens if len(t) >= 5)


def _latest_agent_text(state: State) -> dict[str, str]:
    user_ids = {agent.id for agent in state.agents if agent.role == "user"}
    latest = {}
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
            a = _text_signature(latest_text[users[i].id])
            b = _text_signature(latest_text[users[j].id])
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
        buckets[_text_signature(latest_text[user.id])].append(user.id)
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
    original = state
    excluded = [turn for turn in state.public_history if turn.generation and turn.generation.source == "fallback"]
    history = [turn for turn in state.public_history if not (turn.generation and turn.generation.source == "fallback")]
    valid_ids = {turn.speaker_id for turn in history}
    failed_only_ids = {turn.speaker_id for turn in excluded} - valid_ids
    state = state.model_copy(update={
        "public_history": history,
    })
    users = [a for a in state.agents if a.role == "user"]
    latest_text = _latest_agent_text(state)
    missing_ids = sorted(a.id for a in users if a.id not in latest_text)
    insufficient = len(users) < 2 or bool(missing_ids)
    consensus = None if insufficient else _pairwise_similarity(state)
    polarization = None if consensus is None else min(1.0, max(0.0, (1.0 - consensus) * 0.75))
    civility = _civility_from_history(state)
    return {
        "consensus_score": None if consensus is None else round(consensus, 3),
        "polarization_score": None if polarization is None else round(polarization, 3),
        "detected_coalitions": [] if insufficient else _coalition_ids(users, latest_text),
        "civility_score": None if excluded and not history else round(civility, 3),
        "evaluation": {
            "policy_version": METRICS_POLICY_VERSION,
            "status": "insufficient_data" if insufficient else "available",
            "excluded_fallback_turns": len(excluded),
            "excluded_agent_ids": sorted(a.id for a in original.agents if a.id in failed_only_ids and a.role == "user"),
            "eligible_participant_count": len(users),
            "included_turns": len(history),
            "prior_valid_text_agent_ids": sorted(
                a.id for a in users
                if a.id in valid_ids and next(
                    (bool(t.generation and t.generation.source == "fallback")
                     for t in reversed(original.public_history) if t.speaker_id == a.id), False
                )
            ),
            "missing_contribution_agent_ids": missing_ids,
            "unannotated_turns_included": sum(turn.generation is None for turn in history),
        },
    }
