from __future__ import annotations

from app.llm import generate_agent_message
from app.metrics import compute_emergent_metrics
from app.models import Agent, PublicTurn, Reaction, RoundResult, State
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
    librarian_lines = [t.message for t in turns if "emergent pattern" in t.message.lower()]
    if librarian_lines:
        return librarian_lines[-1]
    librarian_ids = {a.id for a in agents if a.role == "mediator" and a.name == "The Chaos Librarian"}
    for turn in reversed(turns):
        if turn.speaker_id in librarian_ids:
            return turn.message
    return "The group explored diverse angles while maintaining constructive energy."


def _drift_stance(agent: Agent, topic: str, round_number: int) -> None:
    anchor = agent.quirks[round_number % 3]
    tone = "collaborative trials" if agent.energy >= 0.5 else "careful checks"
    agent.stance = (
        f"{agent.name} now frames {topic} through {anchor}, favoring {tone} with civil debate."
    )


async def run_round(state: State) -> RoundResult:
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
        message = truncate_to_words(message, 100)
        turns.append(PublicTurn(speaker_id=speaker.id, message=message))

    speaker_ids = {speaker.id for speaker in speakers}
    non_speaking_users = [a for a in state.agents if a.role == "user" and a.id not in speaker_ids]
    reactions = [_reaction_for(agent, state.round_number) for agent in non_speaking_users]

    for agent in state.agents:
        if agent.role == "user":
            _drift_stance(agent, state.topic, state.round_number)

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
