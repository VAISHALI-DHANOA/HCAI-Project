"""Final thesis metrics: profile stability, lexical convergence, and consensus."""
from __future__ import annotations

import json
import logging
import re
from itertools import combinations
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.analysis import analysis_headline, analysis_report
from app.config import THESIS_METRICS_SETTINGS
from app.llm import get_client
from app.models import Agent, PublicTurn, State
from app.personality import OCEAN_TRAITS, TRAIT_BEHAVIOR_MAP

logger = logging.getLogger(__name__)

THESIS_METRICS_VERSION = "thesis-metrics-v1"

PERSONALITY_STABILITY_JUDGE_INSTRUCTIONS = (
    "You evaluate Personality Stability in a multi-agent discussion.\n"
    "\n"
    "YOUR TASK:\n"
    "- Judge how consistently each agent's observed behavior matches its complete configured profile\n"
    "- Consider persona text, functional role, OCEAN tendencies, and custom instructions when present\n"
    "- Evaluate each agent only from its own supplied contributions\n"
    "- Use only the profile information provided; do not invent additional personality expectations\n"
    "\n"
    "EVIDENCE RULES:\n"
    "- Opinion or conclusion changes are not automatically personality inconsistency\n"
    "- If the profile explicitly specifies a stable stance, belief, priority, or commitment, contradicting it is evidence of inconsistency\n"
    "- Distinguish reasonable belief updates from abandoning an explicitly configured profile characteristic\n"
    "- Do not require every profile tendency to appear\n"
    "- Absence of observable evidence is not inconsistency\n"
    "SCORE:\n"
    "- 0 = strongly inconsistent\n"
    "- 1 = mostly inconsistent\n"
    "- 2 = mixed, with both consistent behavior and meaningful profile tension\n"
    "- 3 = very good: clearly consistent with the configured profile\n"
    "- 4 = exceptional: unusually distinctive and repeatedly profile-typical\n"
    "\n"
    "SCORE 4 REQUIREMENTS:\n"
    "- Require multiple distinctive and repeated behavioral patterns\n"
    "- Evidence should reflect the persona or functional role plus at least two diagnostic OCEAN tendencies\n"
    "- The behavior should distinguish this profile from plausible contrasting profiles\n"
    "- Score 4 requires contributions from at least two different rounds\n"
    "- A strong profile match normally merits 3; reserve 4 for exceptional evidence\n"
    "\n"
    "OUTPUT:\n"
    "- Return exactly one result for every supplied agent_id, in the same order\n"
    "- Return agent_id, status, score, and a brief reason for each agent\n"
    "- Keep each reason within 12 words; describe one observed behavior\n"
    "- For insufficient evidence use status=\"insufficient_evidence\" and score=null\n"
    "- Do not return unavailable or error\n"
    "- Submit results using the required record_personality_stability tool"
)

PERSONALITY_STABILITY_TOOL_NAME = "record_personality_stability"

CONSENSUS_JUDGE_INSTRUCTIONS = (
    "You evaluate substantive consensus in a multi-agent discussion.\n"
    "\n"
    "YOUR TASK:\n"
    "- Judge the level of substantive agreement between participant contributions in the current round\n"
    "- Use the original discussion problem as context\n"
    "- Look for shared relevant claims, conclusions, recommendations, or answers\n"
    "\n"
    "CONSENSUS RULES:\n"
    "- Shared terminology, framing, or background facts alone are not broad consensus\n"
    "- Explicit disagreement about the same claim is not consensus, even when wording is similar\n"
    "- Distinguish genuine agreement from superficial similarity\n"
    "- Use insufficient_evidence with score=null only when the supplied contributions cannot support a reliable judgment\n"
    "\n"
    "SCORE:\n"
    "- 0 = no substantive shared conclusion\n"
    "- 1 = limited consensus: some local agreement, but substantial disagreement on the main conclusion\n"
    "- 2 = partial consensus: agreement on one or more important conclusions, with meaningful disagreement remaining\n"
    "- 3 = broad consensus: participants largely support the same main substantive conclusion, with only minor disagreement\n"
    "\n"
    "OUTPUT:\n"
    "- Return exactly one result\n"
    "- Keep reason, shared_conclusion, and unresolved_disagreement to 20 words maximum each\n"
    "- Use null when no shared conclusion can be identified\n"
    "- Use null when no unresolved disagreement remains\n"
    "- For insufficient evidence use status=\"insufficient_evidence\" and score=null\n"
    "- Do not return unavailable or error\n"
    "- Submit the result using the required record_consensus tool"
)
CONSENSUS_TOOL_NAME = "record_consensus"
LEXICAL_CONVERGENCE_VERSION = "jaccard-lexical-overlap-v1"


class PersonalityStabilityJudgeResult(BaseModel):
    """Structured output required from the judge for one participant."""

    model_config = ConfigDict(extra="forbid")
    agent_id: str
    status: Literal["available", "insufficient_evidence"]
    score: int | None = Field(default=None, ge=0, le=4)
    # Treat the word limit as guidance: verbose reasons must not invalidate scores.
    reason: str

    @model_validator(mode="after")
    def score_matches_status(self):
        if self.status == "available" and self.score is None:
            raise ValueError("available results require a score")
        if self.status == "insufficient_evidence" and self.score is not None:
            raise ValueError("insufficient_evidence results require score=null")
        return self


class PersonalityStabilityJudgeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    results: list[PersonalityStabilityJudgeResult]


class ConsensusJudgeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["available", "insufficient_evidence"]
    score: int | None = Field(default=None, ge=0, le=3)
    # The prompt and fixed output budget keep these concise. Do not invalidate an
    # otherwise valid score solely because the provider exceeds a display-text hint.
    shared_conclusion: str | None = None
    unresolved_disagreement: str | None = None
    reason: str

    @model_validator(mode="after")
    def score_matches_status(self):
        if self.status == "available" and self.score is None:
            raise ValueError("available results require a score")
        if self.status == "insufficient_evidence" and self.score is not None:
            raise ValueError("insufficient_evidence results require score=null")
        return self


def _profile(agent: Agent) -> dict | None:
    profile: dict = {}
    if agent.persona_text.strip():
        profile["persona_text"] = agent.persona_text.strip()
    if agent.personality is not None:
        personality = agent.personality
        trait_values = personality.ocean.model_dump()
        profile["ocean"] = {
            trait: {
                "level": trait_values[trait],
                "behavioral_expression_instructions": TRAIT_BEHAVIOR_MAP[trait][trait_values[trait]],
            }
            for trait in OCEAN_TRAITS
        }
        if personality.role_goal.strip():
            profile["functional_role_goal"] = personality.role_goal.strip()
        if personality.custom_instructions.strip():
            profile["custom_instructions"] = personality.custom_instructions.strip()
    return profile or None


def _valid_contributions(agent_id: str, history: list[PublicTurn], round_number: int) -> list[dict]:
    return [
        {"round_number": turn.round_number, "message": _agent_authored_message(turn)}
        for turn in history
        if turn.round_number <= round_number
        and turn.speaker_id == agent_id
        and turn.turn_type == "participant"
        and _agent_authored_message(turn)
        and not (turn.generation and turn.generation.source == "fallback")
    ]


def _agent_authored_message(turn: PublicTurn) -> str:
    """Exclude deterministic backend analysis text from personality evidence."""
    results = [item for item in [turn.analysis, *turn.additional_analyses] if item is not None]
    if not results:
        return turn.message.strip()
    completed = [item for item in results if item.status == "completed"]
    failed = [item for item in results if item.status != "completed"]
    suffix_parts = [analysis_headline(item) for item in completed]
    if failed:
        suffix_parts.append(" ".join(analysis_report(item) for item in failed))
    suffix = " ".join(suffix_parts)
    if suffix and turn.message.endswith(" " + suffix):
        return turn.message[:-(len(suffix) + 1)].strip()
    return turn.message.strip()


def _current_round_contributions(state: State) -> list[dict]:
    participant_ids = {agent.id for agent in state.agents if agent.role == "user"}
    grouped: dict[str, list[str]] = {}
    for turn in state.public_history:
        if (turn.round_number == state.round_number
                and turn.speaker_id in participant_ids
                and turn.turn_type == "participant"
                and turn.message.strip()
                and not (turn.generation and turn.generation.source == "fallback")):
            grouped.setdefault(turn.speaker_id, []).append(turn.message.strip())
    return [
        {"agent_id": agent.id, "message": "\n".join(grouped[agent.id])}
        for agent in state.agents
        if agent.role == "user" and agent.id in grouped
    ]


def _error_result(agent_id: str, status: Literal["unavailable", "error"], reason: str) -> dict:
    return {"agent_id": agent_id, "status": status, "score": None, "reason": reason}


def _insufficient_evidence_result(agent_id: str) -> dict:
    return {
        "agent_id": agent_id,
        "status": "insufficient_evidence",
        "score": None,
        "reason": "No valid observable participant contributions.",
    }


def _round_summary(results: list[dict]) -> dict:
    scores = [item["score"] for item in results if item["status"] == "available"]
    return {
        "per_agent": results,
        "mean_score": round(sum(scores) / len(scores), 3) if scores else None,
        "evaluated_agent_count": len(scores),
        "insufficient_evidence_agent_count": sum(
            item["status"] == "insufficient_evidence" for item in results
        ),
    }


def _run_summary(state: State, current_results: list[dict]) -> dict:
    participant_ids = [agent.id for agent in state.agents if agent.role == "user"]
    by_agent: dict[str, list[int]] = {agent_id: [] for agent_id in participant_ids}
    all_scores: list[int] = []
    rounds = [r.thesis_metrics.get("personality_stability", {}).get("round", {}) for r in state.rounds]
    for round_data in [*rounds, {"per_agent": current_results}]:
        for item in round_data.get("per_agent", []):
            if item.get("status") == "available" and item.get("score") is not None:
                by_agent.setdefault(item["agent_id"], []).append(item["score"])
                all_scores.append(item["score"])
    return {
        "per_agent_mean": {
            agent_id: (round(sum(scores) / len(scores), 3) if scores else None)
            for agent_id, scores in by_agent.items()
        },
        "overall_mean": round(sum(all_scores) / len(all_scores), 3) if all_scores else None,
        "available_score_count": len(all_scores),
    }


def _payload(
    state: State,
    results: list[dict],
    *,
    failure: dict | None = None,
    one_call_per_round: bool = True,
) -> dict:
    judge = THESIS_METRICS_SETTINGS.to_dict()
    return {
        "version": THESIS_METRICS_VERSION,
        "evaluation": {
            "judge": judge,
            "one_call_per_round": one_call_per_round,
            "failure": failure,
        },
        "personality_stability": {
            "evaluation": {"judge": judge, "failure": failure},
            "round": _round_summary(results),
            "run": _run_summary(state, results),
        },
    }


def personality_stability_error_payload(state: State) -> dict:
    """Last-resort payload used by the round runner if evaluation itself raises."""
    results = [
        _error_result(agent.id, "error", "Judge evaluation failed.")
        for agent in state.agents if agent.role == "user"
    ]
    return _payload(
        state,
        results,
        failure={"category": "provider_or_runtime_error", "detail": "Unhandled evaluation error."},
    )


def _metric_failure(category: str, detail: str) -> dict:
    return {"category": category, "detail": detail}


async def _structured_judge_call(
    *, instructions: str, tool_name: str, output_model: type[BaseModel], message: str,
    normalize: Callable[[object], object] | None = None,
) -> BaseModel:
    response = await get_client().messages.create(
        model=THESIS_METRICS_SETTINGS.model,
        max_tokens=THESIS_METRICS_SETTINGS.max_tokens,
        temperature=THESIS_METRICS_SETTINGS.temperature,
        timeout=THESIS_METRICS_SETTINGS.timeout_seconds,
        system=instructions,
        messages=[{"role": "user", "content": message}],
        tools=[{
            "name": tool_name,
            "description": f"Record the structured {tool_name} result.",
            "input_schema": output_model.model_json_schema(),
        }],
        tool_choice={"type": "tool", "name": tool_name},
    )
    tool_block = next((
        block for block in response.content
        if getattr(block, "type", None) == "tool_use"
        and getattr(block, "name", None) == tool_name
    ), None)
    if getattr(response, "stop_reason", None) == "max_tokens":
        raise JudgeOutputTruncatedError("Judge output exceeded max_tokens")
    if tool_block is None:
        raise json.JSONDecodeError("Judge returned no structured tool output", "", 0)
    parsed = tool_block.input
    if isinstance(parsed, str):
        parsed = json.loads(parsed)
    if normalize is not None:
        parsed = normalize(parsed)
    return output_model.model_validate(parsed)


_JUDGE_XML_RESIDUE = re.compile(
    r"</?(?:invoke|tool[_-]?call|(?:an|un)?resolved_disagreement|shared_conclusion|reason)\b[^>]*>",
    flags=re.IGNORECASE,
)


def _sanitize_consensus_output(parsed: object) -> object:
    """Remove known provider/tool residue without supplying missing judge content."""
    if not isinstance(parsed, dict):
        return parsed
    cleaned = dict(parsed)
    for field in ("shared_conclusion", "unresolved_disagreement", "reason"):
        value = cleaned.get(field)
        if isinstance(value, str):
            cleaned[field] = _JUDGE_XML_RESIDUE.sub("", value).strip()
    return cleaned


def _normalize_personality_output(parsed: object) -> object:
    """Accept equivalent list wrappers sometimes emitted by structured-output providers."""
    if isinstance(parsed, list):
        return {"results": parsed}
    if not isinstance(parsed, dict) or "results" in parsed:
        return parsed
    for alias in ("evaluations", "agent_results", "per_agent"):
        candidate = parsed.get(alias)
        if isinstance(candidate, list):
            return {"results": candidate}
    if {"agent_id", "status", "reason"}.issubset(parsed):
        return {"results": [parsed]}
    return parsed


def _judge_cases_message(cases: list[dict]) -> str:
    return "CASES:\n" + json.dumps(cases, ensure_ascii=False, separators=(",", ":"))


def _validation_failure_reason(exc: ValidationError) -> str:
    first = exc.errors(include_url=False)[0]
    location = ".".join(str(part) for part in first.get("loc", ())) or "output"
    return f"Judge output invalid ({location}: {first['type']})."


class JudgeAgentIdError(ValueError):
    pass


class JudgeOutputTruncatedError(ValueError):
    pass


async def _judge_personality_cases(
    cases: list[dict],
) -> tuple[list[PersonalityStabilityJudgeResult], bool]:
    try:
        judged = (await _structured_judge_call(
            instructions=PERSONALITY_STABILITY_JUDGE_INSTRUCTIONS,
            tool_name=PERSONALITY_STABILITY_TOOL_NAME,
            output_model=PersonalityStabilityJudgeOutput,
            message=_judge_cases_message(cases),
            normalize=_normalize_personality_output,
        )).results
        return judged, False
    except JudgeOutputTruncatedError:
        if len(cases) == 1:
            raise
        midpoint = len(cases) // 2
        left, _ = await _judge_personality_cases(cases[:midpoint])
        right, _ = await _judge_personality_cases(cases[midpoint:])
        return [*left, *right], True


def _failure_results(cases: list[dict], reason: str) -> dict[str, dict]:
    return {
        case["agent_id"]: _error_result(case["agent_id"], "error", reason)
        for case in cases
    }


async def evaluate_personality_stability(state: State) -> dict:
    participants = [agent for agent in state.agents if agent.role == "user"]
    local_results: dict[str, dict] = {}
    cases: list[dict] = []
    for agent in participants:
        profile = _profile(agent)
        if profile is None:
            local_results[agent.id] = _error_result(
                agent.id, "unavailable", "Required profile information unavailable."
            )
            continue
        contributions = _valid_contributions(
            agent.id, state.public_history, state.round_number
        )
        if not contributions:
            local_results[agent.id] = _insufficient_evidence_result(agent.id)
            continue
        cases.append({
            "agent_id": agent.id,
            "profile": profile,
            "contributions": contributions,
        })

    if not cases:
        return _payload(state, [local_results[agent.id] for agent in participants])

    failure = None
    retried_in_batches = False
    try:
        judged, retried_in_batches = await _judge_personality_cases(cases)
        expected_ids = {case["agent_id"] for case in cases}
        received_ids = [item.agent_id for item in judged]
        if len(received_ids) != len(set(received_ids)) or set(received_ids) != expected_ids:
            raise JudgeAgentIdError("Judge result agent IDs did not match requested participants")
        contribution_rounds = {
            case["agent_id"]: {entry["round_number"] for entry in case["contributions"]}
            for case in cases
        }
        by_id = {}
        for item in judged:
            value = item.model_dump()
            if item.score == 4 and len(contribution_rounds[item.agent_id]) < 2:
                value["score"] = 3
            value["reason"] = " ".join(item.reason.split())[:240]
            by_id[item.agent_id] = value
        results = [local_results.get(agent.id) or by_id[agent.id] for agent in participants]
    except json.JSONDecodeError as exc:
        logger.warning("Personality Stability judge JSON parsing failed: %s", exc)
        errors = _failure_results(cases, "Judge output could not be parsed as JSON.")
        failure = {"category": "json_parsing_failure", "detail": str(exc)}
        results = [local_results.get(agent.id) or errors[agent.id] for agent in participants]
    except ValidationError as exc:
        logger.warning("Personality Stability judge output failed validation: %s", exc)
        reason = _validation_failure_reason(exc)
        errors = _failure_results(cases, reason)
        failure = {"category": "schema_validation_failure", "detail": reason}
        results = [local_results.get(agent.id) or errors[agent.id] for agent in participants]
    except JudgeAgentIdError as exc:
        logger.warning("Personality Stability judge agent IDs invalid: %s", exc)
        errors = _failure_results(cases, "Judge returned missing, duplicate, or unexpected agent IDs.")
        failure = {"category": "agent_id_mismatch", "detail": str(exc)}
        results = [local_results.get(agent.id) or errors[agent.id] for agent in participants]
    except JudgeOutputTruncatedError as exc:
        logger.warning("Personality Stability judge output truncated: %s", exc)
        errors = _failure_results(cases, "Judge output exceeded its token budget.")
        failure = _metric_failure("output_truncated", str(exc))
        results = [local_results.get(agent.id) or errors[agent.id] for agent in participants]
    except Exception as exc:
        error_type = type(exc).__name__
        logger.warning("Personality Stability evaluation failed (%s): %s", error_type, exc)
        errors = _failure_results(cases, f"Judge provider/runtime error ({error_type}).")
        failure = {"category": "provider_or_runtime_error", "detail": error_type}
        results = [local_results.get(agent.id) or errors[agent.id] for agent in participants]
    return _payload(
        state,
        results,
        failure=failure,
        one_call_per_round=not retried_in_batches,
    )


def _consensus_unavailable(status: str, reason: str) -> dict:
    return {
        "status": status,
        "score": None,
        "shared_conclusion": None,
        "unresolved_disagreement": None,
        "reason": reason,
    }


def _consensus_run_summary(state: State, current_round: dict) -> dict:
    available = []
    for prior in state.rounds:
        value = prior.thesis_metrics.get("consensus", {}).get("round", {})
        if value.get("status") == "available" and value.get("score") is not None:
            available.append(value)
    if current_round.get("status") == "available" and current_round.get("score") is not None:
        available.append(current_round)
    latest = available[-1] if available else None
    return {
        "latest_evaluable_round_number": latest.get("round_number") if latest else None,
        "latest_evaluable_result": latest,
    }


async def evaluate_consensus(state: State) -> dict:
    contributions = _current_round_contributions(state)
    evaluation = {
        "judge": THESIS_METRICS_SETTINGS.to_dict(),
        "failure": None,
    }
    if len(contributions) < 2:
        round_result = {
            "round_number": state.round_number,
            "included_agent_ids": [item["agent_id"] for item in contributions],
            "included_participant_count": len(contributions),
            **_consensus_unavailable(
                "insufficient_evidence",
                "At least two valid participant contributions are required.",
            ),
        }
        return {
            "evaluation": evaluation,
            "round": round_result,
            "run": _consensus_run_summary(state, round_result),
        }

    message = "ORIGINAL PROBLEM:\n" + state.topic + "\n\nCONTRIBUTIONS:\n" + json.dumps(
        contributions, ensure_ascii=False, separators=(",", ":")
    )
    try:
        judged = await _structured_judge_call(
            instructions=CONSENSUS_JUDGE_INSTRUCTIONS,
            tool_name=CONSENSUS_TOOL_NAME,
            output_model=ConsensusJudgeOutput,
            message=message,
            normalize=_sanitize_consensus_output,
        )
        result = judged.model_dump()
    except json.JSONDecodeError as exc:
        evaluation["failure"] = _metric_failure("json_parsing_failure", str(exc))
        result = _consensus_unavailable("error", "Judge output could not be parsed as JSON.")
    except ValidationError as exc:
        reason = _validation_failure_reason(exc)
        evaluation["failure"] = _metric_failure("schema_validation_failure", reason)
        result = _consensus_unavailable("error", reason)
    except Exception as exc:
        error_type = type(exc).__name__
        logger.warning("Consensus judge failed (%s): %s", error_type, exc)
        evaluation["failure"] = _metric_failure("provider_or_runtime_error", error_type)
        result = _consensus_unavailable("error", f"Judge provider/runtime error ({error_type}).")
    round_result = {
        "round_number": state.round_number,
        "included_agent_ids": [item["agent_id"] for item in contributions],
        "included_participant_count": len(contributions),
        **result,
    }
    return {
        "evaluation": evaluation,
        "round": round_result,
        "run": _consensus_run_summary(state, round_result),
    }


def _lexical_tokens(text: str) -> frozenset[str]:
    return frozenset(re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE))


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float | None:
    if not left or not right:
        return None
    return len(left & right) / len(left | right)


def _convergence_observations(state: State, current_round: dict) -> list[dict]:
    observations = []
    for prior in state.rounds:
        value = prior.thesis_metrics.get("conversation_convergence", {}).get("round", {})
        if value.get("status") == "available" and value.get("round_score") is not None:
            observations.append({
                "round_number": prior.round_number,
                "round_score": value["round_score"],
            })
    if current_round.get("status") == "available":
        observations.append({
            "round_number": state.round_number,
            "round_score": current_round["round_score"],
        })
    return observations


def _convergence_run_summary(state: State, current_round: dict) -> dict:
    observations = _convergence_observations(state, current_round)
    first_round = next((item for item in observations if item["round_number"] == 1), None)
    latest = observations[-1] if observations else None
    slope = None
    if len(observations) >= 2:
        xs = [item["round_number"] for item in observations]
        ys = [item["round_score"] for item in observations]
        mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
        denominator = sum((value - mean_x) ** 2 for value in xs)
        if denominator:
            slope = sum(
                (x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)
            ) / denominator
    return {
        "observations": observations,
        "first_round_score": first_round["round_score"] if first_round else None,
        "latest_score": latest["round_score"] if latest else None,
        "latest_round_number": latest["round_number"] if latest else None,
        "delta_from_first_round": (
            latest["round_score"] - first_round["round_score"]
            if first_round and latest else None
        ),
        "slope": slope,
    }


def evaluate_conversation_convergence(state: State) -> dict:
    contributions = _current_round_contributions(state)
    usable = [
        (item["agent_id"], _lexical_tokens(item["message"]))
        for item in contributions
        if _lexical_tokens(item["message"])
    ]
    pair_scores = [
        score
        for (_, left), (_, right) in combinations(usable, 2)
        if (score := _jaccard(left, right)) is not None
    ]
    if len(usable) < 2 or not pair_scores:
        round_result = {
            "round_number": state.round_number,
            "status": "insufficient_evidence",
            "round_score": None,
            "pair_count": 0,
            "included_agent_ids": [agent_id for agent_id, _ in usable],
            "reason": "At least two token-bearing participant contributions are required.",
        }
    else:
        round_result = {
            "round_number": state.round_number,
            "status": "available",
            "round_score": round(sum(pair_scores) / len(pair_scores), 6),
            "pair_count": len(pair_scores),
            "included_agent_ids": [agent_id for agent_id, _ in usable],
            "reason": "Mean pairwise Jaccard lexical overlap for the current round.",
        }
    return {
        "definition_version": LEXICAL_CONVERGENCE_VERSION,
        "method": "mean_pairwise_jaccard_token_set_similarity",
        "round": round_result,
        "run": _convergence_run_summary(state, round_result),
    }


async def evaluate_thesis_metrics(state: State) -> dict:
    """Evaluate the three final metrics independently so one failure cannot erase the others."""
    try:
        payload = await evaluate_personality_stability(state)
    except Exception as exc:
        logger.exception("Unhandled Personality Stability error")
        payload = personality_stability_error_payload(state)
        payload["personality_stability"]["evaluation"]["failure"] = _metric_failure(
            "provider_or_runtime_error", type(exc).__name__
        )
    try:
        payload["consensus"] = await evaluate_consensus(state)
    except Exception as exc:
        logger.exception("Unhandled Consensus error")
        payload["consensus"] = {
            "evaluation": {
                "judge": THESIS_METRICS_SETTINGS.to_dict(),
                "failure": _metric_failure("provider_or_runtime_error", type(exc).__name__),
            },
            "round": {
                "round_number": state.round_number,
                "included_agent_ids": [],
                "included_participant_count": 0,
                **_consensus_unavailable("error", "Consensus evaluation failed."),
            },
            "run": _consensus_run_summary(state, {}),
        }
    try:
        payload["conversation_convergence"] = evaluate_conversation_convergence(state)
    except Exception as exc:
        logger.exception("Unhandled Conversation Convergence error")
        round_result = {
            "round_number": state.round_number,
            "status": "error",
            "round_score": None,
            "pair_count": 0,
            "included_agent_ids": [],
            "reason": f"Convergence calculation failed ({type(exc).__name__}).",
        }
        payload["conversation_convergence"] = {
            "definition_version": LEXICAL_CONVERGENCE_VERSION,
            "method": "mean_pairwise_jaccard_token_set_similarity",
            "round": round_result,
            "run": _convergence_run_summary(state, round_result),
        }
    return payload
