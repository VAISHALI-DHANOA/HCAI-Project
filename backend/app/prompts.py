"""Pure prompt construction. Personality and moderator rules have their own owners."""
from __future__ import annotations

import json

from app.models import Agent, ChatMessageInput, PublicTurn, State
from app.moderator import DEFAULT_MODERATOR_STRATEGY_ID, build_moderator_strategy_prompt, get_moderator_strategy
from app.personality import AgentPersonality, build_personality_prompt, normalize_personality

VISUAL_REQUEST = "Generate the visual spec now."


def build_test_chat_messages(messages: list[ChatMessageInput], user_message: str) -> list[dict]:
    return [
        *[{"role": "user" if msg.role == "user" else "assistant", "content": msg.content} for msg in messages],
        {"role": "user", "content": user_message},
    ]

ROUND_PROMPTS = {
    1: "DATA ONBOARDING: Introduce the dataset to the team. Describe what this data represents, key columns, data types, and overall scope. Help everyone understand what we're working with.",
    2: "DATA QUALITY & PROCESSING: Identify data quality issues — missing values, suspicious patterns, columns that need cleaning or transformation. Recommend specific preprocessing steps.",
    3: "VISUALIZATION & PATTERNS: Create visualizations to explore the data. Propose and generate charts that reveal distributions, comparisons, and trends. Agents should create visuals that highlight something meaningful.",
    4: "DEEP EXPLORATION: Use visualizations and cross-column analysis to dig deeper. Explore relationships between variables — how do discounts affect profit? Which regions have more returns? What drives support costs?",
    5: "INSIGHTS & RECOMMENDATIONS: Synthesize findings into actionable insights. What are the key takeaways? What business decisions should this data inform? Summarize the most important discoveries.",
}
DEFAULT_ROUND_PROMPT = "Continue exploring the data, building on all previous findings and refining your analysis with new evidence."


def _build_chair_system_prompt(
    agent: Agent, topic: str, round_number: int,
    dataset_context: str = "", human_request: str = "",
    moderator_strategy_id: str = DEFAULT_MODERATOR_STRATEGY_ID,
) -> str:
    human_directive = ""
    if human_request:
        human_directive = (
            f"\n*** HUMAN PARTICIPANT DIRECTIVE ***\n"
            f"A human participant has intervened with this request:\n"
            f'"{human_request}"\n'
            f"You MUST redirect the discussion toward this request. Frame your opening "
            f"question around it and steer all participants to address it.\n"
        )

    base = (
        f'You are "{agent.name}", a mediator in a multi-agent deliberation about: {topic}\n'
        f"\n"
        f"This is round {round_number} of the discussion.\n"
        f"{human_directive}"
        f"\n"
        f"YOUR ROLE:\n"
        f"- Open the round by posing a focused question or framing the next angle to explore\n"
        f"- Facilitate fair turn-taking among participants\n"
        f"- Keep the conversation civil and on-track\n"
        f"- Do NOT summarize previous rounds; a separate summary happens at the end\n"
        f"\n"
        f"CONSTRAINTS:\n"
        f"- Respond in 25 words maximum — be concise\n"
        f"- Stay neutral; do not advocate for a specific position\n"
        f"- Address participants by name when referencing their points\n"
        f"- Do not use markdown formatting, bullet points, or numbered lists\n"
        f"- Write in a natural conversational tone as if speaking aloud in a meeting"
    )
    base += build_moderator_strategy_prompt(moderator_strategy_id, "opening")
    if dataset_context:
        base += f"\n\nDATASET CONTEXT (the team is analyzing this data):\n{dataset_context}\n"
    return base


def _build_user_system_prompt(
    agent: Agent, topic: str, round_number: int,
    dataset_context: str = "", human_request: str = "",
) -> str:
    personality = normalize_personality(agent.personality)
    personality_prompt = build_personality_prompt(personality)

    human_directive = ""
    if human_request:
        human_directive = (
            f"\n*** HUMAN PARTICIPANT DIRECTIVE ***\n"
            f"A human participant has intervened with this request:\n"
            f'"{human_request}"\n'
            f"You MUST change your analysis to address this request. Your response "
            f"should directly engage with what the human asked for, applying your "
            f"unique perspective and expertise to it.\n"
        )

    base = (
        f'You are "{agent.name}", a participant in a multi-agent deliberation about: {topic}\n'
        f"\n"
        f"Your persona: {agent.persona_text}\n"
        f"Treat the perspective and priorities described in your persona as your stance on the topic.\n"
        f"This is round {round_number} of the discussion.\n"
        f"{human_directive}"
        f"\n"
        f"{personality_prompt}\n"
        f"\n"
        f"YOUR ROLE:\n"
        f"- Let the agent configuration above guide what you contribute and how you communicate\n"
        f"- Respond to what others have said; build on, challenge, or refine their ideas\n"
        f"\n"
        f"CONSTRAINTS:\n"
        f"- Respond in 25 words maximum — be concise and punchy\n"
        f"- Do not break character or reference the simulation\n"
        f"- Do not use markdown formatting, bullet points, or numbered lists\n"
        f"- Engage with prior contributions when relevant, but do not force a question or explicit invitation in every response.\n"
        f"- Write in a natural conversational tone as if speaking aloud in a meeting"
    )
    if dataset_context:
        base += f"\n\nDATASET CONTEXT (use this data in your analysis):\n{dataset_context}\n"
    return base


def build_system_prompt(
    agent: Agent, topic: str, round_number: int,
    dataset_context: str = "", human_request: str = "",
    moderator_strategy_id: str = DEFAULT_MODERATOR_STRATEGY_ID,
) -> str:
    if agent.role == "mediator":
        return _build_chair_system_prompt(
            agent, topic, round_number, dataset_context, human_request, moderator_strategy_id
        )
    return _build_user_system_prompt(agent, topic, round_number, dataset_context, human_request)


def _format_conversation_history(
    state: State,
    active_turns: list[PublicTurn],
    speaker: Agent,
) -> list[dict]:
    recent_history = state.public_history[-12:]
    all_context_turns = recent_history + active_turns

    round_hint = ""
    if state.dataset_summary:
        round_hint = ROUND_PROMPTS.get(state.round_number, DEFAULT_ROUND_PROMPT)
        round_hint = f"\nROUND FOCUS: {round_hint}\n"

    if not all_context_turns:
        return [
            {
                "role": "user",
                "content": (
                    f'You are starting the discussion on the topic: "{state.topic}"\n'
                    f"No one has spoken yet. Please open the conversation."
                    f"{round_hint}"
                ),
            }
        ]

    agent_names = {a.id: a.name for a in state.agents}
    agent_names["human"] = "Human Participant"
    lines = []
    has_human_input = False
    for turn in all_context_turns:
        name = agent_names.get(turn.speaker_id, "Unknown")
        lines.append(f"{name}: {turn.message}")
        if state.dataset_summary and turn.analysis is not None:
            lines.append("Backend analysis result: " + turn.analysis.model_dump_json(exclude={"chart_data"}))
        if turn.speaker_id == "human":
            has_human_input = True

    transcript = "\n".join(lines)
    if state.dataset_summary:
        # Keep verified evidence available after the short conversation window moves on.
        seen = set()
        evidence = []
        for turn in reversed(state.public_history + active_turns):
            for result in [turn.analysis, *turn.additional_analyses]:
                if result and result.status == "completed":
                    key = result.spec.model_dump_json()
                    if key not in seen:
                        seen.add(key)
                        evidence.append(result.model_dump_json(exclude={"chart_data", "request"}))
            if len(evidence) >= 8:
                break
        if evidence:
            transcript += "\nKnown completed backend analyses:\n" + "\n".join(evidence[:8])

    human_note = ""
    if has_human_input and state.human_request:
        human_note = (
            "\nA human participant has spoken in the discussion above. "
            "You MUST directly acknowledge and respond to their input. \n"
        )
    elif has_human_input:
        human_note = (
            "\nHuman messages above are part of the discussion history. "
            "They may still inform or shape the ongoing discussion when relevant, "
            "but they are not new or pending requests. "
            "Do not re-answer them as if they had just been asked again, "
            "and do not address 'Human Participant' directly unless it is naturally relevant.\n"
        )

    human_request_note = ""
    if state.human_request:
        human_request_note = (
            f"\n*** PRIORITY: HUMAN REQUEST ***\n"
            f'The human participant asked: "{state.human_request}"\n'
            f"You MUST pivot your response to address this request. "
            f"Do NOT continue with the previous analysis direction — "
            f"redirect your expertise toward what the human asked for.\n"
        )

    return [
        {
            "role": "user",
            "content": (
                f"{human_request_note}"
                f"Here is the recent conversation:\n\n{transcript}\n\n"
                f"{round_hint}"
                f"{human_note}"
                f"Now respond as {speaker.name}. "
                f"Remember your persona, traits, and constraints."
            ),
        }
    ]

def build_chair_summary_prompt(
    chair: Agent,
    state: State,
    round_turns: list[PublicTurn],
) -> tuple[str, list[dict]]:
    agent_names = {a.id: a.name for a in state.agents}
    lines = [f"{agent_names.get(t.speaker_id, 'Unknown')}: {t.message}" for t in round_turns]
    if state.dataset_summary:
        lines.extend("Backend analysis result: " + turn.analysis.model_dump_json(exclude={"chart_data"})
                     for turn in round_turns if turn.analysis is not None)
        lines.extend("Backend analysis result: " + result.model_dump_json(exclude={"chart_data"})
                     for turn in round_turns for result in turn.additional_analyses)
    transcript = "\n".join(lines)

    human_request_note = ""
    if state.human_request:
        human_request_note = (
            f"\nHUMAN REQUEST: The human participant asked: \"{state.human_request}\"\n"
            f"Your summary MUST acknowledge this request and reflect it according to the selected moderator strategy.\n"
        )

    system_prompt = (
        f'You are "{chair.name}", the meeting facilitator.\n'
        f"Topic: {state.topic}\n"
        f"This was round {state.round_number}.\n\n"
        f"{human_request_note}"
        f"YOUR TASK:\n"
        f"{build_moderator_strategy_prompt(state.moderator_strategy_id, 'summary')}\n\n"
        f"CONSTRAINTS:\n"
        f"- 20 words maximum — be concise\n"
        f"- Do not list participant names\n"
        f"- Do not use generic phrases like 'good discussion' or 'diverse perspectives'\n"
        f"- Do not use markdown formatting\n"
        f"- Write in a natural conversational tone"
    )

    if state.dataset_summary:
        system_prompt += "\nOnly completed backend analysis results are evidence of performed analyses. Do not repeat unsupported findings as facts. Summarize qualitatively without numbers; each analysis contribution already reports its backend measurements. If no result exists, summarize proposed next steps rather than findings."

    messages = [
        {
            "role": "user",
            "content": (
                f"Here is what was said this round:\n\n{transcript}\n\n"
                f"{get_moderator_strategy(state.moderator_strategy_id).summary_request}"
            ),
        }
    ]

    return system_prompt, messages

VISUAL_ROUND_HINTS = {
    1: "For round 1 (data onboarding), prefer stat_card or table visuals that give an overview of the dataset — column counts, data types, basic statistics.",
    2: "For round 2 (data quality), prefer table or stat_card visuals showing missing values, null counts, or data quality metrics that need attention.",
    3: "For round 3 (visualization), prefer bar_chart or line_chart visuals that reveal distributions, category comparisons, or trends in the data.",
    4: "For round 4 (deep exploration), prefer scatter or heatmap visuals that show relationships between variables — correlations, cross-column analysis.",
    5: "For round 5 (insights), prefer bar_chart or stat_card visuals that summarize key findings and actionable business metrics.",
}

def build_visual_prompt(agent: Agent, state: State, agent_message: str, round_number: int = 0) -> str:
    round_visual_hint = VISUAL_ROUND_HINTS.get(round_number, "Choose the most appropriate visual type for the analysis being discussed.")

    visual_system = (
        f'You are "{agent.name}" generating a data visualization specification.\n'
        f"Your persona: {agent.persona_text}\n"
        f"\nDATASET:\n{state.dataset_summary}\n"
        f"\nYour message this round was: {agent_message}\n"
        f"\nROUND GUIDANCE: {round_visual_hint}\n"
        f"\nGenerate a JSON object describing a visual contribution. The JSON MUST have:\n"
        f'- "visual_type": one of "bar_chart", "table", "scatter", "line_chart", "stat_card", "heatmap"\n'
        f'- "title": short descriptive title\n'
        f'- "data": the chart data payload:\n'
        f'  For bar_chart/line_chart: {{"labels": [...], "values": [...], "series_name": "..."}}\n'
        f'  For scatter: {{"points": [{{"x": num, "y": num}}, ...], "x_label": "...", "y_label": "..."}}\n'
        f'  For table: {{"headers": [...], "rows": [[...], ...]}}\n'
        f'  For stat_card: {{"stats": [{{"label": "...", "value": "..."}}, ...]}}\n'
        f'  For heatmap: {{"headers": [...], "rows": [[...], ...]}}\n'
        f'- "description": one sentence about what this shows\n'
        f"\nUse realistic data values based on the dataset statistics provided.\n"
        f"Respond with ONLY the JSON object, no markdown, no explanation."
    )
    return visual_system

def _build_test_chat_system_prompt(
    agent_name: str,
    agent_persona: str,
    personality: AgentPersonality,
) -> str:
    agent_personality = normalize_personality(personality)
    personality_prompt = build_personality_prompt(agent_personality)
    return (
        f'You are "{agent_name}", having a casual one-on-one conversation.\n'
        f"\nYour persona: {agent_persona}"
        f"\n\n{personality_prompt}\n"
        f"\nCONSTRAINTS:\n"
        f"- Stay in character at all times\n"
        f"- Respond in 1-2 short sentences maximum\n"
        f"- Be conversational and natural\n"
        f"- Show your personality through your tone and perspective\n"
        f"- Do not use markdown formatting"
    )


DATA_EVIDENCE_RULES = (

    "\nEVIDENCE RULE: Conversation claims and proposed analyses are not computed evidence. "
    "Do not claim an analysis was performed without a completed backend analysis result. "
    "Do not invent coefficients, significance, confidence intervals, regression, stratification, or causal findings. "
    "Without a backend result for a proposed analysis, discuss questions and next steps only; "
    "do not describe measurements or completed computations. Dataset metadata and provided descriptive "
    "statistics may be described as metadata, not as newly performed analyses. "
    "Never promise results are about to arrive unless a completed backend result exists. "
    "A positive Pearson correlation does not imply causation, benefits of investment, or moderation. "
    "Pearson correlation does not require matching units; positive standardization does not change it. "
    "If a composite-score formula or survey methodology is unavailable, state that limitation once "
    "and continue with available supported analyses; do not promise to contact the data source."

)


def build_analysis_request_prompt(agent: Agent, state: State) -> str:
    """Describe the request contract; computation and validation stay in the backend."""
    return (
        f"You are {agent.name} ({agent.persona_text}). Propose the analysis requested by the human, "
        "current discussion when you have a concrete computation to contribute. "
        'Return one JSON object with exactly two fields: {"message": "your short contribution", "analysis_request": null}. '
        "For a computation, replace analysis_request=null with the requested analysis object. "
        "Use null for ordinary discussion, deferred ideas, or acknowledgement of existing results. "
        "Keep your message within 25 words, reflecting your personality. With an analysis request, "
        "the backend replaces your message with computed facts; do not anticipate results. "
        "Do not compute or invent results. Return JSON only without markdown fences, preserving the requested operation, columns, "
        "grouping, aggregation, and filters even if unsupported; never substitute another analysis. "
        "Omit unused fields. Supported operations and fields:\n"
        "- pearson_correlation / scatter: x_column, y_column (distinct numeric columns), optional group_by.\n"
        "- grouped_comparison: group_by, y_column, aggregation; count may omit y_column to count rows. "
        "For numeric quartiles use grouping=quartiles; otherwise grouping=categories.\n"
        "- table: columns, limit (1-30).\n"
        "- summary: columns, aggregation.\n"
        "Aggregations: mean, median, min, max, sum, count, std. "
        'Optional filters: {"column": value} for equality or {"column": {"operator": "gte", "value": 79}} '
        "for comparisons (eq, gt, gte, lt, lte). "
        'Up to three correlations, grouped comparisons, or summaries may use {"analyses": [spec, ...]}. '
        "Put filters inside each spec, never outside the analyses list. "
        "Discuss identical completed results without requesting them again; set redisplay=true only "
        "when explicitly showing that result again.\n"
        "Available dataset columns: " + json.dumps(state.dataset_columns) +
        "\nDataset context:\n" + state.dataset_summary
    )
