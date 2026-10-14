from __future__ import annotations

import hashlib
import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from app.agent_factory import create_agents_from_user, create_mediators
from app.experiment import EXPORT_SCHEMA_VERSION, configuration_snapshot
from app.models import Agent, DraftAgentInput, PublicTurn, RoundResult, State, UserAgentInput
from app.moderator import DEFAULT_MODERATOR_STRATEGY_ID

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionBusyError(RuntimeError):
    pass


class InMemoryStateStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._busy = False
        self._revision = 0
        self._active_round: State | None = None
        self._round_intervention_start: int | None = None
        self._state = State(
            topic="Untitled classroom inquiry", agents=create_mediators(),
            world_state={"round": 0}, moderator_strategy_id=DEFAULT_MODERATOR_STRATEGY_ID,
        )
        self._start_metadata()

    def _start_metadata(self) -> None:
        self._started_at = utc_now()
        self._dataset: dict = {}
        self._interventions: list[dict] = []
        self._configuration_events: list[dict] = []
        self._failed_rounds: list[dict] = []

    @contextmanager
    def mutation(self):
        """Reject overlapping mutations, without holding a thread lock over await."""
        with self._lock:
            if self._busy:
                raise SessionBusyError("Session is busy. Wait for the current operation to finish, then retry.")
            self._busy = True
        try:
            yield
        finally:
            with self._lock:
                self._busy = False

    def _touch(self) -> None:
        self._revision += 1
        self._state.revision = self._revision

    def get_state(self) -> State:
        with self._lock:
            return self._state

    def _archive_current(self) -> None:
        if self._state.rounds or self._state.public_history or self._configuration_events:
            self._write_log_file(self._state)

    def set_topic(self, topic: str) -> State:
        with self._lock:
            self._archive_current()
            self._state.topic = topic
            self._state.run_id = uuid4().hex
            self._state.round_number = 0
            self._state.public_history.clear()
            self._state.reactions.clear()
            self._state.rounds.clear()
            self._state.world_state = {"round": 0}
            self._state.dataset_summary = ""
            self._state.dataset_columns = []
            self._state.dataset_preview = None
            self._state.human_request = ""
            self._start_metadata()
            self._touch()
            return self._state

    def set_dataset_summary(self, summary: str, filename: str) -> State:
        with self._lock:
            self._archive_current()
            self._state.run_id = uuid4().hex
            self._state.dataset_summary = summary
            self._state.dataset_preview = None
            self._state.topic = f"Analyze the uploaded dataset: {filename}"
            self._state.round_number = 0
            self._state.public_history.clear()
            self._state.reactions.clear()
            self._state.rounds.clear()
            self._state.world_state = {"round": 0}
            self._state.human_request = ""
            self._start_metadata()
            self._touch()
            return self._state

    def reset(self, topic: str | None = None, *, preserve_agents: bool = False) -> State:
        with self._lock:
            self._archive_current()
            agents = (
                [agent.model_copy(deep=True) for agent in self._state.agents]
                if preserve_agents else create_mediators()
            )
            self._state = State(
                topic=topic if topic and topic.strip() else "Untitled classroom inquiry",
                agents=agents, world_state={"round": 0},
                moderator_strategy_id=DEFAULT_MODERATOR_STRATEGY_ID,
            )
            self._start_metadata()
            self._touch()
            return self._state

    def add_agents(self, new_agents: list[Agent]) -> State:
        with self._lock:
            existing_ids = {agent.id for agent in self._state.agents}
            for agent in new_agents:
                if agent.id not in existing_ids:
                    self._state.agents.append(agent)
                    existing_ids.add(agent.id)
            self._touch()
            return self._state

    def sync_agents(self, drafts: list[DraftAgentInput], run_id: str, revision: int) -> State:
        with self._lock:
            if run_id != self._state.run_id or revision != self._state.revision:
                raise SessionBusyError("The roster changed in another request. Reload it before saving.")
            if self._state.rounds or self._state.round_number:
                raise SessionBusyError("Agent drafts can only be synchronized before discussion starts.")
            existing = {agent.id: agent for agent in self._state.agents if agent.role == "user"}
            roster: list[Agent] = []
            seen: set[str] = set()
            generated_agents = create_agents_from_user(self._state.topic, [
                UserAgentInput.model_validate(draft.model_dump(exclude={"id"})) for draft in drafts
            ])
            for index, draft in enumerate(drafts):
                generated = generated_agents[index]
                if draft.id is not None:
                    if draft.id not in existing or draft.id in seen:
                        raise ValueError("Unknown or repeated draft agent ID")
                    original = existing[draft.id]
                    generated = original.model_copy(update={
                        "name": generated.name, "persona_text": generated.persona_text,
                        "personality": generated.personality,
                    })
                elif generated.id in existing or generated.id in seen:
                    # Distinct drafts may have identical names and configurations.
                    generated.id = uuid4().hex
                seen.add(generated.id)
                roster.append(generated)
            self._state.agents = [a for a in self._state.agents if a.role == "mediator"] + roster
            self._touch()
            return self._state

    def begin_round(self) -> State:
        with self._lock:
            if self._active_round is not None:
                raise SessionBusyError("A round is already running.")
            self._active_round = self._state.model_copy(deep=True)
            self._round_intervention_start = len(self._interventions)
            return self._active_round

    def abort_round(self, error_type: str) -> None:
        with self._lock:
            self._failed_rounds.append({
                "attempted_round": self._state.round_number + 1,
                "failed_at": utc_now(), "error_type": error_type,
            })
            self._active_round = None
            self._round_intervention_start = None
            self._touch()
            try:
                self._write_log_file(self._state)
            except OSError:
                logging.getLogger(__name__).exception("Could not persist failed-round metadata")

    def save_round(self, result: RoundResult, working_state: State | None = None) -> None:
        with self._lock:
            target = working_state if working_state is not None else self._state
            if target.run_id != self._state.run_id:
                raise SessionBusyError("Cannot save a round from a different run.")
            if any(item.round_number == result.round_number for item in target.rounds):
                return
            previous_revision = target.revision
            pending_request = target.human_request
            history_length = len(target.public_history)
            queued = (self._interventions[self._round_intervention_start:]
                      if working_state is self._active_round and self._round_intervention_start is not None else [])
            target.rounds.append(result)
            target.revision = self._revision + 1
            # Only consume requests present when this round began. New input
            # stays outside the working snapshot until the next round.
            target.human_request = "\n".join(item["message"] for item in queued)
            target.public_history.extend(
                PublicTurn(speaker_id="human", message=item["message"], turn_type="human",
                           round_number=(item["during_round"] if item["during_round"] is not None
                                         else item["after_completed_round"]),
                           moderator_strategy_id=None)
                for item in queued
            )
            try:
                self._write_log_file(target)
            except BaseException:
                target.rounds.pop()
                target.revision = previous_revision
                target.human_request = pending_request
                del target.public_history[history_length:]
                raise
            self._state = target
            self._revision = target.revision
            self._active_round = None
            self._round_intervention_start = None

    def set_moderator_strategy(self, strategy_id: str) -> State:
        with self._lock:
            self._state.moderator_strategy_id = strategy_id
            self._state.world_state["moderator_strategy_id"] = strategy_id
            self._touch()
            return self._state

    def add_intervention(self, message: str) -> PublicTurn:
        """Log immediately, but freeze the active round's input at its start."""
        with self._lock:
            # Record when input arrived, independently of when it is consumed.
            arrival_round = (self._active_round or self._state).round_number
            turn = PublicTurn(speaker_id="human", message=message, turn_type="human",
                              round_number=arrival_round, moderator_strategy_id=None)
            self._state.public_history.append(turn)
            self._state.human_request = "\n".join(filter(None, [self._state.human_request, message]))
            self._interventions.append({
                "at": utc_now(), "message": message,
                "after_completed_round": self._state.round_number,
                "during_round": self._active_round.round_number if self._active_round else None,
            })
            self._touch()
            self._write_log_file(self._state)
            return turn

    def set_dataset_identity(self, filename: str, contents: bytes) -> None:
        with self._lock:
            self._dataset = {
                "filename": filename, "sha256": hashlib.sha256(contents).hexdigest(),
                "size_bytes": len(contents),
            }

    def experiment_snapshot(self) -> dict:
        with self._lock:
            return configuration_snapshot(self._state, self._dataset)

    def record_configuration(self, action: str) -> None:
        with self._lock:
            self._configuration_events.append({
                "at": utc_now(), "action": action, "after_completed_round": self._state.round_number,
                "configuration": self.experiment_snapshot(),
            })
            self._write_log_file(self._state)

    def _log_payload(self, state: State) -> dict:
        return {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "session_id": state.run_id, "run_id": state.run_id,
            "started_at": self._started_at, "topic": state.topic,
            "moderator_strategy_id": state.moderator_strategy_id,
            "agents": [a.model_dump() for a in state.agents],
            "rounds": [item.model_dump() for item in state.rounds],
            "public_history": [turn.model_dump() for turn in state.public_history],
            "experiment": configuration_snapshot(state, self._dataset),
            "configuration_events": list(self._configuration_events),
            "interventions": list(self._interventions),
            "failed_rounds": list(self._failed_rounds),
        }

    def get_full_log(self) -> dict:
        with self._lock:
            return {**self._log_payload(self._state), "exported_at": utc_now()}

    def _write_log_file(self, state: State) -> None:
        log_path = LOGS_DIR / f"session_{state.run_id}.json"
        temporary = log_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self._log_payload(state), indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(log_path)


class SessionManager:
    """Process-local sessions. Run this prototype with one backend worker."""

    def __init__(self) -> None:
        self._sessions: dict[str, InMemoryStateStore] = {}
        self._csv_paths: dict[str, Path | None] = {}
        self._lock = RLock()

    def get_store(self, session_id: str) -> InMemoryStateStore:
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = InMemoryStateStore()
            return self._sessions[session_id]

    def get_csv_path(self, session_id: str) -> Path | None:
        with self._lock:
            return self._csv_paths.get(session_id)

    def set_csv_path(self, session_id: str, path: Path | None) -> None:
        with self._lock:
            self._csv_paths[session_id] = path


SESSIONS = SessionManager()
