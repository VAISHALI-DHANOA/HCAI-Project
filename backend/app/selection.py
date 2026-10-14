from __future__ import annotations

import hashlib
import random

from app.models import Agent


def select_speakers(agents: list[Agent], run_id: str, round_number: int) -> list[Agent]:
    mediators = [a for a in agents if a.role == "mediator"]
    users = [a for a in agents if a.role == "user"]
    if len(mediators) != 1:
        raise ValueError("Exactly 1 mediator (The Chair) is required")
    if len(users) < 4:
        raise ValueError("At least 4 user agents are required to run a round")

    # A run and round uniquely determine the order, so it can be reproduced
    # from the run_id and round number recorded in the session log.
    seed_material = f"{run_id}:{round_number}".encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(seed_material).digest(), "big")
    random.Random(seed).shuffle(users)

    return mediators + users
