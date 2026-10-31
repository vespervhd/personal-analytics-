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

_CHARTS = ["Bar", "Line", "Scatter", "Histogram", "Box", "Heatmap", "Pie"]


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    return [str(c) for c in df.select_dtypes(include="number").columns]


def render() -> None:
    st.header("Visualizations")
    df = require_dataset()
    if df is None:
        return

    chart = st.selectbox("Chart type", options=_CHARTS)
    columns = list(df.columns)
    numeric = _numeric_columns(df)
    try:
        if chart == "Bar":
            x = st.selectbox("X (category)", options=columns)
            use_y = st.checkbox("Use a Y value (otherwise bars show counts)", value=False)
            y = st.selectbox("Y (numeric)", options=numeric) if use_y else None
            color = st.selectbox("Colour by (optional)", options=[None] + columns)
            fig = bar_chart(df, x, y, color=color)
        elif chart == "Line":
            x = st.selectbox("X", options=columns)
            y = st.selectbox("Y (numeric)", options=numeric)
            color = st.selectbox("Colour by (optional)", options=[None] + columns)
            fig = line_chart(df, x, y, color=color)
        elif chart == "Scatter":
            x = st.selectbox("X (numeric)", options=numeric)
            y = st.selectbox("Y (numeric)", options=numeric)
            color = st.selectbox("Colour by (optional)", options=[None] + columns)
            size = st.selectbox("Size by (optional)", options=[None] + numeric)
            fig = scatter_plot(df, x, y, color=color, size=size)
        elif chart == "Histogram":
            column = st.selectbox("Column (numeric)", options=numeric)
            bins = st.slider("Bins", min_value=5, max_value=100, value=30)
            fig = histogram(df, column, bins=bins)
        elif chart == "Box":
            column = st.selectbox("Column (numeric)", options=numeric)
            by = st.selectbox("Group by (optional)", options=[None] + columns)
            fig = box_plot(df, column, by=by)
        elif chart == "Heatmap":
            selected = st.multiselect("Numeric columns", options=numeric, default=numeric)
            fig = heatmap(df, selected or None)
        else:  # Pie
            column = st.selectbox("Column", options=columns)
            fig = pie_chart(df, column)
        st.plotly_chart(fig, use_container_width=True)
    except VisualizationError as exc:
        st.error(f"Could not build chart: {exc}")
