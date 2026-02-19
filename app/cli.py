from __future__ import annotations

import json

from app.agent_factory import create_agents_from_user, create_mediators
from app.models import SimulationState, UserAgentInput
from app.simulation import run_round


def _prompt_int(message: str, minimum: int, maximum: int) -> int:
    while True:
        raw = input(message).strip()
        try:
            value = int(raw)
            if minimum <= value <= maximum:
                return value
        except ValueError:
            pass
        print(f"Enter an integer between {minimum} and {maximum}.")


def _collect_user_agents() -> list[UserAgentInput]:
    print("Add up to 25 user agents. Leave name empty to stop.")
    collected: list[UserAgentInput] = []
    while len(collected) < 25:
        name = input(f"Agent {len(collected) + 1} name: ").strip()
        if not name:
            break
        persona = input("Persona text: ").strip()
        if not persona:
            print("Persona text is required.")
            continue
        energy_raw = input("Energy 0.0-1.0 (default 0.6): ").strip()
        energy = 0.6
        if energy_raw:
            try:
                energy = max(0.0, min(1.0, float(energy_raw)))
            except ValueError:
                print("Invalid energy; using default 0.6.")
        collected.append(UserAgentInput(name=name, persona_text=persona, energy=energy))
    return collected


def main() -> None:
    print("Creative Multi-Agent Playground")
    topic = input("Topic: ").strip() or "Untitled classroom inquiry"
    user_inputs = _collect_user_agents()
    if len(user_inputs) < 4:
        print("At least 4 user agents are required.")
        return

    state = SimulationState(topic=topic, agents=create_mediators(), world_state={"round": 0})
    state.agents.extend(create_agents_from_user(topic, user_inputs))

    rounds = _prompt_int("How many rounds? (1-20): ", 1, 20)
    for _ in range(rounds):
        result = run_round(state)
        print(f"\n=== Round {result.round_number} ===")
        print(json.dumps(result.model_dump(), indent=2))

    print("\n=== Final State ===")
    print(json.dumps(state.model_dump(), indent=2))


if __name__ == "__main__":
    main()

