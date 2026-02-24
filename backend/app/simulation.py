from __future__ import annotations

from typing import Awaitable, Callable

from app.llm import (
    generate_agent_message,
    generate_chair_summary,
    generate_dashboard_visual,
    generate_table_action_and_visual,
    generate_visual_spec,
    AGENT_COLORS,
)
from app.metrics import compute_emergent_metrics
from app.models import (
    Agent, CellAnnotation, CellHighlight, PublicTurn, Reaction,
    RoundResult, State, TableAction, VisualSpec,
)
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
        message = truncate_to_words(message, 40)

        visual = None
        table_action = None
        if state.dataset_summary and speaker.role == "user":
            if state.dataset_columns and state.round_number >= 3:
                # Dashboard mode: visual only, no table_action
                visual_data = await generate_dashboard_visual(
                    speaker, state, message,
                    round_number=state.round_number,
                    column_names=state.dataset_columns,
                )
                if visual_data and isinstance(visual_data, dict) and visual_data.get("visual_type"):
                    try:
                        visual = VisualSpec(**visual_data)
                    except Exception:
                        pass
            elif state.dataset_columns:
                # Rounds 1-2: combined table action + visual generation
                speaker_idx = next(
                    (i for i, a in enumerate(state.agents) if a.id == speaker.id), 0
                )
                agent_color = AGENT_COLORS[speaker_idx % len(AGENT_COLORS)]
                action_data = await generate_table_action_and_visual(
                    speaker, state, message,
                    round_number=state.round_number,
                    column_names=state.dataset_columns,
                    row_count=state.world_state.get("dataset_row_count", 200),
                )
                try:
                    ta_raw = action_data.get("table_action")
                    if ta_raw:
                        # Enrich highlights and annotations with agent_id and color
                        highlights = []
                        for h in ta_raw.get("highlights", []):
                            highlights.append(CellHighlight(
                                row_start=h["row_start"],
                                row_end=h["row_end"],
                                columns=h["columns"],
                                color=agent_color,
                                agent_id=speaker.id,
                            ))
                        annotations = []
                        for a in ta_raw.get("annotations", []):
                            annotations.append(CellAnnotation(
                                row=a["row"],
                                column=a["column"],
                                text=str(a["text"])[:40],
                                agent_id=speaker.id,
                            ))
                        table_action = TableAction(
                            navigate_to=ta_raw.get("navigate_to", {"row": 0, "column": state.dataset_columns[0]}),
                            highlights=highlights,
                            annotations=annotations,
                        )
                    vis_raw = action_data.get("visual")
                    if vis_raw and isinstance(vis_raw, dict) and vis_raw.get("visual_type"):
                        visual = VisualSpec(**vis_raw)
                except Exception:
                    pass
            else:
                # Fallback: no dataset columns, use original visual generation
                visual_data = await generate_visual_spec(speaker, state, message, round_number=state.round_number)
                if visual_data:
                    try:
                        visual = VisualSpec(**visual_data)
                    except Exception:
                        visual = None

        turn = PublicTurn(speaker_id=speaker.id, message=message, visual=visual, table_action=table_action)
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
