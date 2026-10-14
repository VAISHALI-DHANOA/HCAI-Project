"""Deterministic table navigation and annotations for early data rounds."""

from __future__ import annotations

import hashlib
import re
from typing import Any

# ---------------------------------------------------------------------------
# Hashing & column extraction
# ---------------------------------------------------------------------------

def _stable_hash(seed: str, mod: int) -> int:
    """Deterministic hash -> integer in [0, mod). Uses MD5 for uniform distribution."""
    if mod <= 0:
        return 0
    digest = hashlib.md5(seed.encode()).hexdigest()
    return int(digest, 16) % mod


def _extract_mentioned_columns(message: str, column_names: list[str]) -> list[str]:
    """Find column names mentioned in text (case-insensitive, underscore-tolerant).

    Replicates the frontend keyword-matching pattern from App.tsx.
    """
    msg_lower = message.lower()
    found: list[str] = []
    for col in column_names:
        col_lower = col.lower()
        if col_lower in msg_lower:
            found.append(col)
            continue
        spaced = col_lower.replace("_", " ")
        if spaced != col_lower and spaced in msg_lower:
            found.append(col)
    return found


def _classify_columns(
    column_names: list[str], dataset_summary: str = "",
) -> tuple[list[str], list[str]]:
    """Split columns into (categorical, numeric) using dtype hints from summary."""
    numeric_dtypes = {"int64", "float64", "int32", "float32", "int", "float"}
    dtype_map: dict[str, str] = {}
    for line in dataset_summary.split("\n"):
        match = re.match(r"\s+-\s+(\S+)\s+\[(\w+)\]", line)
        if match:
            dtype_map[match.group(1)] = match.group(2)

    cat_cols: list[str] = []
    num_cols: list[str] = []
    numeric_keywords = (
        "score", "rate", "index", "pct", "usd", "per_", "count",
        "population", "density", "income", "price", "cost", "amount",
        "total", "avg", "mean", "ratio", "percent", "tons", "hectare",
        "usage", "m3",
    )
    for col in column_names:
        dtype = dtype_map.get(col, "")
        if dtype in numeric_dtypes:
            num_cols.append(col)
        elif dtype.startswith("object") or dtype == "str":
            cat_cols.append(col)
        else:
            lower = col.lower()
            if any(kw in lower for kw in numeric_keywords):
                num_cols.append(col)
            elif col.endswith("_ID") or col.endswith("_id"):
                cat_cols.append(col)
            else:
                cat_cols.append(col)
    return cat_cols, num_cols


# ---------------------------------------------------------------------------
# Column selection
# ---------------------------------------------------------------------------

def _pick_columns_for_agent(
    mentioned: list[str],
    cat_cols: list[str],
    num_cols: list[str],
    agent_seed: str,
    n_numeric: int = 2,
    n_categorical: int = 1,
) -> tuple[list[str], list[str]]:
    """Select columns for table navigation, preferring message-mentioned ones."""
    cat_set, num_set = set(cat_cols), set(num_cols)
    mentioned_cat = [c for c in mentioned if c in cat_set]
    mentioned_num = [c for c in mentioned if c in num_set]
    mentioned_set = set(mentioned)

    # Fill categorical
    sel_cat = mentioned_cat[:n_categorical]
    if len(sel_cat) < n_categorical:
        remaining = [c for c in cat_cols if c not in mentioned_set]
        if remaining:
            offset = _stable_hash(agent_seed + "_cat", len(remaining))
            for i in range(n_categorical - len(sel_cat)):
                sel_cat.append(remaining[(offset + i) % len(remaining)])

    # Fill numeric
    sel_num = mentioned_num[:n_numeric]
    if len(sel_num) < n_numeric:
        remaining = [c for c in num_cols if c not in mentioned_set]
        if remaining:
            offset = _stable_hash(agent_seed + "_num", len(remaining))
            for i in range(n_numeric - len(sel_num)):
                sel_num.append(remaining[(offset + i) % len(remaining)])

    return sel_cat, sel_num


def _humanize_column(col: str) -> str:
    return col.replace("_", " ")


# ---------------------------------------------------------------------------
# Annotation helpers
# ---------------------------------------------------------------------------

_ANNOTATION_TEMPLATES = [
    "Check {col} values here",
    "Notable {col} pattern",
    "Unusual {col} range",
    "{col} stands out",
    "Compare {col} rows",
]


def _generate_annotation_text(
    mentioned: list[str],
    sel_num: list[str],
    agent_name: str,
    round_number: int,
) -> str:
    col_label = (mentioned[:1] or sel_num[:1] or ["data"])[0]
    short_col = _humanize_column(col_label)
    if len(short_col) > 15:
        short_col = short_col[:12] + "..."
    idx = _stable_hash(f"{agent_name}_{round_number}_ann", len(_ANNOTATION_TEMPLATES))
    return _ANNOTATION_TEMPLATES[idx].format(col=short_col)[:30]


# ---------------------------------------------------------------------------
# Public table-action API
# ---------------------------------------------------------------------------

def compute_table_action_and_visual(
    agent: Any,
    state: Any,
    agent_message: str,
    round_number: int = 0,
    column_names: list[str] | None = None,
    row_count: int = 200,
) -> dict:
    """Return the table action used during onboarding and data quality rounds."""
    if not column_names:
        return {}

    agent_seed = f"{agent.id}_{round_number}"
    mentioned = _extract_mentioned_columns(agent_message, column_names)
    cat_cols, num_cols = _classify_columns(column_names, state.dataset_summary)
    sel_cat, sel_num = _pick_columns_for_agent(mentioned, cat_cols, num_cols, agent_seed)

    # --- Table Action ---
    nav_row = _stable_hash(agent_seed + "_nav", max(row_count, 1))
    nav_col = (mentioned or sel_num or sel_cat or column_names)[0]

    hl_cols = (mentioned or sel_num or sel_cat)[:2]
    if not hl_cols:
        hl_cols = [column_names[0]]
    # Highlight entire columns so the agent's focus area is clearly visible
    hl_start = 0
    hl_end = row_count - 1

    annotation_text = _generate_annotation_text(mentioned, sel_num, agent.name, round_number)

    table_action = {
        "navigate_to": {"row": nav_row, "column": nav_col},
        "highlights": [{
            "row_start": hl_start,
            "row_end": hl_end,
            "columns": hl_cols,
        }],
        "annotations": [{
            "row": nav_row,
            "column": nav_col,
            "text": annotation_text,
        }],
    }

    return {"table_action": table_action}
