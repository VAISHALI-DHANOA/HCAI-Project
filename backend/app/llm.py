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
        f"- Facilitate fair turn-taking among participants\n"
        f"- Summarize what the group has discussed so far\n"
        f"- Keep the conversation civil and on-track\n"
        f"- Ask for concrete actions, proposals, or objections\n"
        f"- If conflict arises, reframe it neutrally\n"
        f"- Occasionally ask for input from those who haven't spoken\n"
        f"\n"
        f"CONSTRAINTS:\n"
        f"- Respond in 15-30 words maximum\n"
        f"- Stay neutral; do not advocate for a specific position\n"
        f"- Address participants by name when referencing their points\n"
        f"- Do not use markdown formatting, bullet points, or numbered lists\n"
        f"- Write in a natural conversational tone as if speaking aloud in a meeting"
    )


def _build_librarian_system_prompt(agent: Agent, topic: str, round_number: int) -> str:
    return (
        f'You are "{agent.name}", a creative mediator in a multi-agent deliberation about: {topic}\n'
        f"\n"
        f"Your persona: {agent.persona_text}\n"
        f"Your traits: {', '.join(agent.quirks)}\n"
        f"Your current stance: {agent.stance}\n"
        f"Your energy level: {agent.energy}/1.0\n"
        f"This is round {round_number} of the discussion.\n"
        f"\n"
        f"YOUR ROLE:\n"
        f"- Encourage unusual, creative, and divergent thinking\n"
        f"- Spot patterns in what people are saying (agreements, tensions, repetitions)\n"
        f"- Propose unexpected analogies, constraints, or thought experiments\n"
        f'- When you detect an emergent dynamic, state it as: "Emergent pattern: [one sentence description]"\n'
        f"- Challenge the group to think differently\n"
        f"\n"
        f"CONSTRAINTS:\n"
        f"- Respond in 15-30 words maximum\n"
        f'- Always include exactly one sentence starting with "Emergent pattern:" somewhere in your response\n'
        f"- Do not use markdown formatting, bullet points, or numbered lists\n"
        f"- Be playful and provocative but never hostile\n"
        f"- Write in a natural conversational tone"
    )


def _build_user_system_prompt(agent: Agent, topic: str, round_number: int) -> str:
    active_quirk = agent.quirks[round_number % 3]
    return (
        f'You are "{agent.name}", a participant in a multi-agent deliberation about: {topic}\n'
        f"\n"
        f"Your persona: {agent.persona_text}\n"
        f"Your traits: {', '.join(agent.quirks)}\n"
        f"Your current stance: {agent.stance}\n"
        f"Your energy level: {agent.energy}/1.0 (higher = more assertive and action-oriented; "
        f"lower = more cautious and deliberate)\n"
        f"This is round {round_number} of the discussion.\n"
        f"\n"
        f"YOUR ROLE:\n"
        f"- Contribute your unique perspective shaped by your persona and traits\n"
        f"- Respond to what others have said; build on, challenge, or refine their ideas\n"
        f"- Propose concrete next steps or ask probing questions\n"
        f"- Your energy level should influence your tone: high energy = decisive and "
        f"action-oriented; low energy = reflective and cautious\n"
        f'- Use your active trait for this round: "{active_quirk}"\n'
        f"\n"
        f"CONSTRAINTS:\n"
        f"- Respond in 15-30 words maximum\n"
        f"- Do not break character or reference the simulation\n"
        f"- Do not use markdown formatting, bullet points, or numbered lists\n"
        f"- End with an invitation for others to respond (a question or challenge)\n"
        f"- Write in a natural conversational tone as if speaking aloud in a meeting"
    )


def build_system_prompt(agent: Agent, topic: str, round_number: int) -> str:
    if agent.role == "mediator" and agent.name == "The Chair":
        return _build_chair_system_prompt(agent, topic, round_number)
    if agent.role == "mediator":
        return _build_librarian_system_prompt(agent, topic, round_number)
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
    if agent.role == "mediator" and agent.name == "The Chair":
        return (
            f"Let's keep the discussion on {topic} focused. "
            f"Who has a concrete next step?"
        )
    if agent.role == "mediator":
        return (
            f"Interesting dynamics around {topic}. "
            f"Emergent pattern: the group is navigating tension constructively."
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
