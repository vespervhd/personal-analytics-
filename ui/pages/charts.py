"""Visualizations page: chart type, columns, grouping, and filter controls.

Item 9 — smart chart suggestions: a section above the controls lists
charts the current columns suit (from ``core.chart_suggest``). A
suggestion only pre-fills the controls below it: clicking one stores
the chart type and columns under the widgets' session-state keys and
reruns, so the widgets render with those values. The user can still
change anything afterwards, and the chart draws from the controls
exactly as before — the suggestion never draws a chart by itself.

Widget keys are assigned BEFORE the widgets are created (never after),
the same rule as the ``nav_pending`` navigation fix: a click handler
sets keys, then reruns, and the widgets read them on the fresh run.
Stale keys from a previous dataset are sanitised before any widget is
created, so a value that is no longer a column can never crash a
selectbox.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.chart_suggest import Suggestion, suggest_charts
from core.visualization import (
    VisualizationError,
    bar_chart,
    box_plot,
    heatmap,
    histogram,
    line_chart,
    pie_chart,
    scatter_plot,
)
from ui.components.common import require_dataset
from ui.i18n import t

_CHARTS = ["Bar", "Line", "Scatter", "Histogram", "Box", "Heatmap", "Pie"]

_CHART_LABELS = {
    "Bar": "chart_bar",
    "Line": "chart_line",
    "Scatter": "chart_scatter",
    "Histogram": "chart_histogram",
    "Box": "chart_box",
    "Heatmap": "chart_heatmap",
    "Pie": "chart_pie",
}

#: Session-state keys for the chart controls, so a suggestion click can
#: pre-fill them before the widgets are created on the next run.
_KEYS = {
    "chart": "ch_chart",
    "bar_x": "ch_bar_x",
    "bar_use_y": "ch_bar_use_y",
    "bar_y": "ch_bar_y",
    "bar_color": "ch_bar_color",
    "line_x": "ch_line_x",
    "line_y": "ch_line_y",
    "line_color": "ch_line_color",
    "scatter_x": "ch_scatter_x",
    "scatter_y": "ch_scatter_y",
    "scatter_color": "ch_scatter_color",
    "scatter_size": "ch_scatter_size",
    "hist_col": "ch_hist_col",
    "hist_bins": "ch_hist_bins",
    "box_col": "ch_box_col",
    "box_by": "ch_box_by",
    "heat_cols": "ch_heat_cols",
    "pie_col": "ch_pie_col",
}


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    return [str(c) for c in df.select_dtypes(include="number").columns]


def _apply_suggestion(suggestion: Suggestion) -> None:
    """Pre-fill the chart controls from ``suggestion`` and rerun.

    All assignments happen before any chart widget is created in the
    rerun that follows, so no widget value is ever set after its
    widget exists. Optional encodings reset to None so the suggested
    chart starts clean instead of inheriting an earlier choice.
    """
    st.session_state[_KEYS["chart"]] = suggestion.chart
    if suggestion.chart == "Bar":
        st.session_state[_KEYS["bar_x"]] = suggestion.x
        st.session_state[_KEYS["bar_use_y"]] = suggestion.use_y
        st.session_state[_KEYS["bar_y"]] = suggestion.y
        st.session_state[_KEYS["bar_color"]] = None
    elif suggestion.chart == "Line":
        st.session_state[_KEYS["line_x"]] = suggestion.x
        st.session_state[_KEYS["line_y"]] = suggestion.y
        st.session_state[_KEYS["line_color"]] = None
    elif suggestion.chart == "Scatter":
        st.session_state[_KEYS["scatter_x"]] = suggestion.x
        st.session_state[_KEYS["scatter_y"]] = suggestion.y
        st.session_state[_KEYS["scatter_color"]] = None
        st.session_state[_KEYS["scatter_size"]] = None
    elif suggestion.chart == "Histogram":
        st.session_state[_KEYS["hist_col"]] = suggestion.column
    elif suggestion.chart == "Box":
        st.session_state[_KEYS["box_col"]] = suggestion.column
        st.session_state[_KEYS["box_by"]] = suggestion.by
    elif suggestion.chart == "Heatmap":
        st.session_state[_KEYS["heat_cols"]] = list(suggestion.columns or [])
    elif suggestion.chart == "Pie":
        st.session_state[_KEYS["pie_col"]] = suggestion.column
    st.rerun()


def _sanitize_keys(df: pd.DataFrame) -> None:
    """Drop stored control values that are no longer valid options.

    Runs before any widget is created, so a dataset switch can never
    leave a selectbox holding a column that no longer exists. A dropped
    key simply falls back to the widget's default on this run.
    """
    columns = list(df.columns)
    numeric = _numeric_columns(df)
    select_options = {
        _KEYS["chart"]: _CHARTS,
        _KEYS["bar_x"]: columns,
        _KEYS["bar_y"]: numeric,
        _KEYS["bar_color"]: [None] + columns,
        _KEYS["line_x"]: columns,
        _KEYS["line_y"]: numeric,
        _KEYS["line_color"]: [None] + columns,
        _KEYS["scatter_x"]: numeric,
        _KEYS["scatter_y"]: numeric,
        _KEYS["scatter_color"]: [None] + columns,
        _KEYS["scatter_size"]: [None] + numeric,
        _KEYS["hist_col"]: numeric,
        _KEYS["box_col"]: numeric,
        _KEYS["box_by"]: [None] + columns,
        _KEYS["pie_col"]: columns,
    }
    for key, options in select_options.items():
        if key in st.session_state:
            value = st.session_state[key]
            if value is not None and value not in options:
                del st.session_state[key]
    heat_key = _KEYS["heat_cols"]
    if heat_key in st.session_state:
        value = st.session_state[heat_key]
        if isinstance(value, list):
            kept = [c for c in value if c in numeric]
            if kept != value:
                st.session_state[heat_key] = kept


def _render_suggestions(df: pd.DataFrame) -> None:
    """Render the suggestion section above the chart controls."""
    suggestions = suggest_charts(df)
    if not suggestions:
        return
    st.subheader(t("suggest_heading"))
    st.caption(t("suggest_hint"))
    for index, suggestion in enumerate(suggestions):
        cols = suggestion.involved_columns()
        if suggestion.chart == "Heatmap":
            cols_label = ", ".join(cols)
        else:
            cols_label = " × ".join(cols)
        label = f"{t(_CHART_LABELS[suggestion.chart])}: {cols_label}"
        if st.button(label, key=f"ch_suggest_{index}"):
            _apply_suggestion(suggestion)
        st.caption(t(suggestion.explanation_key))


def render() -> None:
    st.header(t("page_visualizations"))
    df = require_dataset()
    if df is None:
        return

    _render_suggestions(df)
    _sanitize_keys(df)

    chart = st.selectbox(
        t("chart_type"), options=_CHARTS, key=_KEYS["chart"],
        format_func=lambda c: t(_CHART_LABELS[c]),
    )
    columns = list(df.columns)
    numeric = _numeric_columns(df)
    try:
        if chart == "Bar":
            x = st.selectbox(t("x_category"), options=columns, key=_KEYS["bar_x"])
            use_y = st.checkbox(t("use_y"), value=False, key=_KEYS["bar_use_y"])
            y = st.selectbox(t("y_numeric"), options=numeric, key=_KEYS["bar_y"]) if use_y else None
            color = st.selectbox(t("colour_by"), options=[None] + columns, key=_KEYS["bar_color"])
            fig = bar_chart(df, x, y, color=color)
        elif chart == "Line":
            x = st.selectbox(t("x_label"), options=columns, key=_KEYS["line_x"])
            y = st.selectbox(t("y_numeric"), options=numeric, key=_KEYS["line_y"])
            color = st.selectbox(t("colour_by"), options=[None] + columns, key=_KEYS["line_color"])
            fig = line_chart(df, x, y, color=color)
        elif chart == "Scatter":
            x = st.selectbox(t("x_numeric"), options=numeric, key=_KEYS["scatter_x"])
            y = st.selectbox(t("y_numeric"), options=numeric, key=_KEYS["scatter_y"])
            color = st.selectbox(t("colour_by"), options=[None] + columns, key=_KEYS["scatter_color"])
            size = st.selectbox(t("size_by"), options=[None] + numeric, key=_KEYS["scatter_size"])
            fig = scatter_plot(df, x, y, color=color, size=size)
        elif chart == "Histogram":
            column = st.selectbox(t("column_numeric"), options=numeric, key=_KEYS["hist_col"])
            bins = st.slider(t("bins_label"), min_value=5, max_value=100, value=30, key=_KEYS["hist_bins"])
            fig = histogram(df, column, bins=bins)
        elif chart == "Box":
            column = st.selectbox(t("column_numeric"), options=numeric, key=_KEYS["box_col"])
            by = st.selectbox(t("group_by"), options=[None] + columns, key=_KEYS["box_by"])
            fig = box_plot(df, column, by=by)
        elif chart == "Heatmap":
            selected = st.multiselect(
                t("numeric_cols_label"), options=numeric, default=numeric, key=_KEYS["heat_cols"]
            )
            fig = heatmap(df, selected or None)
        else:  # Pie
            column = st.selectbox(t("column_plain"), options=columns, key=_KEYS["pie_col"])
            fig = pie_chart(df, column)
        st.plotly_chart(fig, use_container_width=True)
    except VisualizationError as exc:
        st.error(t("chart_error").format(err=exc))
