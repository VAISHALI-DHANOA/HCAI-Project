"""Render stored turn metadata for model prompts."""
from __future__ import annotations

from app.models import PublicTurn, State
from app.moderator import MODERATOR_STRATEGIES

TURN_LABELS = {
    "moderator_opening": "Moderator opening",
    "participant": "Participant",
    "moderator_summary": "Moderator summary",
    "human": "Human participant",
}


def format_turn(state: State, turn: PublicTurn) -> str:
    """Render explicit turn metadata for model context."""
    agent = next((agent for agent in state.agents if agent.id == turn.speaker_id), None)
    name = "Human Participant" if turn.speaker_id == "human" else agent.name if agent else "Unknown"
    header = [f"Round {turn.round_number}", TURN_LABELS[turn.turn_type]]
    if turn.turn_type in ("moderator_opening", "moderator_summary"):
        header.append(f"Strategy: {MODERATOR_STRATEGIES[turn.moderator_strategy_id].name}")
    return f"[{' | '.join(header)}]\n{name}: {turn.message}"
