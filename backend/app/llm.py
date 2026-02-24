from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.models import Agent, PublicTurn, State

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 80
TEMPERATURE = 0.85
TIMEOUT_SECONDS = 15.0

MBTI_DESCRIPTIONS = {
    "E": "extraverted, energized by interaction",
    "I": "introverted, energized by reflection",
    "S": "sensing, focused on concrete facts",
    "N": "intuitive, focused on patterns and possibilities",
    "T": "thinking, logic-driven decisions",
    "F": "feeling, values-driven decisions",
    "J": "judging, prefers structure and planning",
    "P": "perceiving, prefers flexibility and openness",
}


def _mbti_line(mbti_type: str | None) -> str:
    if not mbti_type:
        return ""
    traits = [MBTI_DESCRIPTIONS.get(c, "") for c in mbti_type if c in MBTI_DESCRIPTIONS]
    if not traits:
        return ""
    return f"\nYour MBTI type: {mbti_type} ({', '.join(traits)})\n"

_client: Optional[anthropic.AsyncAnthropic] = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY environment variable is not set. "
                "Set it before starting the server."
            )
        _client = anthropic.AsyncAnthropic(
            api_key=api_key,
            timeout=TIMEOUT_SECONDS,
        )
    return _client


ROUND_PROMPTS = {
    1: "DATA ONBOARDING: Introduce the dataset to the team. Describe what this data represents, key columns, data types, and overall scope. Help everyone understand what we're working with.",
    2: "DATA QUALITY & PROCESSING: Identify data quality issues — missing values, suspicious patterns, columns that need cleaning or transformation. Recommend specific preprocessing steps.",
    3: "VISUALIZATION & PATTERNS: Create visualizations to explore the data. Propose and generate charts that reveal distributions, comparisons, and trends. Each agent should create a visual that highlights something meaningful.",
    4: "DEEP EXPLORATION: Use visualizations and cross-column analysis to dig deeper. Explore relationships between variables — how do discounts affect profit? Which regions have more returns? What drives support costs?",
    5: "INSIGHTS & RECOMMENDATIONS: Synthesize findings into actionable insights. What are the key takeaways? What business decisions should this data inform? Summarize the most important discoveries.",
}
DEFAULT_ROUND_PROMPT = "Continue exploring the data, building on all previous findings and refining your analysis with new evidence."


def _build_chair_system_prompt(agent: Agent, topic: str, round_number: int, dataset_context: str = "") -> str:
    base = (
        f'You are "{agent.name}", a mediator in a multi-agent deliberation about: {topic}\n'
        f"\n"
        f"Your persona: {agent.persona_text}\n"
        f"Your traits: {', '.join(agent.quirks)}\n"
        f"Your current stance: {agent.stance}\n"
        f"Your energy level: {agent.energy}/1.0\n"
        f"This is round {round_number} of the discussion.\n"
        f"\n"
        f"YOUR ROLE:\n"
        f"- Open the round by posing a focused question or framing the next angle to explore\n"
        f"- Facilitate fair turn-taking among participants\n"
        f"- Keep the conversation civil and on-track\n"
        f"- Do NOT summarize previous rounds; a separate summary happens at the end\n"
        f"\n"
        f"CONSTRAINTS:\n"
        f"- Respond in 20 words maximum — be brief\n"
        f"- Stay neutral; do not advocate for a specific position\n"
        f"- Address participants by name when referencing their points\n"
        f"- Start your message with a single relevant emoji\n"
        f"- Do not use markdown formatting, bullet points, or numbered lists\n"
        f"- Write in a natural conversational tone as if speaking aloud in a meeting"
    )
    if dataset_context:
        base += f"\n\nDATASET CONTEXT (the team is analyzing this data):\n{dataset_context}\n"
    return base


def _mbti_behavior(mbti_type: str | None) -> str:
    if not mbti_type or len(mbti_type) != 4:
        return ""
    behaviors = []
    if mbti_type[0] == "E":
        behaviors.append("You speak up eagerly, react to others directly, and think out loud")
    else:
        behaviors.append("You pause before responding, choose words carefully, and reflect internally before sharing")
    if mbti_type[1] == "S":
        behaviors.append("You ground arguments in concrete examples, data, and real-world evidence")
    else:
        behaviors.append("You explore abstract possibilities, analogies, and big-picture implications")
    if mbti_type[2] == "T":
        behaviors.append("You prioritize logical consistency and point out flaws in reasoning")
    else:
        behaviors.append("You prioritize how ideas affect people and appeal to shared values")
    if mbti_type[3] == "J":
        behaviors.append("You push for decisions, closure, and clear action items")
    else:
        behaviors.append("You keep options open, explore alternatives, and resist premature conclusions")
    return "\n".join(f"- {b}" for b in behaviors)


def _build_user_system_prompt(agent: Agent, topic: str, round_number: int, dataset_context: str = "") -> str:
    active_quirk = agent.quirks[round_number % 3]
    mbti = _mbti_line(agent.mbti_type)
    mbti_behavior = _mbti_behavior(agent.mbti_type)
    base = (
        f'You are "{agent.name}", a participant in a multi-agent deliberation about: {topic}\n'
        f"\n"
        f"Your persona: {agent.persona_text}\n"
        f"{mbti}"
        f"Your traits: {', '.join(agent.quirks)}\n"
        f"Your current stance: {agent.stance}\n"
        f"Your energy level: {agent.energy}/1.0 (higher = more assertive and action-oriented; "
        f"lower = more cautious and deliberate)\n"
        f"This is round {round_number} of the discussion.\n"
        f"\n"
        f"YOUR COMMUNICATION STYLE (follow these closely):\n"
        f"{mbti_behavior}\n"
        f"\n"
        f"YOUR ROLE:\n"
        f"- Stay true to your communication style above — it defines HOW you speak\n"
        f"- Respond to what others have said; build on, challenge, or refine their ideas\n"
        f"- Your energy level should influence your tone: high energy = decisive and "
        f"action-oriented; low energy = reflective and cautious\n"
        f'- Use your active trait for this round: "{active_quirk}"\n'
        f"\n"
        f"CONSTRAINTS:\n"
        f"- Respond in 25 words maximum — be concise and punchy\n"
        f"- Start your message with a single relevant emoji\n"
        f"- Do not break character or reference the simulation\n"
        f"- Do not use markdown formatting, bullet points, or numbered lists\n"
        f"- End with an invitation for others to respond (a question or challenge)\n"
        f"- Write in a natural conversational tone as if speaking aloud in a meeting"
    )
    if dataset_context:
        base += f"\n\nDATASET CONTEXT (use this data in your analysis):\n{dataset_context}\n"
    return base


def build_system_prompt(agent: Agent, topic: str, round_number: int, dataset_context: str = "") -> str:
    if agent.role == "mediator":
        return _build_chair_system_prompt(agent, topic, round_number, dataset_context)
    return _build_user_system_prompt(agent, topic, round_number, dataset_context)


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
        if turn.speaker_id == "human":
            has_human_input = True

    transcript = "\n".join(lines)

    human_note = ""
    if has_human_input:
        human_note = (
            "\nIMPORTANT: A human participant has contributed to the discussion. "
            "You MUST directly acknowledge and respond to their input. "
            "Address them as 'Human Participant' and engage with their specific points.\n"
        )

    return [
        {
            "role": "user",
            "content": (
                f"Here is the recent conversation:\n\n{transcript}\n\n"
                f"{round_hint}"
                f"{human_note}"
                f"Now respond as {speaker.name}. "
                f"Remember your persona, traits, and constraints."
            ),
        }
    ]


def _fallback_message(agent: Agent, topic: str) -> str:
    if agent.role == "mediator":
        return (
            f"Let's keep the discussion on {topic} focused. "
            f"Who has a concrete next step?"
        )
    return (
        f"I'm thinking about {topic} from my perspective. "
        f"I'd like to hear what others think before committing to a direction."
    )


async def generate_agent_message(
    agent: Agent,
    state: State,
    active_turns: list[PublicTurn],
) -> str:
    try:
        client = get_client()
        system_prompt = build_system_prompt(
            agent, state.topic, state.round_number,
            dataset_context=state.dataset_summary,
        )
        messages = _format_conversation_history(state, active_turns, agent)

        response = await client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            system=system_prompt,
            messages=messages,
        )

        text = response.content[0].text.strip()
        if not text:
            raise ValueError("Empty response from API")
        return text

    except anthropic.APIConnectionError as exc:
        logger.warning("LLM connection error for %s: %s", agent.name, exc)
    except anthropic.RateLimitError as exc:
        logger.warning("LLM rate limit for %s: %s", agent.name, exc)
    except anthropic.APIStatusError as exc:
        logger.warning(
            "LLM API error for %s: status=%s %s", agent.name, exc.status_code, exc
        )
    except Exception as exc:
        logger.warning("Unexpected LLM error for %s: %s", agent.name, exc)

    return _fallback_message(agent, state.topic)


async def generate_chair_summary(
    chair: Agent,
    state: State,
    round_turns: list[PublicTurn],
) -> str:
    agent_names = {a.id: a.name for a in state.agents}
    lines = [f"{agent_names.get(t.speaker_id, 'Unknown')}: {t.message}" for t in round_turns]
    transcript = "\n".join(lines)

    system_prompt = (
        f'You are "{chair.name}", the meeting facilitator.\n'
        f"Topic: {state.topic}\n"
        f"This was round {state.round_number}.\n\n"
        f"YOUR TASK:\n"
        f"Summarize the main themes discussed and suggest next steps moving forward.\n\n"
        f"CONSTRAINTS:\n"
        f"- 20 words maximum — be very brief\n"
        f"- Start your message with a single relevant emoji\n"
        f"- Focus on themes and next steps, not listing who said what\n"
        f"- Do not list participant names\n"
        f"- Do not use generic phrases like 'good discussion' or 'diverse perspectives'\n"
        f"- Do not use markdown formatting\n"
        f"- Write in a natural conversational tone"
    )

    messages = [
        {
            "role": "user",
            "content": (
                f"Here is what was said this round:\n\n{transcript}\n\n"
                f"Now summarize the key themes and next steps in 30 words or fewer."
            ),
        }
    ]

    try:
        client = get_client()
        response = await client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=0.7,
            system=system_prompt,
            messages=messages,
        )
        text = response.content[0].text.strip()
        if text:
            return text
    except Exception as exc:
        logger.warning("Chair summary error: %s", exc)

    return f"Good discussion this round. Let's continue exploring {state.topic}."


VISUAL_MAX_TOKENS = 500

TABLE_ACTION_MAX_TOKENS = 900

VISUAL_ROUND_HINTS = {
    1: "For round 1 (data onboarding), prefer stat_card or table visuals that give an overview of the dataset — column counts, data types, basic statistics.",
    2: "For round 2 (data quality), prefer table or stat_card visuals showing missing values, null counts, or data quality metrics that need attention.",
    3: "For round 3 (visualization), prefer bar_chart or line_chart visuals that reveal distributions, category comparisons, or trends in the data.",
    4: "For round 4 (deep exploration), prefer scatter or heatmap visuals that show relationships between variables — correlations, cross-column analysis.",
    5: "For round 5 (insights), prefer bar_chart or stat_card visuals that summarize key findings and actionable business metrics.",
}

# Agent-specific highlight colors (with alpha for overlay)
AGENT_COLORS = [
    "#38bdf844",  # sky blue
    "#f97316cc",  # orange
    "#a855f744",  # purple
    "#22c55e44",  # green
    "#ef444444",  # red
    "#eab30844",  # yellow
    "#ec489944",  # pink
    "#06b6d444",  # cyan
]


async def generate_visual_spec(
    agent: Agent,
    state: State,
    agent_message: str,
    round_number: int = 0,
) -> dict | None:
    """Generate a visual contribution spec based on the agent's message and role.
    Used as fallback when no dataset columns are available."""
    if not state.dataset_summary:
        return None

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

    try:
        client = get_client()
        response = await client.messages.create(
            model=MODEL,
            max_tokens=VISUAL_MAX_TOKENS,
            temperature=0.7,
            system=visual_system,
            messages=[{"role": "user", "content": "Generate the visual spec now."}],
        )
        import json
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        return json.loads(text)
    except Exception as exc:
        logger.warning("Visual spec generation failed for %s: %s", agent.name, exc)
        return None


async def generate_table_action_and_visual(
    agent: Agent,
    state: State,
    agent_message: str,
    round_number: int = 0,
    column_names: list[str] | None = None,
    row_count: int = 200,
) -> dict:
    """Generate table action (navigate, highlight, annotate) and optional visual in one LLM call."""
    if not column_names:
        return {}

    round_visual_hint = VISUAL_ROUND_HINTS.get(
        round_number, "Choose the most appropriate visual type for the analysis being discussed."
    )
    cols_str = ", ".join(column_names)

    system_prompt = (
        f'You are "{agent.name}" generating table interaction actions.\n'
        f"Your persona: {agent.persona_text}\n"
        f"\nDATASET:\n{state.dataset_summary}\n"
        f"\nYour message this round was: {agent_message}\n"
        f"\nAVAILABLE COLUMNS: {cols_str}\n"
        f"ROW RANGE: 0 to {row_count - 1}\n"
        f"\nGenerate a JSON object with TWO fields:\n"
        f'\n1. "table_action" (REQUIRED): Where you navigate and what you highlight on the data table.\n'
        f'   - "navigate_to": {{"row": <int 0-{row_count - 1}>, "column": "<column name>"}}\n'
        f'     Pick the row and column most relevant to your message.\n'
        f'   - "highlights": array of cell range highlights (0-2 highlights):\n'
        f'     [{{"row_start": <int>, "row_end": <int>, "columns": ["<col1>", "<col2>"]}}]\n'
        f'     Highlight a specific range that supports your point.\n'
        f'   - "annotations": array of cell annotations (0-2 annotations):\n'
        f'     [{{"row": <int>, "column": "<col>", "text": "<max 30 chars>"}}]\n'
        f'     Add a short note on a specific cell.\n'
        f'\n2. "visual" (REQUIRED — always include a chart): A chart to show in your speech bubble.\n'
        f"   ROUND GUIDANCE: {round_visual_hint}\n"
        f"   It MUST have:\n"
        f'   - "visual_type": one of "bar_chart", "line_chart", "scatter", "stat_card"\n'
        f'   - "title": short descriptive title\n'
        f'   - "data": chart data payload matching this format:\n'
        f'     For bar_chart/line_chart: {{"labels": ["A","B","C"], "values": [1,2,3]}}\n'
        f'     For scatter: {{"points": [{{"x":1,"y":2}},{{"x":3,"y":4}}], "x_label":"X", "y_label":"Y"}}\n'
        f'     For stat_card: {{"stats": [{{"label":"Metric","value":"42"}}]}}\n'
        f'   - "description": one sentence\n'
        f"\nRespond with ONLY the JSON object, no markdown, no explanation.\n"
        f"Use ONLY column names from the AVAILABLE COLUMNS list."
    )

    try:
        client = get_client()
        response = await client.messages.create(
            model=MODEL,
            max_tokens=TABLE_ACTION_MAX_TOKENS,
            temperature=0.7,
            system=system_prompt,
            messages=[{"role": "user", "content": "Generate the table action and visual chart now. You MUST include a visual with valid data."}],
        )
        import json
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        return json.loads(text)
    except Exception as exc:
        logger.warning("Table action generation failed for %s: %s", agent.name, exc)
        return {}


def _build_test_chat_system_prompt(
    agent_name: str, agent_persona: str, mbti_type: str,
) -> str:
    mbti = _mbti_line(mbti_type) if mbti_type else ""
    return (
        f'You are "{agent_name}", having a casual one-on-one conversation.\n'
        f"\nYour persona: {agent_persona}"
        f"{mbti}\n"
        f"\nCONSTRAINTS:\n"
        f"- Stay in character at all times\n"
        f"- Respond in 1-2 short sentences maximum\n"
        f"- Be conversational and natural\n"
        f"- Show your personality through your tone and perspective\n"
        f"- Do not use markdown formatting"
    )


async def generate_test_chat_message(
    agent_name: str,
    agent_persona: str,
    mbti_type: str,
    messages: list,
    user_message: str,
) -> str:
    try:
        client = get_client()
        system_prompt = _build_test_chat_system_prompt(agent_name, agent_persona, mbti_type)

        formatted_messages = []
        for msg in messages:
            role = "user" if msg.role == "user" else "assistant"
            formatted_messages.append({"role": role, "content": msg.content})
        formatted_messages.append({"role": "user", "content": user_message})

        response = await client.messages.create(
            model=MODEL,
            max_tokens=100,
            temperature=TEMPERATURE,
            system=system_prompt,
            messages=formatted_messages,
        )

        text = response.content[0].text.strip()
        return text if text else "I'm still gathering my thoughts on that."

    except Exception as exc:
        logger.warning("Test chat error for %s: %s", agent_name, exc)
        return f"Hmm, let me think about that from my perspective as {agent_name}."
