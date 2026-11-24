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


def _fmt_num(value: float) -> str:
    """Format a number with thousands separators, no decimals when integral."""
    number = float(value)
    if number == int(number):
        return f"{int(number):,}"
    return f"{number:,.2f}"


def _detect_date_column(df: pd.DataFrame) -> str | None:
    """First column holding dates (datetime dtype, or mostly parseable text)."""
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            return str(col)
        if pd.api.types.is_numeric_dtype(df[col]):
            continue
        parsed = pd.to_datetime(df[col], errors="coerce")
        if len(parsed) and parsed.notna().mean() >= 0.8:
            return str(col)
    return None


def _detect_category_column(df: pd.DataFrame, exclude: set[str]) -> str | None:
    """First text column with a handful of distinct values (2..50)."""
    for col in df.columns:
        if str(col) in exclude:
            continue
        if not pd.api.types.is_string_dtype(df[col]):
            continue
        if 2 <= df[col].nunique(dropna=True) <= 50:
            return str(col)
    return None


def business_summary(
    df: pd.DataFrame,
    lang: str = "fa",
    value_column: str | None = None,
    category_column: str | None = None,
    date_column: str | None = None,
) -> list[str]:
    """Plain-language business summary from the actual numbers.

    Sentences, each derived from the data (never invented): the top
    category by total value, the best and weakest period when a date
    column exists, the trend (second-half vs first-half mean), and the
    largest single value with its category and date. Columns are
    auto-detected when not given: the value is the last numeric column,
    the category the first low-cardinality text column, the date the
    first parseable date column. Returns an honest fallback sentence
    when no numeric column exists.
    """
    from ui.i18n import t

    numeric = [str(c) for c in df.select_dtypes(include="number").columns]
    value = value_column if value_column in numeric else (numeric[-1] if numeric else None)
    if value is None or len(df) == 0:
        return [t("business_none", lang=lang)]

    date = None
    if date_column is not None and date_column in df.columns:
        parsed = pd.to_datetime(df[date_column], errors="coerce")
        if len(parsed) and parsed.notna().mean() >= 0.8:
            date = str(date_column)
    if date is None:
        date = _detect_date_column(df)

    category = None
    if category_column is not None and category_column in df.columns:
        if 2 <= df[category_column].nunique(dropna=True) <= 50:
            category = str(category_column)
    if category is None:
        category = _detect_category_column(df, {value, date} if date else {value})

    sentences: list[str] = []
    values = pd.to_numeric(df[value], errors="coerce")

    if category is not None:
        totals = df.assign(_v=values).groupby(category)["_v"].sum().dropna()
        if not totals.empty:
            top = totals.idxmax()
            sentences.append(
                t("business_top_category", lang=lang).format(
                    category=top, total=_fmt_num(totals[top]), value=value
                )
            )

    if date is not None:
        dates = pd.to_datetime(df[date], errors="coerce")
        frame = pd.DataFrame({"d": dates, "v": values}).dropna()
        if not frame.empty:
            if frame["d"].nunique() > 12:
                frame = frame.assign(period=frame["d"].dt.strftime("%Y-%m"))
            else:
                frame = frame.assign(period=frame["d"].dt.strftime("%Y-%m-%d"))
            by_period = frame.groupby("period")["v"].sum()
            if len(by_period) >= 2:
                best, worst = by_period.idxmax(), by_period.idxmin()
                sentences.append(
                    t("business_best_period", lang=lang).format(
                        period=best, total=_fmt_num(by_period[best])
                    )
                )
                sentences.append(
                    t("business_worst_period", lang=lang).format(
                        period=worst, total=_fmt_num(by_period[worst])
                    )
                )

    ordered = pd.DataFrame({"v": values})
    if date is not None:
        ordered["d"] = pd.to_datetime(df[date], errors="coerce")
        ordered = ordered.dropna(subset=["v", "d"]).sort_values("d")
    else:
        ordered = ordered.dropna(subset=["v"])
    if len(ordered) >= 2:
        half = len(ordered) // 2
        first = float(ordered["v"].iloc[:half].mean())
        second = float(ordered["v"].iloc[half:].mean())
        if first != 0:
            change = (second - first) / abs(first) * 100
            if abs(change) < 1:
                sentences.append(
                    t("business_trend_flat", lang=lang).format(
                        value=value, first=_fmt_num(first), second=_fmt_num(second)
                    )
                )
            elif change > 0:
                sentences.append(
                    t("business_trend_up", lang=lang).format(
                        value=value,
                        first=_fmt_num(first),
                        second=_fmt_num(second),
                        pct=f"{change:.1f}",
                    )
                )
            else:
                sentences.append(
                    t("business_trend_down", lang=lang).format(
                        value=value,
                        first=_fmt_num(first),
                        second=_fmt_num(second),
                        pct=f"{abs(change):.1f}",
                    )
                )

    if values.notna().any():
        max_idx = values.idxmax()
        amount = _fmt_num(float(values.loc[max_idx]))
        parts = []
        if category is not None:
            parts.append(
                t("business_where_category", lang=lang).format(category=df.loc[max_idx, category])
            )
        if date is not None:
            when = pd.to_datetime(df.loc[max_idx, date], errors="coerce")
            if pd.notna(when):
                parts.append(
                    t("business_where_date", lang=lang).format(date=when.date().isoformat())
                )
        where = " (" + ("، " if lang == "fa" else ", ").join(parts) + ")" if parts else ""
        sentences.append(
            t("business_max_single", lang=lang).format(value=value, amount=amount, where=where)
        )

    return sentences or [t("business_none", lang=lang)]


def key_insights(
    df: pd.DataFrame, report: dict | None = None, lang: str = "en"
) -> list[str]:
    """Generate insight sentences from the actual EDA numbers.

    Rules: missing > 20% in a column; |correlation| >= 0.7 between two
    columns; |skew| >= 1.0 in a numeric column; duplicate rows present.
    Returns an honest fallback sentence when nothing stands out.
    Sentences are rendered through the i18n dictionary in ``lang``
    (``"fa"`` or ``"en"``); the import is local so this core module
    never depends on Streamlit at import time.
    """
    from ui.i18n import t

    report = report or eda_report(df)
    insights: list[str] = []

    for column, info in report["missing"]["columns"].items():
        if info["percent"] >= MISSING_WARN_PCT:
            insights.append(
                t("insight_missing", lang=lang).format(
                    column=column, percent=info["percent"], missing=info["missing"]
                )
            )

    duplicates = report["overview"]["duplicate_rows"]
    if duplicates:
        insights.append(t("insight_duplicates", lang=lang).format(n=duplicates))

    for column, summary in report["columns"].items():
        if summary["type"] == "numeric" and summary.get("skew") is not None:
            if abs(summary["skew"]) >= HIGH_SKEW:
                insights.append(
                    t("insight_skew", lang=lang).format(
                        column=column, skew=f"{summary['skew']:.2f}"
                    )
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
                t("insight_correlation", lang=lang).format(
                    a=best[0], b=best[1], r=f"{best[2]:.2f}"
                )
            )

    if not insights:
        insights.append(t("insight_none", lang=lang))
    return insights
