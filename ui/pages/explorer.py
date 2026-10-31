"""Data Explorer page: interactive table and per-column information."""

from __future__ import annotations

import streamlit as st

from ui.components.common import require_dataset
from ui.i18n import t


def render() -> None:
    st.header(t("page_data_explorer"))
    df = require_dataset()
    if df is None:
        return

    st.subheader(t("table_sub"))
    selected = st.multiselect(
        t("columns_display"), options=list(df.columns), default=list(df.columns)
    )
    max_rows = st.slider(t("max_rows"), min_value=10, max_value=500,
                         value=100, step=10)
    view = df[selected] if selected else df.iloc[:, :0]
    st.dataframe(view.head(max_rows), use_container_width=True)
    st.caption(t("showing_rows").format(shown=f"{min(max_rows, len(view)):,}", total=f"{len(df):,}"))

    st.subheader(t("column_info_sub"))
    rows = []
    for column in df.columns:
        series = df[column]
        example = series.dropna().iloc[0] if series.notna().any() else None
        rows.append(
            {
                t("col_column"): column,
                t("col_dtype"): str(series.dtype),
                t("col_non_null"): int(series.notna().sum()),
                t("col_null"): int(series.isna().sum()),
                t("col_unique"): int(series.nunique(dropna=True)),
                t("col_example"): "" if example is None else str(example),
            }
        )
    st.dataframe(rows, use_container_width=True)
