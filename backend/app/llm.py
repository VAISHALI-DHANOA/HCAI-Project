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
MAX_TOKENS = 100
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


def _build_chair_system_prompt(agent: Agent, topic: str, round_number: int) -> str:
    return (
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
        f"- Respond in 18 words maximum\n"
        f"- Stay neutral; do not advocate for a specific position\n"
        f"- Address participants by name when referencing their points\n"
        f"- Start your message with a single relevant emoji\n"
        f"- Do not use markdown formatting, bullet points, or numbered lists\n"
        f"- Write in a natural conversational tone as if speaking aloud in a meeting"
    )


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


def _build_user_system_prompt(agent: Agent, topic: str, round_number: int) -> str:
    active_quirk = agent.quirks[round_number % 3]
    mbti = _mbti_line(agent.mbti_type)
    mbti_behavior = _mbti_behavior(agent.mbti_type)
    return (
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
        f"- Respond in 18 words maximum\n"
        f"- Start your message with a single relevant emoji\n"
        f"- Do not break character or reference the simulation\n"
        f"- Do not use markdown formatting, bullet points, or numbered lists\n"
        f"- End with an invitation for others to respond (a question or challenge)\n"
        f"- Write in a natural conversational tone as if speaking aloud in a meeting"
    )


def build_system_prompt(agent: Agent, topic: str, round_number: int) -> str:
    if agent.role == "mediator":
        return _build_chair_system_prompt(agent, topic, round_number)
    return _build_user_system_prompt(agent, topic, round_number)


def _format_conversation_history(
    state: State,
    active_turns: list[PublicTurn],
    speaker: Agent,
) -> list[dict]:
    recent_history = state.public_history[-12:]
    all_context_turns = recent_history + active_turns

    if not all_context_turns:
        return [
            {
                "role": "user",
                "content": (
                    f'You are starting the discussion on the topic: "{state.topic}"\n'
                    f"No one has spoken yet. Please open the conversation."
                ),
            }
        ]

    agent_names = {a.id: a.name for a in state.agents}
    lines = []
    for turn in all_context_turns:
        name = agent_names.get(turn.speaker_id, "Unknown")
        lines.append(f"{name}: {turn.message}")

    transcript = "\n".join(lines)

    return [
        {
            "role": "user",
            "content": (
                f"Here is the recent conversation:\n\n{transcript}\n\n"
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
        system_prompt = build_system_prompt(agent, state.topic, state.round_number)
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
        f"- 18 words maximum\n"
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
                f"Now summarize the key themes and next steps in 18 words or fewer."
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
