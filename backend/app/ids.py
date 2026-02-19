from __future__ import annotations

import re
import uuid

NAMESPACE = uuid.UUID("2e8f9e94-6ab2-4f2d-9ab0-6f94af5ff58e")


def slugify(value: str) -> str:
    lowered = value.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "agent"


def deterministic_agent_id(role: str, name: str, persona_text: str, index: int) -> str:
    key = f"{role}|{name.strip().lower()}|{persona_text.strip().lower()}|{index}"
    uid = uuid.uuid5(NAMESPACE, key)
    return f"{role[:1]}_{slugify(name)}_{uid.hex[:10]}"
