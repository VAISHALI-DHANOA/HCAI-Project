from __future__ import annotations

from threading import RLock

from app.agent_factory import create_mediators
from app.models import Agent, State


class InMemoryStateStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._state: State = State(
            topic="Untitled classroom inquiry",
            agents=create_mediators(),
            world_state={"round": 0},
        )

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

    def reset(self, topic: str | None = None) -> State:
        with self._lock:
            next_topic = topic if topic and topic.strip() else "Untitled classroom inquiry"
            self._state = State(
                topic=next_topic,
                agents=create_mediators(),
                world_state={"round": 0},
            )
            return self._state

    def add_agents(self, new_agents: list[Agent]) -> State:
        with self._lock:
            existing_ids = {agent.id for agent in self._state.agents}
            for agent in new_agents:
                if agent.id not in existing_ids:
                    self._state.agents.append(agent)
            return self._state


STORE = InMemoryStateStore()
