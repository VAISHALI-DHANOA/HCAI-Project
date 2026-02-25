"""Backend computation engine for chart data.

The LLM proposes a lightweight chart specification (columns, aggregation,
chart type). This module executes the computation on the real pandas
DataFrame so that every number rendered in the frontend is reproducible
and derived from actual data.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

_df_cache: dict[str, pd.DataFrame] = {}
_DEFAULT_CSV = Path(__file__).resolve().parent.parent / "ExampleDataset.csv"
_active_csv: Path | None = None


def set_active_dataset(csv_path: str | Path) -> None:
    """Set the active dataset CSV path used by compute_chart_data."""
    global _active_csv
    _active_csv = Path(csv_path)


def load_dataframe(csv_path: str | Path | None = None) -> pd.DataFrame:
    """Load and cache the dataset DataFrame."""
    if csv_path is None:
        csv_path = _active_csv or _DEFAULT_CSV
    key = str(csv_path)
    if key not in _df_cache:
        _df_cache[key] = pd.read_csv(csv_path)
    return _df_cache[key].copy()


def clear_cache() -> None:
    """Clear the cached DataFrames (useful after uploading a new dataset)."""
    _df_cache.clear()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _apply_filter(df: pd.DataFrame, spec: dict) -> pd.DataFrame:
    """Apply an optional single-column equality filter from spec."""
    fc = spec.get("filter_column")
    fv = spec.get("filter_value")
    if fc and fv is not None and fc in df.columns:
        df = df[df[fc].astype(str) == str(fv)]
    return df


def _validate_columns(df: pd.DataFrame, cols: list[str]) -> list[str]:
    """Return only columns that actually exist in the DataFrame."""
    return [c for c in cols if c in df.columns]


def _safe_agg(series: pd.Series, agg: str) -> float:
    """Apply an aggregation method safely, falling back to count."""
    agg_map = {
        "mean": "mean",
        "sum": "sum",
        "count": "count",
        "median": "median",
        "min": "min",
        "max": "max",
        "std": "std",
    }
    method = agg_map.get(agg, "mean")
    try:
        result = getattr(series, method)()
        return round(float(result), 2)
    except (TypeError, ValueError):
        return float(series.count())


# ---------------------------------------------------------------------------
# Chart-type compute functions
# ---------------------------------------------------------------------------

def _compute_bar_chart(spec: dict, df: pd.DataFrame) -> dict | None:
    x_col = spec.get("x_column", "")
    y_col = spec.get("y_column", "")
    agg = spec.get("aggregation", "mean")
    sort = spec.get("sort", "desc")
    top_n = spec.get("top_n")

    if x_col not in df.columns:
        return None

    df = _apply_filter(df, spec)

    if y_col and y_col in df.columns:
        grouped = df.groupby(x_col, sort=False)[y_col].agg(
            agg if agg != "count" else "count"
        )
    else:
        grouped = df.groupby(x_col, sort=False).size()

    if sort == "desc":
        grouped = grouped.sort_values(ascending=False)
    elif sort == "asc":
        grouped = grouped.sort_values(ascending=True)

    if top_n and isinstance(top_n, int) and top_n > 0:
        grouped = grouped.head(top_n)

    labels = [str(label) for label in grouped.index.tolist()]
    values = [round(float(v), 2) for v in grouped.values.tolist()]
    series_name = f"{agg}({y_col})" if y_col else f"count({x_col})"

    return {"labels": labels, "values": values, "series_name": series_name}


def _compute_line_chart(spec: dict, df: pd.DataFrame) -> dict | None:
    x_col = spec.get("x_column", "")
    y_col = spec.get("y_column", "")
    agg = spec.get("aggregation", "mean")
    top_n = spec.get("top_n")

    if x_col not in df.columns:
        return None

    df = _apply_filter(df, spec)

    if y_col and y_col in df.columns:
        grouped = df.groupby(x_col, sort=True)[y_col].agg(
            agg if agg != "count" else "count"
        )
    else:
        grouped = df.groupby(x_col, sort=True).size()

    grouped = grouped.sort_index()

    if top_n and isinstance(top_n, int) and top_n > 0:
        grouped = grouped.head(top_n)

    labels = [str(label) for label in grouped.index.tolist()]
    values = [round(float(v), 2) for v in grouped.values.tolist()]
    series_name = f"{agg}({y_col})" if y_col else f"count({x_col})"

    return {"labels": labels, "values": values, "series_name": series_name}


def _compute_scatter(spec: dict, df: pd.DataFrame) -> dict | None:
    x_col = spec.get("x_column", "")
    y_col = spec.get("y_column", "")
    sample_n = min(spec.get("sample_n", 50), 100)

    if x_col not in df.columns or y_col not in df.columns:
        return None

    df = _apply_filter(df, spec)
    subset = df[[x_col, y_col]].dropna()

    if len(subset) > sample_n:
        subset = subset.sample(n=sample_n, random_state=42)

    points = [
        {"x": round(float(row[x_col]), 2), "y": round(float(row[y_col]), 2)}
        for _, row in subset.iterrows()
    ]

    return {"points": points, "x_label": x_col, "y_label": y_col}


def _compute_stat_card(spec: dict, df: pd.DataFrame) -> dict | None:
    metrics_spec = spec.get("metrics", [])
    if not metrics_spec:
        return None

    df = _apply_filter(df, spec)

    stats: list[dict[str, str]] = []
    for m in metrics_spec:
        col = m.get("column", "")
        agg = m.get("aggregation", "mean")
        label = m.get("label", col)

        if col not in df.columns:
            continue

        value = _safe_agg(df[col], agg)
        if abs(value) >= 1_000:
            formatted = f"{value:,.0f}"
        elif abs(value) < 1:
            formatted = f"{value:.3f}"
        else:
            formatted = f"{value:.1f}"

        stats.append({"label": label, "value": formatted})

    return {"stats": stats} if stats else None


def _compute_heatmap(spec: dict, df: pd.DataFrame) -> dict | None:
    columns = _validate_columns(df, spec.get("columns", []))
    if len(columns) < 2:
        return None

    df = _apply_filter(df, spec)
    numeric_cols = [c for c in columns if pd.api.types.is_numeric_dtype(df[c])]
    if len(numeric_cols) < 2:
        return None

    corr = df[numeric_cols].corr().round(2)
    headers = numeric_cols
    rows = [[round(float(v), 2) for v in row] for row in corr.values.tolist()]

    return {"headers": headers, "rows": rows}


def _compute_table(spec: dict, df: pd.DataFrame) -> dict | None:
    columns = _validate_columns(df, spec.get("columns", []))
    sort_by = spec.get("sort_by")
    sort_order = spec.get("sort_order", "desc")
    head_n = min(spec.get("head_n", 10), 30)

    if not columns:
        columns = df.columns[:5].tolist()

    df = _apply_filter(df, spec)
    subset = df[columns]

    if sort_by and sort_by in subset.columns:
        subset = subset.sort_values(sort_by, ascending=(sort_order == "asc"))

    subset = subset.head(head_n)
    headers = columns
    rows = []
    for _, row in subset.iterrows():
        formatted_row: list[Any] = []
        for col in columns:
            v = row[col]
            if pd.isna(v):
                formatted_row.append("N/A")
            elif isinstance(v, float):
                formatted_row.append(round(v, 2))
            else:
                formatted_row.append(v)
        rows.append(formatted_row)

    return {"headers": headers, "rows": rows}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

_COMPUTE_FNS = {
    "bar_chart": _compute_bar_chart,
    "line_chart": _compute_line_chart,
    "scatter": _compute_scatter,
    "stat_card": _compute_stat_card,
    "heatmap": _compute_heatmap,
    "table": _compute_table,
}


def compute_chart_data(chart_spec: dict) -> dict | None:
    """Given a lightweight chart spec from the LLM, compute real data.

    Args:
        chart_spec: Dict with ``visual_type`` plus a ``spec`` sub-dict
            describing columns, aggregation, etc.

    Returns:
        Data payload ready to be used as ``VisualSpec.data``, or *None*
        on failure.
    """
    try:
        df = load_dataframe()
    except Exception as exc:
        logger.warning("Failed to load dataframe: %s", exc)
        return None

    visual_type = chart_spec.get("visual_type", "")
    spec = chart_spec.get("spec", {})
    if not spec:
        spec = chart_spec

    compute_fn = _COMPUTE_FNS.get(visual_type)
    if not compute_fn:
        logger.warning("Unknown chart type: %s", visual_type)
        return None

    try:
        return compute_fn(spec, df)
    except Exception as exc:
        logger.warning("Chart computation failed for %s: %s", visual_type, exc)
        return None
