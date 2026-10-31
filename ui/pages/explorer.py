"""Data Explorer page: interactive table and per-column information."""

from __future__ import annotations

import streamlit as st

from ui.components.common import require_dataset


def render() -> None:
    st.header("Data Explorer")
    df = require_dataset()
    if df is None:
        return

    st.subheader("Table")
    selected = st.multiselect(
        "Columns to display", options=list(df.columns), default=list(df.columns)
    )
    max_rows = st.slider("Maximum rows to display", min_value=10, max_value=500,
                         value=100, step=10)
    view = df[selected] if selected else df.iloc[:, :0]
    st.dataframe(view.head(max_rows), use_container_width=True)
    st.caption(f"Showing {min(max_rows, len(view)):,} of {len(df):,} rows.")

    st.subheader("Column information")
    rows = []
    for column in df.columns:
        series = df[column]
        example = series.dropna().iloc[0] if series.notna().any() else None
        rows.append(
            {
                "column": column,
                "dtype": str(series.dtype),
                "non-null": int(series.notna().sum()),
                "null": int(series.isna().sum()),
                "unique": int(series.nunique(dropna=True)),
                "example": "" if example is None else str(example),
            }
        )
    st.dataframe(rows, use_container_width=True)
