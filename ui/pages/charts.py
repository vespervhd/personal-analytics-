"""Visualizations page: chart type, columns, grouping, and filter controls."""

from __future__ import annotations

import pandas as pd
import streamlit as st

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



def _numeric_columns(df: pd.DataFrame) -> list[str]:
    return [str(c) for c in df.select_dtypes(include="number").columns]


def render() -> None:
    st.header(t("page_visualizations"))
    df = require_dataset()
    if df is None:
        return

    chart = st.selectbox(t("chart_type"), options=_CHARTS, format_func=lambda c: t(_CHART_LABELS[c]))
    columns = list(df.columns)
    numeric = _numeric_columns(df)
    try:
        if chart == "Bar":
            x = st.selectbox(t("x_category"), options=columns)
            use_y = st.checkbox(t("use_y"), value=False)
            y = st.selectbox(t("y_numeric"), options=numeric) if use_y else None
            color = st.selectbox(t("colour_by"), options=[None] + columns)
            fig = bar_chart(df, x, y, color=color)
        elif chart == "Line":
            x = st.selectbox(t("x_label"), options=columns)
            y = st.selectbox(t("y_numeric"), options=numeric)
            color = st.selectbox(t("colour_by"), options=[None] + columns)
            fig = line_chart(df, x, y, color=color)
        elif chart == "Scatter":
            x = st.selectbox(t("x_numeric"), options=numeric)
            y = st.selectbox(t("y_numeric"), options=numeric)
            color = st.selectbox(t("colour_by"), options=[None] + columns)
            size = st.selectbox(t("size_by"), options=[None] + numeric)
            fig = scatter_plot(df, x, y, color=color, size=size)
        elif chart == "Histogram":
            column = st.selectbox(t("column_numeric"), options=numeric)
            bins = st.slider(t("bins_label"), min_value=5, max_value=100, value=30)
            fig = histogram(df, column, bins=bins)
        elif chart == "Box":
            column = st.selectbox(t("column_numeric"), options=numeric)
            by = st.selectbox(t("group_by"), options=[None] + columns)
            fig = box_plot(df, column, by=by)
        elif chart == "Heatmap":
            selected = st.multiselect(t("numeric_cols_label"), options=numeric, default=numeric)
            fig = heatmap(df, selected or None)
        else:  # Pie
            column = st.selectbox(t("column_plain"), options=columns)
            fig = pie_chart(df, column)
        st.plotly_chart(fig, use_container_width=True)
    except VisualizationError as exc:
        st.error(t("chart_error").format(err=exc))
