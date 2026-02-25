from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from app.agent_factory import create_mediators
from app.models import Agent, RoundResult, State

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)


class InMemoryStateStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._state: State = State(
            topic="Untitled classroom inquiry",
            agents=create_mediators(),
            world_state={"round": 0},
        )
        self._session_id: str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._round_log: list[dict] = []

    def get_state(self) -> State:
        with self._lock:
            return self._state

    def set_topic(self, topic: str) -> State:
        with self._lock:
            self._state.topic = topic
            self._state.round_number = 0
            self._state.public_history.clear()
            self._state.reactions.clear()
            self._state.world_state = {"round": 0}
            for agent in self._state.agents:
                if agent.role == "user":
                    agent.stance = f"{agent.name} approaches {topic} constructively while staying adaptable."
            return self._state

    def set_dataset_summary(self, summary: str, filename: str) -> State:
        with self._lock:
            self._state.dataset_summary = summary
            self._state.topic = f"Analyze the uploaded dataset: {filename}"
            self._state.round_number = 0
            self._state.public_history.clear()
            self._state.reactions.clear()
            self._state.world_state = {"round": 0}
            return self._state

    def reset(self, topic: str | None = None) -> State:
        with self._lock:
            next_topic = topic if topic and topic.strip() else "Untitled classroom inquiry"
            self._state = State(
                topic=next_topic,
                agents=create_mediators(),
                world_state={"round": 0},
                dataset_summary="",
            )
            self._session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            self._round_log = []
            return self._state

    def add_agents(self, new_agents: list[Agent]) -> State:
        with self._lock:
            existing_ids = {agent.id for agent in self._state.agents}
            for agent in new_agents:
                if agent.id not in existing_ids:
                    self._state.agents.append(agent)
            return self._state

    def save_round(self, result: RoundResult) -> None:
        """Persist a round result to the session log and write to disk."""
        with self._lock:
            self._round_log.append(result.model_dump())
            self._write_log_file()

    def get_full_log(self) -> dict:
        """Return the full conversation log for the current session."""
        with self._lock:
            return {
                "session_id": self._session_id,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "topic": self._state.topic,
                "agents": [a.model_dump() for a in self._state.agents],
                "rounds": list(self._round_log),
            }

    def _write_log_file(self) -> None:
        log_path = LOGS_DIR / f"session_{self._session_id}.json"
        data = {
            "session_id": self._session_id,
            "topic": self._state.topic,
            "agents": [a.model_dump() for a in self._state.agents],
            "rounds": list(self._round_log),
        }
        log_path.write_text(json.dumps(data, indent=2, default=str))


class SessionManager:
    """Maps session IDs to isolated InMemoryStateStore instances."""

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
