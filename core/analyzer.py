"""Dataset-level EDA orchestration and insight generation.

:func:`eda_report` bundles everything the Statistical Analysis page and
the report generator need. :func:`key_insights` derives its sentences from
the computed numbers (thresholds documented below) — it never invents
findings the data does not support.
"""

from __future__ import annotations

import pandas as pd

from core.data_cleaner import missing_value_report
from core.statistics import column_summary, correlation_matrix
from utils.logger import get_logger

log = get_logger("analyzer")

#: Thresholds used by key_insights (documented, not magic).
MISSING_WARN_PCT = 20.0
STRONG_CORR = 0.7
HIGH_SKEW = 1.0


def dataset_overview(df: pd.DataFrame) -> dict:
    """Rows, columns, dtypes, memory, duplicates, and missing totals."""
    return {
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "column_names": list(df.columns),
        "dtypes": {str(col): str(dtype) for col, dtype in df.dtypes.items()},
        "memory_mb": round(float(df.memory_usage(deep=True).sum()) / 1024 / 1024, 3),
        "duplicate_rows": int(df.duplicated().sum()),
        "total_missing": int(df.isna().sum().sum()),
    }


def eda_report(df: pd.DataFrame) -> dict:
    """Full EDA bundle: overview, missing stats, column summaries, correlation."""
    overview = dataset_overview(df)
    missing = missing_value_report(df)
    summaries = column_summary(df)
    numeric = df.select_dtypes(include="number")
    correlation = None
    if len(numeric.columns) >= 2:
        corr = correlation_matrix(df)
        correlation = {
            str(row): {str(col): (None if pd.isna(val) else round(float(val), 4))
                       for col, val in corr.loc[row].items()}
            for row in corr.index
        }
    report = {
        "overview": overview,
        "missing": missing,
        "columns": summaries,
        "correlation": correlation,
    }
    log.info("eda_report built for {} rows x {} columns", len(df), len(df.columns))
    return report


def key_insights(df: pd.DataFrame, report: dict | None = None) -> list[str]:
    """Generate insight sentences from the actual EDA numbers.

    Rules: missing > 20% in a column; |correlation| >= 0.7 between two
    columns; |skew| >= 1.0 in a numeric column; duplicate rows present.
    Returns an honest fallback sentence when nothing stands out.
    """
    report = report or eda_report(df)
    insights: list[str] = []

    for column, info in report["missing"]["columns"].items():
        if info["percent"] >= MISSING_WARN_PCT:
            insights.append(
                f"Column '{column}' is missing {info['percent']}% of its values "
                f"({info['missing']} cells) — consider filling or dropping it."
            )

    duplicates = report["overview"]["duplicate_rows"]
    if duplicates:
        insights.append(f"There are {duplicates} duplicate row(s) in the dataset.")

    for column, summary in report["columns"].items():
        if summary["type"] == "numeric" and summary.get("skew") is not None:
            if abs(summary["skew"]) >= HIGH_SKEW:
                insights.append(
                    f"Column '{column}' is strongly skewed (skew={summary['skew']:.2f}); "
                    "its mean and median differ, so prefer the median."
                )

    correlation = report.get("correlation")
    if correlation:
        best: tuple[str, str, float] | None = None
        columns = list(correlation)
        for i, col_a in enumerate(columns):
            for col_b in columns[i + 1:]:
                value = correlation[col_a][col_b]
                if value is None:
                    continue
                if best is None or abs(value) > abs(best[2]):
                    best = (col_a, col_b, value)
        if best is not None and abs(best[2]) >= STRONG_CORR:
            insights.append(
                f"Strongest correlation: '{best[0]}' vs '{best[1]}' (r={best[2]:.2f})."
            )

    if not insights:
        insights.append(
            "No strong patterns stood out: missing values are low, no heavy "
            "skew, and no strong correlations were found."
        )
    return insights
