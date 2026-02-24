from __future__ import annotations

from typing import Awaitable, Callable

from app.llm import generate_agent_message, generate_chair_summary, generate_visual_spec
from app.metrics import compute_emergent_metrics
from app.models import Agent, PublicTurn, Reaction, RoundResult, State, VisualSpec
from app.safety import enforce_civility, truncate_to_words
from app.selection import select_speakers

EMOJIS = ["🙂", "🤔", "⚡", "📚", "🧩", "🌱", "🌀", "🛠️", "✨", "🧠"]


def _stable_index(value: str, mod: int) -> int:
    return sum(ord(c) for c in value) % mod


def _reaction_for(agent: Agent, round_number: int) -> Reaction:
    emoji = EMOJIS[_stable_index(agent.id + str(round_number), len(EMOJIS))]
    micro_templates = [
        "Noted, testing this next.",
        "Interesting tension, stay curious.",
        "I can build on that.",
        "Small step, then iterate.",
        "Pattern spotted, still open.",
    ]
    micro = micro_templates[_stable_index(agent.name + str(round_number), len(micro_templates))]
    micro = " ".join(micro.split()[:6])
    return Reaction(agent_id=agent.id, emoji=emoji, micro_comment=micro)


def _extract_emergent_pattern(turns: list[PublicTurn], agents: list[Agent]) -> str:
    chair_ids = {a.id for a in agents if a.role == "mediator"}
    for turn in reversed(turns):
        if turn.speaker_id in chair_ids:
            return turn.message
    return "The group explored diverse angles while maintaining constructive energy."


def _drift_stance(agent: Agent, topic: str, round_number: int) -> None:
    anchor = agent.quirks[round_number % 3]
    tone = "collaborative trials" if agent.energy >= 0.5 else "careful checks"
    agent.stance = (
        f"{agent.name} now frames {topic} through {anchor}, favoring {tone} with civil debate."
    )


async def run_round(
    state: State,
    on_turn: Callable[[PublicTurn, int], Awaitable[None]] | None = None,
) -> RoundResult:
    speakers = select_speakers(state.agents)
    state.round_number += 1

    turns: list[PublicTurn] = []
    for speaker in speakers:
        raw_message = await generate_agent_message(
            agent=speaker,
            state=state,
            active_turns=turns,
        )
        message = enforce_civility(raw_message)
        message = truncate_to_words(message, 125)

        visual = None
        if state.dataset_summary and speaker.role == "user":
            visual_data = await generate_visual_spec(speaker, state, message, round_number=state.round_number)
            if visual_data:
                try:
                    visual = VisualSpec(**visual_data)
                except Exception:
                    visual = None

        turn = PublicTurn(speaker_id=speaker.id, message=message, visual=visual)
        turns.append(turn)
        if on_turn:
            await on_turn(turn, state.round_number)

    speaker_ids = {speaker.id for speaker in speakers}
    non_speaking_users = [a for a in state.agents if a.role == "user" and a.id not in speaker_ids]
    reactions = [_reaction_for(agent, state.round_number) for agent in non_speaking_users]

    for agent in state.agents:
        if agent.role == "user":
            _drift_stance(agent, state.topic, state.round_number)

    chair = next((a for a in state.agents if a.role == "mediator"), None)
    if chair:
        summary_text = await generate_chair_summary(chair, state, turns)
        summary_turn = PublicTurn(speaker_id=chair.id, message=summary_text)
        turns.append(summary_turn)
        if on_turn:
            await on_turn(summary_turn, state.round_number)

    state.public_history.extend(turns)
    state.reactions.extend(reactions)
    emergent_pattern = _extract_emergent_pattern(turns, state.agents)
    state.world_state["last_emergent_pattern"] = emergent_pattern
    state.world_state["last_speaker_ids"] = [speaker.id for speaker in speakers]
    state.world_state["round"] = state.round_number

    metrics = compute_emergent_metrics(state)
    state.world_state["metrics"] = metrics
    return RoundResult(
        round_number=state.round_number,
        speaker_ids=[speaker.id for speaker in speakers],
        turns=turns,
        reactions=reactions,
        emergent_pattern=emergent_pattern,
        metrics=metrics,
    )
