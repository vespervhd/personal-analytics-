"""Overview page: dataset health at a glance."""

from __future__ import annotations

import streamlit as st

from ui.components.common import dataframe_preview, metric_row, nav_to


def render() -> None:
    st.header("Overview")
    df = st.session_state.get("df")
    if df is None:
        st.info("Welcome. Import a dataset to start analysing it.")
        if st.button("Import a dataset"):
            nav_to("Data Import")
        return

    st.subheader(st.session_state.get("df_name", "Dataset"))
    missing_total = int(df.isna().sum().sum())
    duplicate_rows = int(df.duplicated().sum())
    metric_row(
        {
            "Rows": f"{len(df):,}",
            "Columns": f"{len(df.columns):,}",
            "Missing cells": f"{missing_total:,}",
            "Duplicate rows": f"{duplicate_rows:,}",
            "Memory": f"{df.memory_usage(deep=True).sum() / 1024 / 1024:.2f} MB",
        }
    )

    st.subheader("Preview")
    dataframe_preview(df, rows=10)

    st.subheader("Columns")
    info = {
        "column": list(df.columns),
        "dtype": [str(dtype) for dtype in df.dtypes],
        "non-null": [int(df[col].notna().sum()) for col in df.columns],
        "unique": [int(df[col].nunique(dropna=True)) for col in df.columns],
    }
    st.dataframe(info, use_container_width=True)

    history = st.session_state.get("cleaning_history", [])
    st.subheader("Cleaning history")
    if history:
        st.write(f"{len(history)} operation(s) applied this session.")
        st.write(f"Last operation: `{history[-1].get('operation', '—')}`")
    else:
        st.write("No cleaning operations applied yet.")

    st.subheader("Next steps")
    col1, col2, col3 = st.columns(3)
    if col1.button("Explore data"):
        nav_to("Data Explorer")
    if col2.button("Clean data"):
        nav_to("Data Cleaning")
    if col3.button("Visualize"):
        nav_to("Visualizations")
