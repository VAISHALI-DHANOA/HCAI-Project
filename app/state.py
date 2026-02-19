from __future__ import annotations

from threading import RLock

from app.agent_factory import create_mediators
from app.models import Agent, SimulationState


class InMemoryStateStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._state: SimulationState | None = None

    def ensure_state(self, topic: str) -> SimulationState:
        with self._lock:
            if self._state is None:
                self._state = SimulationState(
                    topic=topic,
                    agents=create_mediators(),
                    world_state={"round": 0},
                )
            return self._state

    def get_state(self) -> SimulationState:
        with self._lock:
            if self._state is None:
                raise ValueError("State is not initialized. Add agents first.")
            return self._state

    def add_agents(self, topic: str, new_agents: list[Agent]) -> SimulationState:
        with self._lock:
            state = self.ensure_state(topic)
            existing_ids = {agent.id for agent in state.agents}
            for agent in new_agents:
                if agent.id not in existing_ids:
                    state.agents.append(agent)
            return state

    def reset(self) -> None:
        with self._lock:
            self._state = None


STORE = InMemoryStateStore()
