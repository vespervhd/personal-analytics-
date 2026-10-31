"""Smart chart suggestions for the Visualizations page.

Pure, testable heuristics: columns are classified (numeric vs
categorical vs datetime, using dtypes plus cardinality), and ranked
suggestions are returned. Every suggestion maps ONLY to a chart type
the Visualizations page can already render (see ``SUPPORTED_CHARTS``),
so applying one can never ask the page to draw something it cannot.

A suggestion is a suggestion only: the page still renders its normal
controls, pre-filled from the suggestion, and the user can change
anything before the chart is drawn.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

#: Chart types the Visualizations page supports (``ui/pages/charts.py``).
SUPPORTED_CHARTS = ("Bar", "Line", "Scatter", "Histogram", "Box", "Heatmap", "Pie")

#: An object/string column with at most this many distinct values counts
#: as categorical; beyond that it is treated as free text / an identifier
#: and is not suggested as a grouping column.
MAX_CATEGORIES = 50

#: A pie chart stays readable up to this many slices; mirrors
#: ``core.visualization.PIE_MAX_SLICES`` (which groups the tail into
#: "Other" beyond it), so pie is only suggested for small categories.
PIE_MAX_SLICES = 15

#: A column needs at least this many non-null values to be suggestable.
MIN_NON_NULL = 2

#: Fraction of values that must parse for an object column to count as
#: numeric or datetime.
_PARSE_THRESHOLD = 0.9


@dataclass(frozen=True)
class Suggestion:
    """One ranked chart suggestion.

    ``chart`` is always one of :data:`SUPPORTED_CHARTS`. The column
    fields mirror the Visualizations page controls for that chart:
    ``x``/``y`` for Bar/Line/Scatter, ``column`` for Histogram/Pie,
    ``column`` + ``by`` for Box, ``columns`` for Heatmap. For a Bar
    with ``use_y=False`` the bars show counts of ``x``.
    """

    chart: str
    explanation_key: str
    x: str | None = None
    y: str | None = None
    column: str | None = None
    columns: tuple[str, ...] | None = None
    by: str | None = None
    use_y: bool = True

    def involved_columns(self) -> list[str]:
        """Column names this suggestion uses, in display order."""
        if self.columns is not None:
            return list(self.columns)
        if self.chart == "Box":
            ordered = [self.by, self.column]
        else:
            ordered = [self.x, self.column, self.y]
        return [c for c in ordered if c is not None]


def _parse_rate(series: pd.Series, parser) -> float:
    """Fraction of non-null values ``parser`` converts without loss."""
    non_null = series.dropna()
    if non_null.empty:
        return 0.0
    try:
        parsed = parser(non_null)
    except (TypeError, ValueError):
        return 0.0
    if isinstance(parsed, pd.DataFrame):
        return 0.0
    return float(parsed.notna().mean())


def classify_columns(df: pd.DataFrame) -> dict[str, list[str]]:
    """Classify each usable column as numeric, categorical, or datetime.

    Rules, in order per column (column order of ``df`` is preserved):

    * all-null columns, and columns with fewer than ``MIN_NON_NULL``
      non-null values, are unusable and skipped;
    * boolean columns are categorical (True/False groups);
    * datetime columns are datetime; numeric columns are numeric;
    * object/string columns are tried as numeric, then as datetime
      (at least 90% of values must parse), then as categorical when
      they have at most ``MAX_CATEGORIES`` distinct values; anything
      else (free text, identifiers) is left unclassified.
    """
    result: dict[str, list[str]] = {"numeric": [], "categorical": [], "datetime": []}
    if df is None or df.empty:
        return result
    for raw in df.columns:
        name = str(raw)
        series = df[raw]
        non_null = series.dropna()
        if len(non_null) < MIN_NON_NULL:
            continue
        if pd.api.types.is_bool_dtype(series):
            result["categorical"].append(name)
        elif pd.api.types.is_datetime64_any_dtype(series):
            result["datetime"].append(name)
        elif pd.api.types.is_numeric_dtype(series):
            result["numeric"].append(name)
        else:
            text = non_null.astype(str)
            if _parse_rate(text, lambda s: pd.to_numeric(s, errors="coerce")) >= _PARSE_THRESHOLD:
                result["numeric"].append(name)
            elif (
                _parse_rate(text, lambda s: pd.to_datetime(s, errors="coerce", format="mixed"))
                >= _PARSE_THRESHOLD
            ):
                result["datetime"].append(name)
            elif non_null.nunique() <= MAX_CATEGORIES:
                result["categorical"].append(name)
            # else: free text / identifier — no suggestion uses it.
    return result


def _preferred_numeric(df: pd.DataFrame, numeric: list[str]) -> list[str]:
    """Numeric columns with row-unique values (ID-like) moved last.

    A column whose every value is distinct (e.g. an ``ID`` column) is a
    poor chart axis, so it is only used when nothing else is available.
    """
    n_rows = len(df)
    ordinary = [c for c in numeric if df[c].nunique(dropna=True) < n_rows]
    unique = [c for c in numeric if df[c].nunique(dropna=True) >= n_rows]
    return ordinary + unique


def suggest_charts(df: pd.DataFrame) -> list[Suggestion]:
    """Return ranked chart suggestions for ``df`` (best first).

    Ranked order: Line (datetime trend), Bar (category vs number),
    Scatter (number vs number), Box (number grouped by category),
    Heatmap (correlations across numbers), Bar-count (category alone),
    Pie (category share), Histogram (number alone). Each mapping is
    emitted at most once, using the first suitable columns, so the list
    is short, deterministic, and never repeats a chart for one dataset
    shape beyond its distinct variants.
    """
    if df is None or df.empty:
        return []
    classes = classify_columns(df)
    numeric = classes["numeric"]
    categorical = classes["categorical"]
    datetime_cols = classes["datetime"]
    preferred = _preferred_numeric(df, numeric)
    suggestions: list[Suggestion] = []

    if datetime_cols and preferred:
        suggestions.append(
            Suggestion(
                chart="Line",
                explanation_key="suggest_line",
                x=datetime_cols[0],
                y=preferred[0],
            )
        )
    if categorical and preferred:
        suggestions.append(
            Suggestion(
                chart="Bar",
                explanation_key="suggest_bar",
                x=categorical[0],
                y=preferred[0],
                use_y=True,
            )
        )
    if len(preferred) >= 2:
        suggestions.append(
            Suggestion(
                chart="Scatter",
                explanation_key="suggest_scatter",
                x=preferred[0],
                y=preferred[1],
            )
        )
    if categorical and preferred:
        suggestions.append(
            Suggestion(
                chart="Box",
                explanation_key="suggest_box",
                column=preferred[0],
                by=categorical[0],
            )
        )
    if len(numeric) >= 2:
        suggestions.append(
            Suggestion(
                chart="Heatmap",
                explanation_key="suggest_heatmap",
                columns=tuple(numeric),
            )
        )
    if categorical:
        suggestions.append(
            Suggestion(
                chart="Bar",
                explanation_key="suggest_count",
                x=categorical[0],
                use_y=False,
            )
        )
        first_cat = categorical[0]
        if df[first_cat].nunique(dropna=True) <= PIE_MAX_SLICES:
            suggestions.append(
                Suggestion(
                    chart="Pie",
                    explanation_key="suggest_pie",
                    column=first_cat,
                )
            )
    if preferred:
        suggestions.append(
            Suggestion(
                chart="Histogram",
                explanation_key="suggest_histogram",
                column=preferred[0],
            )
        )
    return suggestions
