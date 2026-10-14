"""Pure prompt construction. Personality and moderator rules have their own owners."""
from __future__ import annotations

import json

from app.history import format_turn
from app.analysis import evidence_context
from app.models import Agent, ChatMessageInput, PublicTurn, State
from app.moderator import DEFAULT_MODERATOR_STRATEGY_ID, build_moderator_strategy_prompt, get_moderator_strategy
from app.personality import AgentPersonality, build_personality_prompt, normalize_personality


def build_test_chat_messages(messages: list[ChatMessageInput], user_message: str) -> list[dict]:
    return [
        *[{"role": "user" if msg.role == "user" else "assistant", "content": msg.content} for msg in messages],
        {"role": "user", "content": user_message},
    ]

ROUND_PROMPTS = {
    1: "DATA ONBOARDING: Introduce the dataset to the team. Describe what this data represents, key columns, data types, and overall scope. Help everyone understand what we're working with.",
    2: "DATA QUALITY & PROCESSING: Identify data quality issues — missing values, suspicious patterns, columns that need cleaning or transformation. Recommend specific preprocessing steps.",
    3: "VISUALIZATION & PATTERNS: Discuss patterns worth testing. Request a chart when it helps answer a specific question.",
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
        f"- Keep the conversation civil and on-track\n"
        f"- Do NOT summarize previous rounds; a separate summary happens at the end\n"
        f"- Keep the original topic as the main anchor when choosing the next question\n"
        f"- If the discussion has remained within the same conceptual frame for several rounds,\n"
        f"- Step back and reopen a substantively different perspective, disagreement, or framing\n"
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
            f"should directly engage with what the human asked for, applying your unique perspective and expertise to it.\n"
        )

    base = (
        f'You are "{agent.name}", a participant in a multi-agent deliberation about: {topic}\n'
        f"Your persona: {agent.persona_text}\n"
        f"Use the perspective and priorities described in your persona to decide what aspects of the topic you consider most important.\n"
        f"This is round {round_number} of the discussion.\n"
        f"{human_directive}\n"
        f"{personality_prompt}\n\n"
        f"YOUR ROLE:\n"
        f"- Let the agent configuration above guide what you contribute and how you communicate\n"
        f"- Respond to what other participants said; develop, question, or challenge a specific point when relevant\n"
        f"- You may discuss an existing finding or ask a question without requesting a new calculation\n"
        f"\n"
        f"MODERATOR CONTEXT:\n"
        f"- Use the moderator's opening as guidance for the current round.\n"
        f"- Moderator summaries are compressed interpretations, not authoritative group conclusions.\n\n"
        f"\n"
        f"CONSTRAINTS:\n"
        f"- Respond in 25 words maximum — be concise and punchy\n"
        f"- Do not break character or reference the simulation\n"
        f"- Do not use markdown formatting, bullet points, or numbered lists\n"
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

    lines = []
    has_human_input = False
    for turn in all_context_turns:
        lines.append(format_turn(state, turn))
        if turn.speaker_id == "human":
            has_human_input = True

    transcript = "\n".join(lines)
    if state.dataset_summary:
        evidence = evidence_context(state.public_history + active_turns)
        if evidence:
            transcript += "\nVerified backend findings (separate from participant claims):\n" + evidence

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
    lines = [format_turn(state, turn) for turn in round_turns]
    if state.dataset_summary:
        evidence = evidence_context(state.public_history + round_turns, limit=12)
        if evidence:
            lines.append("Verified backend findings (check variables, filters and groups before comparing):\n" + evidence)
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
        f"Distinguish what participants said, where genuine agreement exists, and what remains unresolved. "
        f"The moderator opening is framing, not evidence of participant agreement.\n\n"
        f"CONSTRAINTS:\n"
        f"- 20 words maximum — be concise\n"
        f"- Do not list participant names\n"
        f"- Do not use generic phrases like 'good discussion' or 'diverse perspectives'\n"
        f"- Do not use markdown formatting\n"
        f"- Write in a natural conversational tone"
    )

    if state.dataset_summary:
        system_prompt += (
            "\nOnly completed backend analysis results are evidence of performed analyses. "
            "Participant interpretations and earlier moderator statements are claims, not verification. "
            "Describe an unsupported hypothesis as a question or attribute it to participants; "
            "never present it as an established finding. Summarize qualitatively without numbers; "
            "each analysis contribution already reports its backend measurements. "
            "Keep subgroup findings distinct from the overall result and from other subgroups. "
            "Compare coefficients only when both results use the same variables and compatible filters. "
            "Correlations show association, not causes, effects, predictors or intervention benefits. "
            "Do not claim one group leads another unless a completed result directly supports it. "
            "Do not treat failed analyses as findings. If requests failed, use the recorded "
            "backend error; do not guess that column names or data values were wrong. "
            "If no result exists, summarize proposed "
            "next steps rather than findings."
        )

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
    "When citing a previous numeric result, copy it from the verified backend findings with its scope and sample size; "
    "do not calculate a new figure or infer a cause from a correlation. "
    "Treat participant and moderator interpretations as hypotheses until the backend result supports them. "
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
    """Let an agent discuss naturally and optionally request one backend computation."""
    return (
        f"You are {agent.name} ({agent.persona_text}). Continue the conversation from your "
        "own priorities and respond to what others have said. "
        'Return one JSON object with exactly two fields: {"message": "your short contribution", "analysis_request": null}. '
        "Free discussion is a complete contribution. Request one computation only when it "
        "directly advances the current question and the same result is not already available. "
        "For a computation, replace analysis_request=null with one requested analysis object. "
        'For example: {"message":"Compare internet access by region",'
        '"analysis_request":{"operation":"grouped_comparison","group_by":"Region_Type",'
        '"y_column":"Internet_Access_pct","aggregation":"mean"}}. '
        'Put operation inside analysis_request as a field; do not nest fields under an operation-name key. '
        "Use null for ordinary discussion, deferred ideas, or acknowledgement of existing results. "
        "Respond to, challenge, or develop a previous participant's point when relevant. "
        "Keep your message within 25 words and make your persona's priorities recognizable. "
        "The message is the contribution shown in the conversation. If requesting an analysis, "
        "use it to explain the question, motivation, concern, or decision it informs. "
        "Do not state a numeric result of the requested analysis before it runs. "
        "Do not compute or invent results. Return JSON only without markdown fences, preserving the requested operation, columns, "
        "grouping, aggregation, and filters even if unsupported; never substitute another analysis. "
        "Omit unused fields. Supported operations and fields:\n"
        "- pearson_correlation / scatter: x_column, y_column (distinct numeric columns), optional group_by.\n"
        "- grouped_comparison: group_by, y_column, aggregation; count may omit y_column to count rows. "
        "For numeric quartiles use grouping=quartiles; otherwise grouping=categories.\n"
        "- table: columns, limit (1-30).\n"
        "- summary: columns, aggregation.\n"
        "- dataset_overview: optional columns for row count, types and missing values.\n"
        "Aggregations: mean, median, min, max, sum, count, std. "
        'Optional filters: {"column": value} for equality or {"column": {"operator": "gte", "value": 79}} '
        "for comparisons (eq, gt, gte, lt, lte). "
        "Discuss identical completed results without requesting them again; set redisplay=true only "
        "when explicitly showing that result again.\n"
        "Available dataset columns: " + json.dumps(state.dataset_columns) +
        "\nDataset context:\n" + state.dataset_summary
    )
