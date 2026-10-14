from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from app.config import CHAT_SETTINGS, DATA_CONTRIBUTION_SETTINGS, DISCUSSION_SETTINGS, SUMMARY_SETTINGS, GenerationSettings
from app.models import Agent, ChatMessageInput, DataContributionRequest, GenerationMetadata, PublicTurn, State
from app.personality import AgentPersonality
from app.prompts import (
    _build_test_chat_system_prompt, _format_conversation_history,
    DATA_EVIDENCE_RULES, build_analysis_request_prompt, build_chair_summary_prompt, build_system_prompt, build_test_chat_messages,
)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeneratedMessage:
    text: str
    generation: GenerationMetadata
    analysis_request: dict | None = None


def _extract_json(text: str) -> dict | list | None:
    """Robustly extract a JSON object from LLM output.

    Handles markdown fences, leading prose, and trailing text.
    """
    text = text.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try to find a JSON object in the text
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set. Set it before starting the server.")
        _client = anthropic.AsyncAnthropic(
            api_key=api_key, timeout=DISCUSSION_SETTINGS.timeout_seconds,
        )
    return _client


async def _generate_text(
    *, system_prompt: str, messages: list[dict], settings: GenerationSettings,
    operation: str, fallback: str, empty_fallback: str | None = None,
) -> GeneratedMessage:
    try:
        response = await get_client().messages.create(
            model=settings.model,
            max_tokens=settings.max_tokens,
            temperature=settings.temperature,
            timeout=settings.timeout_seconds,
            system=system_prompt,
            messages=messages,
        )
        text = response.content[0].text.strip()
        if text:
            return GeneratedMessage(text, GenerationMetadata(
                source="llm", operation=operation, **settings.to_dict(),
            ))
        error_type = "EmptyResponse"
        fallback = empty_fallback if empty_fallback is not None else fallback
        logger.warning("%s generation returned an empty response", operation)
    except Exception as exc:
        error_type = type(exc).__name__
        logger.warning("%s generation failed (%s): %s", operation, error_type, exc)
    return GeneratedMessage(fallback, GenerationMetadata(
        source="fallback", operation=operation, error_type=error_type, **settings.to_dict(),
    ))


def _fallback_message(agent: Agent, topic: str) -> str:
    if agent.role == "mediator":
        return (
            f"Let's keep the discussion on {topic} focused. "
            f"Which perspective or concern should the group examine further?"
        )
    return (
        f"I'm thinking about {topic} from my perspective. "
        f"I'd like to hear what others think before committing to a direction."
    )


async def generate_agent_message(
    agent: Agent, state: State, active_turns: list[PublicTurn],
) -> GeneratedMessage:
    system_prompt = build_system_prompt(
        agent, state.topic, state.round_number,
        dataset_context=state.dataset_summary,
        human_request=state.human_request,
        moderator_strategy_id=state.moderator_strategy_id,
    )
    if state.dataset_summary:
        system_prompt += DATA_EVIDENCE_RULES
    return await _generate_text(
        system_prompt=system_prompt,
        messages=_format_conversation_history(state, active_turns, agent),
        settings=DISCUSSION_SETTINGS,
        operation="discussion",
        fallback=_fallback_message(agent, state.topic),
    )


async def generate_data_contribution(agent: Agent, state: State, active_turns: list[PublicTurn]) -> GeneratedMessage:
    """Generate a conversational contribution with at most one optional computation."""
    prompt = build_system_prompt(
        agent, state.topic, state.round_number, human_request=state.human_request,
        moderator_strategy_id=state.moderator_strategy_id,
    ) + DATA_EVIDENCE_RULES + "\n" + build_analysis_request_prompt(agent, state)
    settings = DATA_CONTRIBUTION_SETTINGS
    try:
        response = await get_client().messages.create(
            model=settings.model, max_tokens=settings.max_tokens,
            temperature=settings.temperature, timeout=settings.timeout_seconds, system=prompt,
            messages=_format_conversation_history(state, active_turns, agent),
        )
        text = response.content[0].text.strip()
        if not text:
            error_type = "EmptyResponse"
        else:
            payload = _extract_json(text)
            if payload is None:
                raise json.JSONDecodeError("No valid JSON contribution found", text, 0)
            contribution = DataContributionRequest.model_validate(payload)
            if not contribution.message.strip():
                raise ValueError("Empty contribution")
            return GeneratedMessage(contribution.message.strip(), GenerationMetadata(
                source="llm", operation="discussion", **settings.to_dict(),
            ), contribution.analysis_request)

    except Exception as exc:
        error_type = type(exc).__name__
    logger.warning("Data contribution failed for %s (%s)", agent.name, error_type)
    return GeneratedMessage(_fallback_message(agent, state.topic), GenerationMetadata(
        source="fallback", operation="discussion", error_type=error_type, **settings.to_dict(),
    ))


async def generate_chair_summary(
    chair: Agent, state: State, round_turns: list[PublicTurn],
) -> GeneratedMessage:
    system_prompt, messages = build_chair_summary_prompt(chair, state, round_turns)
    return await _generate_text(
        system_prompt=system_prompt, messages=messages,
        settings=SUMMARY_SETTINGS, operation="summary",
        fallback=f"Good discussion this round. Let's continue exploring {state.topic}.",
    )


async def generate_test_chat_message(
    agent_name: str, agent_persona: str, personality: AgentPersonality,
    messages: list[ChatMessageInput], user_message: str,
) -> GeneratedMessage:
    return await _generate_text(
        system_prompt=_build_test_chat_system_prompt(agent_name, agent_persona, personality),
        messages=build_test_chat_messages(messages, user_message),
        settings=CHAT_SETTINGS, operation="chat",
        fallback=f"Hmm, let me think about that from my perspective as {agent_name}.",
        empty_fallback="I'm still gathering my thoughts on that.",
    )
