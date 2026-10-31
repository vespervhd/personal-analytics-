"""Interactive visualization builders.

Pure functions: each takes a DataFrame plus explicit column choices and
returns a figure. Plotly figures power the dashboard; the ``matplotlib_*``
variants power static exports (PDF/Excel) without any extra renderer.

Filtering and grouping happen *before* calling these functions — see
``core.data_cleaner.filter_rows`` — so a figure always shows exactly the
rows it was given, nothing silently dropped (the one documented exception
is :func:`pie_chart`, which groups small slices into an explicit
``"Other"`` bucket and says so in the title).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import seaborn as sns

from utils.logger import get_logger

log = get_logger("visualization")

#: Maximum pie slices before the tail is grouped into "Other".
PIE_MAX_SLICES = 15


class VisualizationError(ValueError):
    """Raised when a chart cannot be built from the given columns."""


def _require_columns(df: pd.DataFrame, columns: list[str | None]) -> None:
    if df is None or df.empty:
        raise VisualizationError("Cannot chart an empty dataset.")
    missing = [c for c in columns if c is not None and c not in df.columns]
    if missing:
        raise VisualizationError(f"Unknown columns: {missing}")


def _require_numeric(df: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        if not pd.api.types.is_numeric_dtype(df[column]):
            raise VisualizationError(f"Column '{column}' must be numeric for this chart.")


def _title_or(base: str, title: str | None) -> str:
    return title or base


def bar_chart(
    df: pd.DataFrame,
    x: str,
    y: str | None = None,
    color: str | None = None,
    title: str | None = None,
) -> go.Figure:
    """Bar chart of ``y`` by ``x``; with no ``y``, bars show counts of ``x``."""
    _require_columns(df, [x, y, color])
    if y is None:
        counts = df[x].value_counts(dropna=False).reset_index()
        counts.columns = [x, "count"]
        fig = px.bar(counts, x=x, y="count", color=color if color in counts else None,
                     title=_title_or(f"Count by {x}", title))
    else:
        _require_numeric(df, [y])
        fig = px.bar(df, x=x, y=y, color=color, title=_title_or(f"{y} by {x}", title))
    log.info("bar_chart built for x={} y={}", x, y)
    return fig


def line_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str | None = None,
    title: str | None = None,
) -> go.Figure:
    """Line chart of ``y`` over ``x`` (rows sorted by ``x`` for readability)."""
    _require_columns(df, [x, y, color])
    _require_numeric(df, [y])
    ordered = df.sort_values(by=x, kind="stable")
    fig = px.line(ordered, x=x, y=y, color=color, title=_title_or(f"{y} over {x}", title))
    log.info("line_chart built for x={} y={}", x, y)
    return fig


def scatter_plot(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str | None = None,
    size: str | None = None,
    title: str | None = None,
) -> go.Figure:
    """Scatter plot of ``y`` against ``x`` with optional colour/size encodings."""
    _require_columns(df, [x, y, color, size])
    _require_numeric(df, [x, y])
    if size is not None:
        _require_numeric(df, [size])
    fig = px.scatter(df, x=x, y=y, color=color, size=size,
                     title=_title_or(f"{y} vs {x}", title))
    log.info("scatter_plot built for x={} y={}", x, y)
    return fig


def histogram(
    df: pd.DataFrame,
    column: str,
    bins: int = 30,
    title: str | None = None,
) -> go.Figure:
    """Histogram of a numeric column's distribution."""
    _require_columns(df, [column])
    _require_numeric(df, [column])
    if bins < 1:
        raise VisualizationError("bins must be at least 1.")
    fig = px.histogram(df, x=column, nbins=bins,
                       title=_title_or(f"Distribution of {column}", title))
    log.info("histogram built for {}", column)
    return fig


def box_plot(
    df: pd.DataFrame,
    column: str,
    by: str | None = None,
    title: str | None = None,
) -> go.Figure:
    """Box plot of a numeric column, optionally grouped by a category."""
    _require_columns(df, [column, by])
    _require_numeric(df, [column])
    fig = px.box(df, x=by, y=column,
                 title=_title_or(f"Box plot of {column}" + (f" by {by}" if by else ""), title))
    log.info("box_plot built for {} by {}", column, by)
    return fig


def heatmap(
    df: pd.DataFrame,
    columns: list[str] | None = None,
    title: str | None = None,
) -> go.Figure:
    """Annotated Plotly heatmap of the correlation matrix."""
    numeric = df.select_dtypes(include="number")
    targets = columns if columns else list(numeric.columns)
    _require_columns(df, targets)
    _require_numeric(df, targets)
    if len(targets) < 2:
        raise VisualizationError("A correlation heatmap needs at least 2 numeric columns.")
    corr = df[targets].corr(numeric_only=True)
    fig = px.imshow(
        corr, text_auto=".2f", aspect="auto", color_continuous_scale="RdBu_r",
        title=_title_or("Correlation heatmap", title),
    )
    log.info("heatmap built for {}", targets)
    return fig


def pie_chart(
    df: pd.DataFrame,
    column: str,
    title: str | None = None,
) -> go.Figure:
    """Pie chart of value counts.

    When a column has more than :data:`PIE_MAX_SLICES` distinct values, the
    smallest ones are grouped into one ``"Other (N categories)"`` slice so
    the chart stays readable; the grouping is stated in the title.
    """
    _require_columns(df, [column])
    counts = df[column].value_counts(dropna=False)
    if len(counts) == 0:
        raise VisualizationError(f"Column '{column}' has no values to chart.")
    grouped = False
    if len(counts) > PIE_MAX_SLICES:
        head = counts.iloc[:PIE_MAX_SLICES]
        tail_count = int(counts.iloc[PIE_MAX_SLICES:].sum())
        tail_n = len(counts) - PIE_MAX_SLICES
        counts = pd.concat(
            [head, pd.Series({f"Other ({tail_n} categories)": tail_count})]
        )
        grouped = True
    fig = px.pie(
        names=counts.index.astype(str), values=counts.values,
        title=_title_or(
            f"Share of {column}" + (" (small categories grouped)" if grouped else ""),
            title,
        ),
    )
    log.info("pie_chart built for {} (grouped={})", column, grouped)
    return fig


def matplotlib_histogram(
    df: pd.DataFrame, column: str, bins: int = 30
) -> tuple[plt.Figure, plt.Axes]:
    """Static matplotlib histogram (used for PDF/Excel reports)."""
    _require_columns(df, [column])
    _require_numeric(df, [column])
    fig, ax = plt.subplots()
    ax.hist(df[column].dropna(), bins=bins)
    ax.set_title(f"Distribution of {column}")
    ax.set_xlabel(column)
    ax.set_ylabel("Count")
    fig.tight_layout()
    return fig, ax


def matplotlib_box(
    df: pd.DataFrame, column: str, by: str | None = None
) -> tuple[plt.Figure, plt.Axes]:
    """Static matplotlib/seaborn box plot (used for PDF/Excel reports)."""
    _require_columns(df, [column, by])
    _require_numeric(df, [column])
    fig, ax = plt.subplots()
    if by:
        sns.boxplot(data=df, x=by, y=column, ax=ax)
    else:
        sns.boxplot(data=df, y=column, ax=ax)
    ax.set_title(f"Box plot of {column}" + (f" by {by}" if by else ""))
    fig.tight_layout()
    return fig, ax


def correlation_graph(
    df: pd.DataFrame, columns: list[str] | None = None
) -> tuple[plt.Figure, plt.Axes]:
    """Static seaborn correlation heatmap (used for PDF/Excel reports)."""
    numeric = df.select_dtypes(include="number")
    targets = columns if columns else list(numeric.columns)
    _require_columns(df, targets)
    _require_numeric(df, targets)
    if len(targets) < 2:
        raise VisualizationError("A correlation graph needs at least 2 numeric columns.")
    corr = df[targets].corr(numeric_only=True)
    fig, ax = plt.subplots(figsize=(max(6, len(targets) * 0.8), max(5, len(targets) * 0.7)))
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="RdBu_r", center=0, ax=ax)
    ax.set_title("Correlation graph")
    fig.tight_layout()
    return fig, ax
