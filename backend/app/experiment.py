"""Export provenance, independent of prompt construction and execution."""
import hashlib
from functools import lru_cache
from pathlib import Path

from app.config import (
    CHAT_SETTINGS, DATA_CONTRIBUTION_SETTINGS, DISCUSSION_SETTINGS,
    SUMMARY_SETTINGS, THESIS_METRICS_SETTINGS, VISUAL_SETTINGS,
)
from app.thesis_metrics import THESIS_METRICS_VERSION
from app.models import State
from app.moderator import get_moderator_strategy

EXPORT_SCHEMA_VERSION = "experiment-export-v3"


@lru_cache(maxsize=1)
def source_fingerprints() -> dict[str, str]:
    folder = Path(__file__).parent
    return {
        name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
        for name in ("prompts.py", "history.py", "models.py", "personality.py", "moderator.py", "config.py", "thesis_metrics.py", "selection.py", "simulation.py", "llm.py", "analysis.py")
    }


def configuration_snapshot(state: State, dataset: dict) -> dict:
    return {
        "run_id": state.run_id,
        "speaker_order": {
            "policy": "seeded_random_v1",
            "seed": state.run_id,
        },
        "topic": state.topic,
        "agents": [agent.model_dump() for agent in state.agents],
        "moderator": get_moderator_strategy(state.moderator_strategy_id).model_dump(),
        "generation_settings": {
            "discussion": DISCUSSION_SETTINGS.to_dict(), "summary": SUMMARY_SETTINGS.to_dict(),
            "chat": CHAT_SETTINGS.to_dict(), "visual": VISUAL_SETTINGS.to_dict(),
            "data_contribution": DATA_CONTRIBUTION_SETTINGS.to_dict(),
            "thesis_metrics_judge": THESIS_METRICS_SETTINGS.to_dict(),
        },
        "dataset": {
            **dataset, "summary": state.dataset_summary, "columns": list(state.dataset_columns),
            "row_count": state.world_state.get("dataset_row_count"),
        },
        "human_request": state.human_request,
        "thesis_metrics_version": THESIS_METRICS_VERSION,
        "source_sha256": dict(source_fingerprints()),
    }
