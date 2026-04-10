"""Dataset upload parsing and summary generation."""

from __future__ import annotations

import io
from typing import Any

import pandas as pd


def parse_dataset(file_bytes: bytes, filename: str) -> dict[str, Any]:
    """Parse CSV or Excel bytes into a structured dataset summary."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "csv":
        df = pd.read_csv(io.BytesIO(file_bytes))
    elif ext in ("xlsx", "xls"):
        df = pd.read_excel(io.BytesIO(file_bytes))
    else:
        raise ValueError(f"Unsupported file type: .{ext}. Use CSV or Excel.")

    columns_info = []
    for col in df.columns:
        null_count = int(df[col].isnull().sum())
        columns_info.append({
            "name": str(col),
            "dtype": str(df[col].dtype),
            "null_count": null_count,
            "null_pct": round(null_count / len(df) * 100, 1) if len(df) > 0 else 0.0,
        })

    sample_rows = df.head(500).fillna("NULL").to_dict(orient="records")

    numeric_stats: dict[str, Any] = {}
    numeric_df = df.select_dtypes(include="number")
    if not numeric_df.empty:
        numeric_stats = numeric_df.describe().round(2).to_dict()

    return {
        "filename": filename,
        "shape": [len(df), len(df.columns)],
        "columns": columns_info,
        "sample_rows": sample_rows,
        "numeric_stats": numeric_stats,
    }


def build_dataset_summary_text(parsed: dict[str, Any]) -> str:
    """Convert parsed dataset info into a text block for LLM system prompts."""
    lines = [
        f"DATASET: {parsed['filename']}",
        f"Shape: {parsed['shape'][0]} rows x {parsed['shape'][1]} columns",
        "",
        "COLUMNS:",
    ]
    for col in parsed["columns"]:
        null_info = f" ({col['null_count']} nulls, {col['null_pct']}%)" if col["null_count"] > 0 else ""
        lines.append(f"  - {col['name']} [{col['dtype']}]{null_info}")

    lines.append("")
    lines.append("SAMPLE ROWS (first 5):")
    for i, row in enumerate(parsed["sample_rows"][:5]):
        row_str = ", ".join(f"{k}={v}" for k, v in row.items())
        lines.append(f"  Row {i + 1}: {row_str}")

    if parsed.get("numeric_stats"):
        lines.append("")
        lines.append("NUMERIC COLUMN STATISTICS:")
        for col_name, stats in parsed["numeric_stats"].items():
            stat_parts = [f"{k}={v}" for k, v in stats.items()]
            lines.append(f"  {col_name}: {', '.join(stat_parts)}")

    return "\n".join(lines)
