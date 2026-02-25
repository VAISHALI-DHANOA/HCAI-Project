"""Deterministic visual generation — no LLM calls.

Replaces generate_table_action_and_visual, generate_dashboard_visual,
and generate_dashboard_narrative from llm.py with pure backend computation.
This cuts per-round API calls by ~50%, eliminating rate-limit errors.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)

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
    """Select columns for a chart, preferring message-mentioned ones."""
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
# Chart spec builders
# ---------------------------------------------------------------------------

ROUND_CHART_TYPES: dict[int, tuple[str, str]] = {
    1: ("stat_card", "table"),
    2: ("table", "stat_card"),
    3: ("bar_chart", "line_chart"),
    4: ("scatter", "heatmap"),
    5: ("bar_chart", "stat_card"),
}
DEFAULT_CHART_TYPES = ("bar_chart", "line_chart")

ROUND_AGGREGATIONS: dict[int, list[str]] = {
    1: ["count", "mean"],
    2: ["count", "mean"],
    3: ["mean", "sum", "count"],
    4: ["mean", "median"],
    5: ["mean", "sum", "max"],
}

_ROUND_TOPICS = {
    1: "Dataset Overview",
    2: "Data Quality Check",
    3: "Distribution Analysis",
    4: "Relationship Exploration",
    5: "Key Findings",
}


def _validate_chart_feasibility(
    visual_type: str,
    cat_cols: list[str],
    num_cols: list[str],
    primary: str,
    secondary: str,
) -> str:
    requirements: dict[str, Any] = {
        "bar_chart":  lambda: len(cat_cols) >= 1,
        "line_chart": lambda: len(cat_cols) >= 1,
        "scatter":    lambda: len(num_cols) >= 2,
        "heatmap":    lambda: len(num_cols) >= 2,
        "stat_card":  lambda: len(num_cols) >= 1,
        "table":      lambda: True,
    }
    for candidate in [visual_type, primary, secondary, "stat_card", "table"]:
        if requirements.get(candidate, lambda: True)():
            return candidate
    return "table"


def _build_spec_for_type(
    visual_type: str,
    sel_cat: list[str],
    sel_num: list[str],
    agg: str,
    agent_seed: str,
    all_columns: list[str],
    cat_cols: list[str],
    num_cols: list[str],
) -> dict:
    """Build the inner 'spec' dict for compute_chart_data."""

    if visual_type == "bar_chart":
        x_col = sel_cat[0] if sel_cat else (cat_cols[0] if cat_cols else all_columns[0])
        y_col = sel_num[0] if sel_num else ""
        sort_dir = "desc" if _stable_hash(agent_seed + "_sort", 2) == 0 else "asc"
        return {
            "x_column": x_col,
            "y_column": y_col,
            "aggregation": agg if y_col else "count",
            "sort": sort_dir,
            "top_n": 10,
        }

    if visual_type == "line_chart":
        x_col = sel_cat[0] if sel_cat else (cat_cols[0] if cat_cols else all_columns[0])
        y_col = sel_num[0] if sel_num else ""
        return {
            "x_column": x_col,
            "y_column": y_col,
            "aggregation": agg if y_col else "count",
            "top_n": 20,
        }

    if visual_type == "scatter":
        x_num = sel_num[0] if sel_num else (num_cols[0] if num_cols else all_columns[0])
        y_num = sel_num[1] if len(sel_num) >= 2 else (
            num_cols[1] if len(num_cols) >= 2 else x_num
        )
        if x_num == y_num and len(num_cols) >= 2:
            candidates = [c for c in num_cols if c != x_num]
            if candidates:
                y_num = candidates[_stable_hash(agent_seed + "_sc", len(candidates))]
        return {"x_column": x_num, "y_column": y_num, "sample_n": 50}

    if visual_type == "heatmap":
        n_heat = min(5, len(num_cols))
        offset = _stable_hash(agent_seed + "_heat", max(len(num_cols), 1))
        seen: set[str] = set()
        heat_cols: list[str] = []
        for i in range(n_heat):
            c = num_cols[(offset + i) % len(num_cols)]
            if c not in seen:
                heat_cols.append(c)
                seen.add(c)
        return {"columns": heat_cols}

    if visual_type == "stat_card":
        n_metrics = min(4, len(num_cols))
        offset = _stable_hash(agent_seed + "_stat", max(len(num_cols), 1))
        agg_cycle = ["mean", "median", "max", "min"]
        metrics: list[dict[str, str]] = []
        for i in range(n_metrics):
            col = num_cols[(offset + i) % len(num_cols)]
            m_agg = agg_cycle[i % len(agg_cycle)]
            label = _humanize_column(col)
            if len(label) > 20:
                label = label[:17] + "..."
            label += f" ({m_agg})"
            metrics.append({"column": col, "aggregation": m_agg, "label": label})
        return {"metrics": metrics}

    # table (default)
    n_show = min(6, len(all_columns))
    offset = _stable_hash(agent_seed + "_tbl", max(len(all_columns), 1))
    seen_t: set[str] = set()
    show_cols: list[str] = []
    for i in range(n_show):
        c = all_columns[(offset + i) % len(all_columns)]
        if c not in seen_t:
            show_cols.append(c)
            seen_t.add(c)
    sort_col = sel_num[0] if sel_num else (num_cols[0] if num_cols else None)
    return {
        "columns": show_cols,
        "sort_by": sort_col,
        "sort_order": "desc",
        "head_n": 10,
    }


def _generate_title(
    visual_type: str,
    sel_cat: list[str],
    sel_num: list[str],
    agg: str,
    round_number: int,
) -> str:
    if visual_type in ("bar_chart", "line_chart") and sel_cat and sel_num:
        return f"{agg.capitalize()} {_humanize_column(sel_num[0])} by {_humanize_column(sel_cat[0])}"
    if visual_type == "scatter" and len(sel_num) >= 2:
        return f"{_humanize_column(sel_num[0])} vs {_humanize_column(sel_num[1])}"
    if visual_type == "heatmap":
        return "Correlation Heatmap"
    topic = _ROUND_TOPICS.get(round_number, "Analysis")
    if visual_type == "stat_card":
        return f"{topic}: Key Metrics"
    if visual_type == "table":
        return f"{topic}: Data Sample"
    cols_str = ", ".join(_humanize_column(c) for c in (sel_num + sel_cat)[:2])
    return f"Analyzing {cols_str}"


def _generate_description(
    visual_type: str,
    sel_cat: list[str],
    sel_num: list[str],
    round_number: int,
) -> str:
    topic = _ROUND_TOPICS.get(round_number, "analysis").lower()
    if visual_type == "bar_chart" and sel_cat and sel_num:
        return f"Comparing {_humanize_column(sel_num[0])} across {_humanize_column(sel_cat[0])} categories."
    if visual_type == "scatter" and len(sel_num) >= 2:
        return f"Exploring the relationship between {_humanize_column(sel_num[0])} and {_humanize_column(sel_num[1])}."
    if visual_type == "heatmap":
        return "Correlation matrix showing relationships among numeric indicators."
    if visual_type == "stat_card":
        return f"Summary statistics for {topic}."
    if visual_type == "table":
        return f"Detailed data rows for {topic} inspection."
    if visual_type == "line_chart" and sel_cat and sel_num:
        return f"Trend of {_humanize_column(sel_num[0])} across {_humanize_column(sel_cat[0])}."
    return f"Visual analysis for round {round_number}."


def _build_visual_spec_for_round(
    round_number: int,
    agent_seed: str,
    mentioned: list[str],
    cat_cols: list[str],
    num_cols: list[str],
    sel_cat: list[str],
    sel_num: list[str],
    all_columns: list[str],
) -> dict:
    """Build a lightweight chart spec dict for the given round."""
    primary, secondary = ROUND_CHART_TYPES.get(round_number, DEFAULT_CHART_TYPES)
    use_secondary = _stable_hash(agent_seed + "_vtype", 2) == 1
    visual_type = secondary if use_secondary else primary
    visual_type = _validate_chart_feasibility(visual_type, cat_cols, num_cols, primary, secondary)

    agg_options = ROUND_AGGREGATIONS.get(round_number, ["mean"])
    agg = agg_options[_stable_hash(agent_seed + "_agg", len(agg_options))]

    spec = _build_spec_for_type(
        visual_type, sel_cat, sel_num, agg,
        agent_seed, all_columns, cat_cols, num_cols,
    )
    title = _generate_title(visual_type, sel_cat, sel_num, agg, round_number)
    description = _generate_description(visual_type, sel_cat, sel_num, round_number)

    return {
        "visual_type": visual_type,
        "title": title,
        "description": description,
        "spec": spec,
    }


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
# Public API — drop-in replacements for LLM functions
# ---------------------------------------------------------------------------

def compute_table_action_and_visual(
    agent: Any,
    state: Any,
    agent_message: str,
    round_number: int = 0,
    column_names: list[str] | None = None,
    row_count: int = 200,
) -> dict:
    """Deterministic replacement for llm.generate_table_action_and_visual.

    Returns dict with 'table_action' and 'visual' keys — identical shape.
    """
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
    hl_half = 3
    hl_start = max(0, nav_row - hl_half)
    hl_end = min(row_count - 1, nav_row + hl_half)

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

    # --- Visual Spec ---
    visual = _build_visual_spec_for_round(
        round_number, agent_seed, mentioned,
        cat_cols, num_cols, sel_cat, sel_num, column_names,
    )

    return {"table_action": table_action, "visual": visual}


def compute_dashboard_visual(
    agent: Any,
    state: Any,
    agent_message: str,
    round_number: int = 0,
    column_names: list[str] | None = None,
    dashboard_narrative: str = "",
) -> dict | None:
    """Deterministic replacement for llm.generate_dashboard_visual.

    Returns dict with visual_type, title, description, spec — identical shape.
    """
    if not state.dataset_summary or not column_names:
        return None

    agent_seed = f"{agent.id}_{round_number}"
    mentioned = _extract_mentioned_columns(agent_message, column_names)

    # Also extract from narrative and human_request
    for extra_text in [dashboard_narrative, state.human_request]:
        if extra_text:
            for col in _extract_mentioned_columns(extra_text, column_names):
                if col not in mentioned:
                    mentioned.append(col)

    cat_cols, num_cols = _classify_columns(column_names, state.dataset_summary)
    sel_cat, sel_num = _pick_columns_for_agent(mentioned, cat_cols, num_cols, agent_seed)

    return _build_visual_spec_for_round(
        round_number, agent_seed, mentioned,
        cat_cols, num_cols, sel_cat, sel_num, column_names,
    )


# ---------------------------------------------------------------------------
# Dashboard narrative
# ---------------------------------------------------------------------------

_NARRATIVE_TEMPLATES = [
    "How does {col1} relate to {col2} across different {cat} categories in this dataset?",
    "What drives variation in {col1} and {col2}, and which {cat} groups stand out?",
    "Exploring whether {col1} and {col2} reveal meaningful patterns when segmented by {cat}.",
    "Which {cat} segments show the strongest interplay between {col1} and {col2}?",
    "Investigating the connection between {col1} and {col2} to identify actionable {cat}-level insights.",
]

_HUMAN_NARRATIVE_TEMPLATES = [
    "Addressing the question: {request} — examining {col1} and {col2} across {cat} groups.",
    "Responding to '{request}' by analyzing how {col1} and {col2} vary by {cat}.",
    "Investigating '{request}' through the lens of {col1}, {col2}, and {cat} segmentation.",
]


def compute_dashboard_narrative(
    chair: Any,
    state: Any,
    all_turns: list,
) -> str:
    """Deterministic replacement for llm.generate_dashboard_narrative.

    Returns a 1-sentence narrative string — identical usage.
    """
    if not state.dataset_columns:
        return f"Exploring key patterns and relationships in the {state.topic} dataset."

    all_messages = " ".join(
        t.message for t in all_turns if hasattr(t, "message")
    )
    mentioned = _extract_mentioned_columns(all_messages, state.dataset_columns)

    if state.human_request:
        for col in _extract_mentioned_columns(state.human_request, state.dataset_columns):
            if col not in mentioned:
                mentioned.append(col)

    cat_cols, num_cols = _classify_columns(state.dataset_columns, state.dataset_summary)

    col_counts = Counter(mentioned)
    top_mentioned = [col for col, _ in col_counts.most_common()]
    top_num = [c for c in top_mentioned if c in set(num_cols)][:2]
    top_cat = [c for c in top_mentioned if c in set(cat_cols)][:1]

    seed = f"{chair.id}_narrative_{state.round_number}"
    if len(top_num) < 2 and num_cols:
        offset = _stable_hash(seed + "_num", len(num_cols))
        for i in range(2 - len(top_num)):
            candidate = num_cols[(offset + i) % len(num_cols)]
            if candidate not in set(top_num):
                top_num.append(candidate)
    if not top_cat and cat_cols:
        offset = _stable_hash(seed + "_cat", len(cat_cols))
        top_cat = [cat_cols[offset % len(cat_cols)]]

    col1 = _humanize_column(top_num[0]) if top_num else "key indicators"
    col2 = _humanize_column(top_num[1]) if len(top_num) >= 2 else "overall patterns"
    cat = _humanize_column(top_cat[0]) if top_cat else "segment"

    if state.human_request:
        short_request = state.human_request
        if len(short_request) > 60:
            short_request = short_request[:57] + "..."
        templates = _HUMAN_NARRATIVE_TEMPLATES
        idx = _stable_hash(seed + "_tmpl", len(templates))
        return templates[idx].format(request=short_request, col1=col1, col2=col2, cat=cat)

    templates = _NARRATIVE_TEMPLATES
    idx = _stable_hash(seed + "_tmpl", len(templates))
    return templates[idx].format(col1=col1, col2=col2, cat=cat)
