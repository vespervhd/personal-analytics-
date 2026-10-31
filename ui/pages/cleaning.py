"""Data Cleaning page: preview-before-apply operations.

Nothing here touches the original upload: every operation runs on a copy,
the preview shows the exact change report first, and only "Apply" replaces
the working dataset. "Reset to original" restores the uploaded data.
"""

from __future__ import annotations

import streamlit as st

from core.data_cleaner import (
    DataCleaningError,
    convert_dtype,
    drop_duplicates,
    drop_missing,
    fill_missing,
    filter_rows,
    flag_outliers_iqr,
    rename_columns,
)
from database.connection import get_session, init_db
from database.repository import record_cleaning
from ui.components.common import dataframe_preview, require_dataset, show_report

_OPERATIONS = [
    "Drop missing values",
    "Fill missing values",
    "Drop duplicates",
    "Convert column type",
    "Rename columns",
    "Filter rows",
    "Flag outliers (IQR)",
]


def _preview_section() -> None:
    preview = st.session_state.get("clean_preview")
    if preview is None:
        return
    operation, result_df, report = preview
    st.subheader(f"Preview — {operation}")
    show_report(report)
    if result_df is not None:
        dataframe_preview(result_df, rows=10)
    if st.button("Apply this change"):
        if operation == "Flag outliers (IQR)":
            st.session_state.outlier_flags = result_df
            st.success("Outlier flags stored (dataset rows unchanged).")
        else:
            st.session_state.df = result_df
            st.success("Change applied to the working dataset.")
        st.session_state.cleaning_history.append(report)
        dataset_id = st.session_state.get("dataset_id")
        if dataset_id:
            try:
                init_db()
                with get_session() as session:
                    record_cleaning(
                        session,
                        operation=report.get("operation", operation),
                        parameters={
                            k: v for k, v in report.items() if k != "operation"
                        },
                        rows_before=report.get("rows_before"),
                        rows_after=report.get("rows_after"),
                        dataset_id=dataset_id,
                    )
            except Exception as exc:
                st.warning(f"Change applied, but it could not be recorded: {exc}")
        st.session_state.clean_preview = None
        st.rerun()
    if st.button("Discard preview"):
        st.session_state.clean_preview = None
        st.rerun()


def render() -> None:
    st.header("Data Cleaning")
    df = require_dataset()
    if df is None:
        return

    st.write(
        f"Working dataset: **{len(df):,} rows × {len(df.columns)} columns**. "
        "Every operation below previews its exact effect before anything changes."
    )

    operation = st.selectbox("Operation", options=_OPERATIONS)
    try:
        if operation == "Drop missing values":
            columns = st.multiselect("Only these columns (empty = all)", options=list(df.columns))
            how = st.selectbox("Drop a row when", options=["any", "all"])
            if st.button("Preview"):
                st.session_state.clean_preview = (
                    operation, *drop_missing(df, columns or None, how)
                )
        elif operation == "Fill missing values":
            mode = st.selectbox("Strategy", options=["median", "mean", "mode"])
            if st.button("Preview"):
                st.session_state.clean_preview = (operation, *fill_missing(df, strategy=mode))
        elif operation == "Drop duplicates":
            columns = st.multiselect("Only these columns (empty = all)", options=list(df.columns))
            if st.button("Preview"):
                st.session_state.clean_preview = (operation, *drop_duplicates(df, columns or None))
        elif operation == "Convert column type":
            column = st.selectbox("Column", options=list(df.columns))
            target = st.selectbox("Target type", options=["int64", "float64", "str", "bool", "datetime64[ns]"])
            if st.button("Preview"):
                st.session_state.clean_preview = (
                    operation, *convert_dtype(df, {column: target})
                )
        elif operation == "Rename columns":
            st.write("One rename per line, as `old_name = new_name`.")
            text = st.text_area("Renames", placeholder="age = Age")
            mapping = {}
            for line in text.splitlines():
                if "=" in line:
                    old, new = line.split("=", 1)
                    mapping[old.strip()] = new.strip()
            if st.button("Preview"):
                if not mapping:
                    st.warning("Enter at least one rename as `old = new`.")
                else:
                    st.session_state.clean_preview = (operation, *rename_columns(df, mapping))
        elif operation == "Filter rows":
            query = st.text_input("Filter expression", placeholder="age > 30")
            if st.button("Preview"):
                st.session_state.clean_preview = (operation, *filter_rows(df, query))
        elif operation == "Flag outliers (IQR)":
            columns = st.multiselect("Numeric columns (empty = all numeric)", options=list(df.columns))
            if st.button("Preview"):
                flags, report = flag_outliers_iqr(df, columns or None)
                st.session_state.clean_preview = (operation, flags, report)
    except DataCleaningError as exc:
        st.error(f"Could not preview: {exc}")

    _preview_section()

    flags = st.session_state.get("outlier_flags")
    if flags is not None:
        st.subheader("Stored outlier flags")
        st.dataframe(flags.head(50), use_container_width=True)

    st.divider()
    col1, col2 = st.columns(2)
    if col1.button("Reset to original upload"):
        st.session_state.df = st.session_state.df_original.copy(deep=True)
        st.session_state.cleaning_history = []
        st.session_state.clean_preview = None
        st.session_state.outlier_flags = None
        st.success("Working dataset reset to the original upload.")
        st.rerun()
    history = st.session_state.get("cleaning_history", [])
    col2.write(f"{len(history)} operation(s) applied this session.")
