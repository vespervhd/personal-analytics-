"""Data cleaning engine.

Every operation takes a DataFrame, works on a **copy**, and returns
``(new_dataframe, report)``. The input is never mutated, and the report is
a plain dict the UI shows as a preview before the user applies anything.
Reports always describe exactly what changed, so data is never discarded
silently.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from utils.logger import get_logger

log = get_logger("data_cleaner")


class DataCleaningError(ValueError):
    """Raised when a cleaning operation cannot be applied as requested."""


def _report(operation: str, **details) -> dict:
    report = {"operation": operation}
    report.update(details)
    return report


def missing_value_report(df: pd.DataFrame) -> dict:
    """Per-column missing counts and percentages, plus the dataset total."""
    missing = df.isna().sum()
    total_cells = max(int(df.size), 1)
    return {
        "operation": "missing_value_report",
        "columns": {
            str(col): {
                "missing": int(missing[col]),
                "percent": round(float(missing[col]) / max(len(df), 1) * 100, 2),
            }
            for col in df.columns
        },
        "total_missing": int(missing.sum()),
        "total_percent": round(float(missing.sum()) / total_cells * 100, 2),
    }


def drop_missing(
    df: pd.DataFrame, columns: list[str] | None = None, how: str = "any"
) -> tuple[pd.DataFrame, dict]:
    """Drop rows with missing values (``how``: ``"any"`` or ``"all"``)."""
    if how not in ("any", "all"):
        raise DataCleaningError("how must be 'any' or 'all'.")
    subset = columns if columns else None
    if subset:
        unknown = [c for c in subset if c not in df.columns]
        if unknown:
            raise DataCleaningError(f"Unknown columns: {unknown}")
    before = len(df)
    cleaned = df.dropna(subset=subset, how=how).copy()
    removed = before - len(cleaned)
    log.info("drop_missing removed {} of {} rows", removed, before)
    return cleaned, _report(
        "drop_missing", columns=subset, how=how, rows_before=before,
        rows_after=len(cleaned), rows_removed=removed,
    )


def fill_missing(
    df: pd.DataFrame, strategy: str | dict[str, object] = "median"
) -> tuple[pd.DataFrame, dict]:
    """Fill missing values.

    ``strategy`` is either one rule applied per column type (``"mean"``,
    ``"median"``, ``"mode"``) or an explicit ``{column: value}`` mapping.
    Columns that cannot be filled by the chosen rule (e.g. mean of text)
    are left untouched and listed in the report — never guessed.
    """
    filled = df.copy()
    filled_counts: dict[str, int] = {}
    skipped: list[str] = []
    if isinstance(strategy, dict):
        for column, value in strategy.items():
            if column not in df.columns:
                raise DataCleaningError(f"Unknown column: {column}")
            missing = int(df[column].isna().sum())
            if missing:
                filled[column] = filled[column].fillna(value)
                filled_counts[column] = missing
    else:
        if strategy not in ("mean", "median", "mode"):
            raise DataCleaningError("strategy must be 'mean', 'median', 'mode', or a mapping.")
        for column in df.columns:
            missing = int(df[column].isna().sum())
            if not missing:
                continue
            series = df[column]
            # Mean/median are numeric-only rules: a text column cannot be
            # filled by them, so it is skipped (never silently mode-filled).
            if strategy in ("mean", "median") and not pd.api.types.is_numeric_dtype(series):
                skipped.append(column)
                continue
            try:
                if strategy == "mean":
                    value = series.mean()
                elif strategy == "median":
                    value = series.median()
                else:
                    modes = series.mode(dropna=True)
                    value = modes.iloc[0] if len(modes) else None
            except (TypeError, ValueError):
                value = None
            if value is None or (isinstance(value, float) and np.isnan(value)):
                skipped.append(column)
                continue
            filled[column] = filled[column].fillna(value)
            filled_counts[column] = missing
    log.info("fill_missing filled {} columns, skipped {}", len(filled_counts), skipped)
    return filled, _report(
        "fill_missing", strategy=strategy, filled=filled_counts, skipped=skipped
    )


def drop_duplicates(
    df: pd.DataFrame, subset: list[str] | None = None
) -> tuple[pd.DataFrame, dict]:
    """Drop duplicate rows, keeping the first occurrence."""
    if subset:
        unknown = [c for c in subset if c not in df.columns]
        if unknown:
            raise DataCleaningError(f"Unknown columns: {unknown}")
    before = len(df)
    cleaned = df.drop_duplicates(subset=subset, keep="first").copy()
    removed = before - len(cleaned)
    log.info("drop_duplicates removed {} of {} rows", removed, before)
    return cleaned, _report(
        "drop_duplicates", subset=subset, rows_before=before,
        rows_after=len(cleaned), rows_removed=removed,
    )


def convert_dtype(
    df: pd.DataFrame, conversions: dict[str, str]
) -> tuple[pd.DataFrame, dict]:
    """Convert column dtypes (``{"age": "int64"}``). All-or-nothing.

    If any conversion fails, the original DataFrame is returned untouched
    and the error names every failing column — partial conversion never
    happens silently.
    """
    unknown = [c for c in conversions if c not in df.columns]
    if unknown:
        raise DataCleaningError(f"Unknown columns: {unknown}")
    converted = df.copy()
    failures: dict[str, str] = {}
    for column, dtype in conversions.items():
        try:
            converted[column] = converted[column].astype(dtype)
        except (ValueError, TypeError) as exc:
            failures[column] = str(exc)
    if failures:
        raise DataCleaningError(
            "Could not convert columns (original data unchanged): "
            + "; ".join(f"{col}: {msg}" for col, msg in failures.items())
        )
    log.info("convert_dtype converted {}", list(conversions))
    return converted, _report("convert_dtype", conversions=conversions)


def flag_outliers_iqr(
    df: pd.DataFrame, columns: list[str] | None = None
) -> tuple[pd.DataFrame, dict]:
    """Flag outliers with the IQR rule (outside Q1 - 1.5*IQR, Q3 + 1.5*IQR).

    Returns a boolean mask DataFrame (same index, one column per numeric
    column analysed) plus per-column bounds and counts. Nothing is removed
    here — removal is the user's explicit decision in the UI.
    """
    numeric = df.select_dtypes(include="number")
    targets = columns if columns else list(numeric.columns)
    unknown = [c for c in targets if c not in df.columns]
    if unknown:
        raise DataCleaningError(f"Unknown columns: {unknown}")
    non_numeric = [c for c in targets if c not in numeric.columns]
    if non_numeric:
        raise DataCleaningError(f"IQR outlier detection needs numeric columns: {non_numeric}")
    flags = pd.DataFrame(False, index=df.index, columns=targets)
    details: dict[str, dict] = {}
    for column in targets:
        series = df[column].dropna()
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        mask = (df[column] < lower) | (df[column] > upper)
        flags[column] = mask.fillna(False)
        details[column] = {
            "lower": float(lower),
            "upper": float(upper),
            "outliers": int(mask.sum()),
        }
    log.info("flag_outliers_iqr analysed {}", targets)
    return flags, _report("flag_outliers_iqr", columns=details)


def rename_columns(
    df: pd.DataFrame, mapping: dict[str, str]
) -> tuple[pd.DataFrame, dict]:
    """Rename columns; unknown sources and duplicate targets are rejected."""
    unknown = [c for c in mapping if c not in df.columns]
    if unknown:
        raise DataCleaningError(f"Unknown columns: {unknown}")
    targets = list(mapping.values())
    if len(set(targets)) != len(targets):
        raise DataCleaningError("Rename targets must be unique.")
    clashes = [t for t in targets if t in df.columns and t not in mapping]
    if clashes:
        raise DataCleaningError(f"Rename targets already exist as columns: {clashes}")
    renamed = df.rename(columns=mapping).copy()
    log.info("rename_columns renamed {}", mapping)
    return renamed, _report("rename_columns", mapping=mapping)


def filter_rows(df: pd.DataFrame, query: str) -> tuple[pd.DataFrame, dict]:
    """Filter rows with a pandas query expression (e.g. ``"age > 30"``)."""
    if not query or not query.strip():
        raise DataCleaningError("Filter expression must not be empty.")
    try:
        filtered = df.query(query).copy()
    except Exception as exc:
        raise DataCleaningError(f"Invalid filter expression {query!r}: {exc}") from exc
    before = len(df)
    log.info("filter_rows kept {} of {} rows for {}", len(filtered), before, query)
    return filtered, _report(
        "filter_rows", query=query, rows_before=before,
        rows_after=len(filtered), rows_removed=before - len(filtered),
    )
