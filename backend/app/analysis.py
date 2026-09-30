"""Small, validated analysis path using the session's actual dataset."""
from __future__ import annotations

import hashlib
import json
import logging
import math
from pathlib import Path
from typing import Sequence

import pandas as pd
from pydantic import ValidationError

from app.chart_compute import clear_cache, load_dataframe
from app.models import AnalysisFilter, AnalysisResult, AnalysisSpec, PublicTurn, VisualSpec

logger = logging.getLogger(__name__)
_dataset_versions: dict[str, str] = {}
OPERATIONS = {"pearson_correlation", "scatter", "grouped_comparison", "table", "summary", "dataset_overview"}
AGGREGATIONS = {"mean", "median", "min", "max", "sum", "count", "std"}
ALTERNATIVE = (
    "Supported alternatives are a scatterplot/Pearson correlation between two numeric columns, "
    "a grouped comparison, a table of named columns, or summary statistics. "
    "No alternative was executed."
)


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    values = pd.to_numeric(frame[column], errors="coerce")
    return values.where(values.map(lambda v: pd.notna(v) and math.isfinite(v)))


def _pearson(frame: pd.DataFrame, x: str, y: str) -> float | None:
    if len(frame) < 2 or frame[x].nunique() < 2 or frame[y].nunique() < 2:
        return None
    value = float(frame[x].corr(frame[y]))
    return value if math.isfinite(value) else None


def _aggregate(values: pd.Series, operation: str) -> float | None:
    value = float(getattr(values, operation)())
    return value if math.isfinite(value) else None


def compute_analysis(request: dict, dataset_path: str | Path | None,
                     history: Sequence[PublicTurn] = (),
                     pending_results: Sequence[AnalysisResult] = ()) -> AnalysisResult:
    """Reuse only an exact spec on identical dataset contents; never substitute columns."""
    spec = None
    try:
        spec = AnalysisSpec.model_validate(request)
        if spec.operation not in OPERATIONS:
            raise ValueError(f"Operation '{spec.operation}' is not supported. {ALTERNATIVE}")
        if spec.aggregation not in AGGREGATIONS:
            raise ValueError(f"Aggregation '{spec.aggregation}' is not supported. {ALTERNATIVE}")
        if spec.grouping == "quartiles" and spec.operation != "grouped_comparison":
            raise ValueError("Quartiles are supported for grouped comparisons only; no alternative was executed.")
        if len(spec.columns) != len(set(spec.columns)):
            raise ValueError("Choose each column only once.")
        if spec.operation in {"pearson_correlation", "scatter", "grouped_comparison"} and spec.columns:
            raise ValueError("Use x_column/y_column for this operation; a multi-column analysis was not performed.")
        if spec.operation in {"pearson_correlation", "scatter"} and spec.aggregation != "mean":
            raise ValueError("Aggregated scatterplots/correlations are not supported. Use a grouped comparison instead; it was not executed.")
        if spec.operation in {"table", "summary"} and spec.columns and (spec.x_column or spec.y_column):
            raise ValueError("Use either columns or x_column/y_column, so no requested column is ignored.")
        if dataset_path is None:
            raise ValueError("The session has no dataset file.")
        version = hashlib.sha256(Path(dataset_path).read_bytes()).hexdigest()
        for previous in reversed(pending_results):
            if (previous.status == "completed" and previous.spec == spec
                    and previous.dataset_version == version):
                return previous.model_copy(update={"reused": True})
        for turn in reversed(history):
            for previous in [turn.analysis, *turn.additional_analyses]:
                if (previous and previous.status == "completed" and previous.spec == spec
                        and previous.dataset_version == version):
                    return previous.model_copy(update={"reused": True, "request": request})
        # A content change must invalidate both computation and result reuse.
        dataset_key = str(dataset_path)
        if _dataset_versions.get(dataset_key) != version:
            clear_cache(dataset_path)
            _dataset_versions[dataset_key] = version
        frame = load_dataframe(dataset_path)
        referenced = [c for c in (spec.x_column, spec.y_column, spec.group_by) if c]
        referenced += [*spec.columns, *spec.filters]
        missing = sorted(set(referenced) - set(frame.columns))
        if missing:
            raise ValueError(f"Unknown dataset columns: {', '.join(missing)}. Choose existing columns; no replacement was made.")
        quartiles = None
        quartile_edges = None
        for column, value in spec.filters.items():
            if isinstance(value, AnalysisFilter) and value.operator != "eq":
                if isinstance(value.value, (str, bool)) or not math.isfinite(value.value):
                    raise ValueError("Comparison filters need a finite numeric threshold.")
                numeric = _numeric(frame, column)
                if numeric.notna().sum() == 0:
                    raise ValueError(f"Comparison filter column '{column}' has no finite numeric values.")
                compare = {"gt": numeric.gt, "gte": numeric.ge, "lt": numeric.lt, "lte": numeric.le}
                frame = frame[compare[value.operator](value.value).fillna(False)]
            else:
                if (isinstance(value, str) and value.lstrip().startswith((">", "<"))
                        and pd.api.types.is_numeric_dtype(frame[column])):
                    raise ValueError("The numeric comparison filter is invalid. Use operator gt/gte/lt/lte with a numeric value; no alternative was executed.")
                frame = frame[frame[column] == (value.value if isinstance(value, AnalysisFilter) else value)]
        if frame.empty:
            raise ValueError("No rows remain after filtering.")
        if spec.grouping == "quartiles":
            group_column = spec.group_by or spec.x_column
            if not group_column:
                raise ValueError("Quartiles need an explicit numeric grouping column.")
            try:
                quartiles, edges = pd.qcut(_numeric(frame, group_column), 4,
                                          labels=["Q1 (lowest)", "Q2", "Q3", "Q4 (highest)"], retbins=True)
                quartile_edges = [float(edge) for edge in edges]
            except ValueError:
                raise ValueError("Four distinct quartiles cannot be formed from this grouping column; no alternative was executed.") from None
        values, groups, pearson = {}, [], None
        if spec.operation == "dataset_overview":
            if spec.x_column or spec.y_column or spec.group_by:
                raise ValueError("Dataset overview uses named columns, not x/y/grouping.")
            columns = spec.columns or list(frame.columns)
            values = {"row_count": len(frame), "column_count": len(columns),
                      "missing_cells": int(frame[columns].isna().sum().sum())}
            chart = {"headers": ["Column", "Type", "Available", "Missing"],
                     "rows": [[c, str(frame[c].dtype), int(frame[c].count()), int(frame[c].isna().sum())]
                              for c in columns]}
        elif spec.operation in {"pearson_correlation", "scatter"}:
            if not spec.x_column or not spec.y_column or spec.x_column == spec.y_column:
                raise ValueError("Choose two distinct numeric columns for this analysis.")
            frame = frame.copy()
            for column in (spec.x_column, spec.y_column):
                frame[column] = _numeric(frame, column)
            frame = frame.dropna(subset=[spec.x_column, spec.y_column])
            if frame.empty:
                raise ValueError("No finite numeric pairs remain after filtering.")
            if spec.operation == "pearson_correlation":
                pearson = _pearson(frame, spec.x_column, spec.y_column)
            if spec.group_by:
                for label, subset in frame.groupby(spec.group_by, dropna=False, sort=False):
                    groups.append({"group": None if pd.isna(label) else str(label),
                                   "sample_size": len(subset),
                                   "pearson_r": _pearson(subset, spec.x_column, spec.y_column)
                                   if spec.operation == "pearson_correlation" else None})
            plotted = frame.sample(n=500, random_state=42) if len(frame) > 500 else frame
            points = []
            point_columns = list(dict.fromkeys([spec.x_column, spec.y_column, *([spec.group_by] if spec.group_by else [])]))
            for row in plotted[point_columns].to_dict(orient="records"):
                point = {"x": float(row[spec.x_column]), "y": float(row[spec.y_column])}
                if spec.group_by:
                    point["group"] = None if pd.isna(row[spec.group_by]) else str(row[spec.group_by])
                points.append(point)
            chart = {"x_label": spec.x_column, "y_label": spec.y_column, "points": points,
                     "plotted_count": len(points)}
        elif spec.operation == "grouped_comparison":
            group_column = spec.group_by or spec.x_column
            if not group_column or (not spec.y_column and spec.aggregation != "count"):
                raise ValueError("A grouped comparison needs a grouping column and a numeric y_column (or aggregation=count to count rows).")
            if spec.x_column and spec.group_by and spec.x_column != spec.group_by:
                raise ValueError("Use one grouping column for a grouped comparison. No alternative was executed.")
            if quartiles is None and frame[group_column].nunique() > 20:
                raise ValueError("This grouping column has too many distinct values for a category comparison. Request grouping=quartiles or a scatterplot instead; neither alternative was executed.")
            frame = frame.copy()
            if spec.aggregation != "count":
                frame[spec.y_column] = _numeric(frame, spec.y_column)
                frame = frame.dropna(subset=[spec.y_column])
            if frame.empty:
                raise ValueError("The selected column has no finite numeric values.")
            grouper = quartiles.loc[frame.index] if quartiles is not None else group_column
            if quartiles is not None:
                frame = frame.loc[quartiles.loc[frame.index].notna()]
                grouper = quartiles.loc[frame.index]
                values["quartile_edges"] = quartile_edges
                if frame.empty:
                    raise ValueError("No rows with a valid quartile remain after filtering.")
            for label, subset in frame.groupby(grouper, dropna=False, sort=quartiles is not None, observed=True):
                groups.append({"group": None if pd.isna(label) else str(label),
                               "sample_size": int(subset[spec.y_column].count()) if spec.y_column else len(subset),
                               "value": _aggregate(subset[spec.y_column], spec.aggregation)
                               if spec.y_column else float(len(subset))})
            chart = {"labels": ["(missing)" if g["group"] is None else g["group"] for g in groups],
                     "values": [g["value"] for g in groups],
                     "series_name": f"{spec.aggregation}({spec.y_column or 'rows'})"}
            # The existing bar renderer converts null into zero; use a table when undefined.
            if any(g["value"] is None for g in groups):
                chart = {"headers": [group_column, "sample_size", chart["series_name"]],
                         "rows": [[g["group"], g["sample_size"], "undefined" if g["value"] is None else g["value"]]
                                  for g in groups]}
        else:
            if spec.group_by:
                raise ValueError(f"Grouping is not supported for '{spec.operation}'. Use a grouped comparison instead; it was not executed.")
            columns = spec.columns or list(dict.fromkeys(c for c in (spec.x_column, spec.y_column) if c))
            if not columns:
                raise ValueError("Name the dataset columns to include; none were selected automatically.")
            if spec.operation == "table":
                rows = json.loads(frame[columns].head(spec.limit).to_json(orient="values", date_format="iso", double_precision=15))
                chart = {"headers": columns, "rows": rows}
            else:
                for column in columns:
                    numeric = (frame[column] if spec.aggregation == "count" else _numeric(frame, column)).dropna()
                    if numeric.empty and spec.aggregation != "count":
                        raise ValueError(f"Column '{column}' has no finite numeric values.")
                    values[column] = {"sample_size": len(numeric), "value": _aggregate(numeric, spec.aggregation)}
                chart = {"stats": [{"label": f"{spec.aggregation}({c}); n={v['sample_size']}",
                                    "value": "undefined" if v["value"] is None else v["value"]}
                                   for c, v in values.items()]}
        return AnalysisResult(status="completed", spec=spec, sample_size=len(frame), pearson_r=pearson,
                              groups=groups, values=values, chart_data=chart, dataset_version=version, request=request)
    except ValidationError as exc:
        logger.warning("Invalid analysis spec: %s", exc)
        return AnalysisResult(status="not_performed", request=request, error=f"The analysis request has invalid or missing fields. {ALTERNATIVE}")
    except (ValueError, TypeError) as exc:
        return AnalysisResult(status="not_performed", spec=spec, request=request, error=str(exc))
    except (OSError, ImportError) as exc:
        logger.warning("Dataset unavailable for analysis: %s", exc)
        return AnalysisResult(status="not_performed", spec=spec, request=request, error="The session dataset could not be read; no analysis was performed.")


def analysis_report(result: AnalysisResult) -> str:
    if result.status != "completed":
        return f"Analysis was not performed: {result.error}"
    spec = result.spec
    prefix = "Existing result reused. " if result.reused else ""
    if spec.operation == "dataset_overview":
        return (f"{prefix}Dataset overview: {result.values['row_count']} rows, "
                f"{result.values['column_count']} columns, {result.values['missing_cells']} missing cells.")
    if spec.operation == "pearson_correlation":
        coefficient = "undefined (insufficient observations or variation)" if result.pearson_r is None else f"{result.pearson_r:.6f}"
        report = f"{prefix}{spec.x_column} vs {spec.y_column}: n={result.sample_size}; Pearson r={coefficient}."
        if not result.reused:
            for group in result.groups:
                r = "undefined" if group["pearson_r"] is None else f"{group['pearson_r']:.6f}"
                report += f" {spec.group_by}={group['group']}: n={group['sample_size']}; r={r}."
        return report
    if spec.operation == "scatter":
        return f"{prefix}{spec.x_column} vs {spec.y_column}: {len(result.chart_data['points'])} of {result.sample_size} finite pairs plotted; no correlation was calculated."
    if spec.operation == "grouped_comparison":
        return prefix + f"{spec.aggregation}({spec.y_column or 'rows'}) by {spec.group_by or spec.x_column}: " + "; ".join(
            f"{g['group']}={'undefined' if g['value'] is None else format(g['value'], '.6g')} (n={g['sample_size']})" for g in result.groups) + "."
    if spec.operation == "summary":
        return prefix + "; ".join(f"{spec.aggregation}({c})={'undefined' if v['value'] is None else format(v['value'], '.6g')} (n={v['sample_size']})"
                                  for c, v in result.values.items()) + "."
    return f"{prefix}Table of {', '.join(result.chart_data['headers'])}: showing {len(result.chart_data['rows'])} of {result.sample_size} filtered rows."


def analysis_visual(result: AnalysisResult) -> VisualSpec | None:
    if result.status != "completed" or result.chart_data is None:
        return None
    spec = result.spec
    visual_type = {"pearson_correlation": "scatter", "scatter": "scatter", "grouped_comparison": "bar_chart",
                   "table": "table", "summary": "stat_card", "dataset_overview": "table"}[spec.operation]
    if "headers" in result.chart_data:
        visual_type = "table"
    title = ("Dataset overview" if spec.operation == "dataset_overview" else
             f"{spec.x_column} vs {spec.y_column}" if visual_type == "scatter" else
             f"{spec.aggregation}({spec.y_column or 'rows'}) by {spec.group_by or spec.x_column}" if spec.operation == "grouped_comparison" else
             f"{spec.operation}: {', '.join(result.chart_data.get('headers', result.values.keys()))}")
    description = analysis_report(result)
    if visual_type == "scatter" and len(result.chart_data["points"]) < result.sample_size and spec.operation == "pearson_correlation":
        description += f" Displaying a sample of {len(result.chart_data['points'])} points; coefficients use all finite pairs."
    return VisualSpec(visual_type=visual_type, title=title, data=result.chart_data, description=description)


def verified_message(result: AnalysisResult) -> str:
    if result.status != "completed":
        return analysis_report(result)
    # Computed contributions are concise facts, not unchecked model interpretations.
    spec = result.spec
    prefix = "Existing result reused. " if result.reused else ""
    if spec.operation == "dataset_overview":
        return analysis_report(result) + " Column details are in the dashboard table."
    if spec.operation == "pearson_correlation":
        if result.pearson_r is None:
            finding = "No interpretable correlation estimate is available"
        elif result.sample_size < 3:
            finding = "Too few observations to establish a reliable relationship"
        else:
            r = result.pearson_r
            strength = "negligible" if abs(r) < .1 else "weak" if abs(r) < .3 else "moderate" if abs(r) < .7 else "strong"
            finding = f"A {strength} {'negative' if r < 0 else 'positive'} correlation"
        return f"{prefix}{spec.x_column} vs {spec.y_column}: {finding}. See the visualization for coefficients and sample sizes; correlation does not establish causation."
    if spec.operation == "grouped_comparison":
        grouping = f"quartiles of {spec.group_by or spec.x_column}" if spec.grouping == "quartiles" else spec.group_by or spec.x_column
        return f"{prefix}Compared {spec.aggregation}({spec.y_column or 'rows'}) across {len(result.groups)} groups of {grouping}. See the chart for group values and sample sizes."
    if spec.operation == "summary":
        return f"{prefix}Calculated {spec.aggregation} for {', '.join(result.values)}. The values and sample sizes are in the visualization."
    if spec.operation == "scatter":
        return f"{prefix}Plotted {spec.x_column} against {spec.y_column}. See the chart; no correlation was calculated."
    return f"{prefix}Prepared the requested table of {', '.join(result.chart_data['headers'])}. See the dashboard for the rows."


def compute_requested_analyses(request: dict, dataset_path: str | Path | None,
                               history: Sequence[PublicTurn]) -> list[AnalysisResult]:
    requests = request.get("analyses")
    if requests is None:
        return [compute_analysis({k: v for k, v in request.items() if k != "redisplay"}, dataset_path, history)]
    if set(request) - {"analyses", "redisplay"}:
        return [AnalysisResult(status="not_performed", request=request,
                               error="Combined requests accept only analyses and redisplay. Put filters and other analysis fields inside each spec; no analysis was performed.")]
    if (not isinstance(requests, list) or not 1 <= len(requests) <= 3
            or any(not isinstance(item, dict) or item.get("operation") not in
                   {"pearson_correlation", "grouped_comparison", "summary"} for item in requests)):
        return [AnalysisResult(status="not_performed", request=request,
                               error="A combined request supports up to three correlations, grouped comparisons, or summaries. No alternative was executed.")]
    results = []
    for item in requests:
        results.append(compute_analysis(item, dataset_path, history, results))
    return results


def combined_analysis_visual(results: list[AnalysisResult]) -> VisualSpec | None:
    if any(r.status == "completed" and r.spec.operation != "pearson_correlation" for r in results):
        rows = []
        for result in results:
            if result.status != "completed":
                continue
            spec = result.spec
            if spec.operation == "grouped_comparison":
                rows.extend([[f"{spec.aggregation}({spec.y_column or 'rows'})", spec.group_by or spec.x_column,
                              g["group"], g["sample_size"], "undefined" if g["value"] is None else g["value"]]
                             for g in result.groups])
            elif spec.operation == "summary":
                rows.extend([[f"{spec.aggregation}({c})", "All rows", "All rows", v["sample_size"],
                              "undefined" if v["value"] is None else v["value"]] for c, v in result.values.items()])
            else:
                rows.append([f"Pearson({spec.x_column}, {spec.y_column})", "All rows", "All rows",
                             result.sample_size, "undefined" if result.pearson_r is None else result.pearson_r])
                rows.extend([[f"Pearson({spec.x_column}, {spec.y_column})", spec.group_by, g["group"],
                              g["sample_size"], "undefined" if g["pearson_r"] is None else g["pearson_r"]]
                             for g in result.groups])
        return VisualSpec(visual_type="table", title="Computed comparisons",
                          data={"headers": ["Measure", "Grouping", "Group", "n", "Value"], "rows": rows},
                          description="Separate backend computations; sample sizes refer to each individual group.")
    rows = []
    for result in results:
        if result.status != "completed":
            continue
        spec = result.spec
        rows.append([spec.x_column, spec.y_column, "All rows", result.sample_size,
                     "undefined" if result.pearson_r is None else result.pearson_r])
        for group in result.groups:
            rows.append([spec.x_column, spec.y_column, f"{spec.group_by}={group['group']}",
                         group["sample_size"], "undefined" if group["pearson_r"] is None else group["pearson_r"]])
    if not rows:
        return None
    return VisualSpec(visual_type="table", title="Computed Pearson correlations",
                      data={"headers": ["X", "Y", "Group", "n", "Pearson r"], "rows": rows},
                      description="Separate pairwise correlations; no regression or causal analysis was performed.")
