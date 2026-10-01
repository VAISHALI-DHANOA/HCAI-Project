from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

from app.auto_visual import (
    compute_dashboard_narrative,
    compute_table_action_and_visual,
)
from app.analysis import (
    analysis_report, analysis_visual, combined_analysis_visual,
    compute_requested_analyses, verified_message,
)
from app.llm import (
    generate_agent_message,
    generate_data_contribution,
    generate_chair_summary,
)
from app.thesis_metrics import evaluate_thesis_metrics, personality_stability_error_payload
from app.models import (
    Agent, CellAnnotation, CellHighlight, PublicTurn, Reaction,
    RoundResult, State, TableAction,
)
from app.safety import enforce_civility, truncate_to_words
from app.selection import select_speakers

# Agent-specific highlight colors (with alpha for overlay)
AGENT_COLORS = [
    "#38bdf888",  # sky blue
    "#f9731688",  # orange
    "#a855f788",  # purple
    "#22c55e88",  # green
    "#ef444488",  # red
    "#eab30888",  # yellow
    "#ec489988",  # pink
    "#06b6d488",  # cyan
]

def _stable_index(value: str, mod: int) -> int:
    return sum(ord(c) for c in value) % mod


def _reaction_for(agent: Agent, round_number: int) -> Reaction:
    micro_templates = [
        "Noted, testing this next.",
        "Interesting tension, stay curious.",
        "I can build on that.",
        "Small step, then iterate.",
        "Pattern spotted, still open.",
    ]
    micro = micro_templates[_stable_index(agent.name + str(round_number), len(micro_templates))]
    micro = " ".join(micro.split()[:6])
    return Reaction(agent_id=agent.id, micro_comment=micro)


def _extract_emergent_pattern(turns: list[PublicTurn], agents: list[Agent]) -> str:
    chair_ids = {a.id for a in agents if a.role == "mediator"}
    for turn in reversed(turns):
        if turn.speaker_id in chair_ids:
            return turn.message
    return "The group explored diverse angles while maintaining constructive energy."


async def run_round(
    state: State,
    on_turn: Callable[[PublicTurn, int], Awaitable[None]] | None = None,
    csv_path: str | Path | None = None,
) -> RoundResult:
    state.round_number += 1
    speakers = select_speakers(state.agents, state.run_id, state.round_number)

    # Re-generate the dashboard narrative if the human request changed since
    # it was last produced.  This ensures dashboard visuals align with what
    # the human actually asked for, even when the intervention happens after
    # round 2 (when the narrative is normally created).
    if (
        state.round_number >= 3
        and state.dataset_summary
        and state.human_request
        and state.human_request != state.world_state.get("narrative_human_request", "")
    ):
        chair = next((a for a in state.agents if a.role == "mediator"), None)
        if chair:
            narrative = compute_dashboard_narrative(
                chair, state, state.public_history,
            )
            state.world_state["dashboard_narrative"] = narrative
            state.world_state["narrative_human_request"] = state.human_request

    turns: list[PublicTurn] = []
    verified_path = bool(state.dataset_summary)
    onboarding_speaker = next((a.id for a in speakers if a.role == "user"), None)
    for speaker in speakers:
        analysis = None
        analyses = []
        request = None
        redisplay = False
        generated = await (
            generate_data_contribution(speaker, state, turns)
            if verified_path and speaker.role == "user"
            else generate_agent_message(speaker, state, turns)
        )
        if verified_path and speaker.role == "user":
            request = generated.analysis_request
            if (request is None and generated.generation.source == "llm"
                    and state.round_number <= 2 and speaker.id == onboarding_speaker):
                # One real overview, persisted as a normal contribution and reused in round 2.
                request = {"operation": "dataset_overview", "columns": state.dataset_columns}
            if request is not None:
                redisplay = request.get("redisplay") is True
                analyses = compute_requested_analyses(request, csv_path, state.public_history + turns)
                analysis = analyses[0]
            if analyses and not any(a.status == "completed" for a in analyses):
                turn = PublicTurn(speaker_id=speaker.id,
                                  turn_type="participant", round_number=state.round_number,
                                  moderator_strategy_id=None,
                                  message=" ".join(analysis_report(a) for a in analyses),
                                  analysis=analysis, additional_analyses=analyses[1:], generation=generated.generation)
                turns.append(turn)
                if on_turn:
                    await on_turn(turn, state.round_number)
                continue
        message = enforce_civility(generated.text)
        # Data prompts already request short sentences; avoid cutting them mid-sentence.
        if not verified_path:
            message = truncate_to_words(message, 40)
        if analysis is not None:
            message = " ".join(verified_message(a) for a in analyses)

        visual = None
        table_action = None
        if analysis is not None:
            # Numeric facts always come from computation, never from the model.
            if redisplay or any(a.status == "completed" and not a.reused for a in analyses):
                visual = combined_analysis_visual(analyses) if len(analyses) > 1 else analysis_visual(analysis)
        if (state.dataset_summary and state.round_number <= 2 and speaker.role == "user"
                and (state.dataset_preview is None or state.dataset_preview["sample_rows"])):
            if state.dataset_columns:
                # Preserve table navigation/annotations during onboarding and data quality.
                speaker_idx = next(
                    (i for i, a in enumerate(state.agents) if a.id == speaker.id), 0
                )
                agent_color = AGENT_COLORS[speaker_idx % len(AGENT_COLORS)]
                action_data = compute_table_action_and_visual(
                    speaker, state, message,
                    round_number=state.round_number,
                    column_names=state.dataset_columns,
                    row_count=(len(state.dataset_preview["sample_rows"]) if state.dataset_preview is not None
                               else min(state.world_state.get("dataset_row_count", 200), 500)),
                )
                try:
                    ta_raw = action_data.get("table_action")
                    if ta_raw:
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
                except Exception:
                    pass

        turn = PublicTurn(
            speaker_id=speaker.id, message=message, visual=visual,
            turn_type="moderator_opening" if speaker.role == "mediator" else "participant",
            round_number=state.round_number,
            moderator_strategy_id=state.moderator_strategy_id if speaker.role == "mediator" else None,
            table_action=table_action, generation=generated.generation, analysis=analysis,
            additional_analyses=analyses[1:],
        )
        turns.append(turn)
        if on_turn:
            await on_turn(turn, state.round_number)

    speaker_ids = {speaker.id for speaker in speakers}
    non_speaking_users = [a for a in state.agents if a.role == "user" and a.id not in speaker_ids]
    reactions = [_reaction_for(agent, state.round_number) for agent in non_speaking_users]

    chair = next((a for a in state.agents if a.role == "mediator"), None)
    if chair:
        summary = await generate_chair_summary(chair, state, turns)
        summary_turn = PublicTurn(
            speaker_id=chair.id, message=summary.text, generation=summary.generation,
            turn_type="moderator_summary", round_number=state.round_number,
            moderator_strategy_id=state.moderator_strategy_id,
        )
        turns.append(summary_turn)
        if on_turn:
            await on_turn(summary_turn, state.round_number)

        # At end of round 2, generate the dashboard narrative
        if state.round_number == 2 and state.dataset_summary:
            all_history = state.public_history + turns
            narrative = compute_dashboard_narrative(chair, state, all_history)
            state.world_state["dashboard_narrative"] = narrative
            state.world_state["narrative_human_request"] = state.human_request

    state.public_history.extend(turns)
    state.reactions.extend(reactions)
    emergent_pattern = _extract_emergent_pattern(turns, state.agents)
    state.world_state["last_emergent_pattern"] = emergent_pattern
    state.world_state["last_speaker_ids"] = [speaker.id for speaker in speakers]
    state.world_state["round"] = state.round_number

    # Thesis metric failures are data, never round failures.
    try:
        thesis_metrics = await evaluate_thesis_metrics(state)
    except Exception:
        thesis_metrics = personality_stability_error_payload(state)
    state.world_state["thesis_metrics"] = thesis_metrics
    return RoundResult(
        round_number=state.round_number,
        speaker_ids=[speaker.id for speaker in speakers],
        turns=turns,
        reactions=reactions,
        emergent_pattern=emergent_pattern,
        thesis_metrics=thesis_metrics,
    )
