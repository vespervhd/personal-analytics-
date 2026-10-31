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
from core.export import dataframe_to_xlsx_bytes
from database.connection import get_session, init_db
from database.repository import record_cleaning
from ui.components.common import dataframe_preview, require_dataset, show_report
from ui.i18n import t

_OPERATIONS = [
    "Drop missing values",
    "Fill missing values",
    "Drop duplicates",
    "Convert column type",
    "Rename columns",
    "Filter rows",
    "Flag outliers (IQR)",
]

_OP_LABELS = {
    "Drop missing values": "op_drop_missing",
    "Fill missing values": "op_fill_missing",
    "Drop duplicates": "op_drop_duplicates",
    "Convert column type": "op_convert_dtype",
    "Rename columns": "op_rename",
    "Filter rows": "op_filter",
    "Flag outliers (IQR)": "op_flag_outliers",
}


def _preview_section() -> None:
    preview = st.session_state.get("clean_preview")
    if preview is None:
        return
    operation, result_df, report = preview
    st.subheader(t("preview_title").format(op=t(_OP_LABELS[operation])))
    show_report(report)
    if result_df is not None:
        dataframe_preview(result_df, rows=10)
    if st.button(t("apply_btn")):
        if operation == "Flag outliers (IQR)":
            st.session_state.outlier_flags = result_df
            st.success(t("outlier_stored"))
        else:
            st.session_state.df = result_df
            st.success(t("change_applied"))
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
                st.warning(t("record_warn").format(err=exc))
        st.session_state.clean_preview = None
        st.rerun()
    if st.button(t("discard_btn")):
        st.session_state.clean_preview = None
        st.rerun()


def render() -> None:
    st.header(t("page_data_cleaning"))
    df = require_dataset()
    if df is None:
        return

    st.write(
        t("cleaning_intro").format(rows=f"{len(df):,}", cols=len(df.columns))
    )

    operation = st.selectbox(t("operation_label"), options=_OPERATIONS, format_func=lambda op: t(_OP_LABELS[op]))
    try:
        if operation == "Drop missing values":
            columns = st.multiselect(t("only_cols"), options=list(df.columns))
            how = st.selectbox(t("drop_when"), options=["any", "all"])
            if st.button(t("preview_btn")):
                st.session_state.clean_preview = (
                    operation, *drop_missing(df, columns or None, how)
                )
        elif operation == "Fill missing values":
            mode = st.selectbox(t("strategy_label"), options=["median", "mean", "mode"])
            if st.button(t("preview_btn")):
                st.session_state.clean_preview = (operation, *fill_missing(df, strategy=mode))
        elif operation == "Drop duplicates":
            columns = st.multiselect(t("only_cols"), options=list(df.columns))
            if st.button(t("preview_btn")):
                st.session_state.clean_preview = (operation, *drop_duplicates(df, columns or None))
        elif operation == "Convert column type":
            column = st.selectbox(t("column_label"), options=list(df.columns))
            target = st.selectbox(t("target_type"), options=["int64", "float64", "str", "bool", "datetime64[ns]"])
            if st.button(t("preview_btn")):
                st.session_state.clean_preview = (
                    operation, *convert_dtype(df, {column: target})
                )
        elif operation == "Rename columns":
            st.write(t("rename_help"))
            text = st.text_area(t("renames_label"), placeholder="age = Age")
            mapping = {}
            for line in text.splitlines():
                if "=" in line:
                    old, new = line.split("=", 1)
                    mapping[old.strip()] = new.strip()
            if st.button(t("preview_btn")):
                if not mapping:
                    st.warning(t("rename_warn"))
                else:
                    st.session_state.clean_preview = (operation, *rename_columns(df, mapping))
        elif operation == "Filter rows":
            query = st.text_input(t("filter_label"), placeholder="age > 30")
            if st.button(t("preview_btn")):
                st.session_state.clean_preview = (operation, *filter_rows(df, query))
        elif operation == "Flag outliers (IQR)":
            columns = st.multiselect(t("numeric_cols_filtered"), options=list(df.columns))
            if st.button(t("preview_btn")):
                flags, report = flag_outliers_iqr(df, columns or None)
                st.session_state.clean_preview = (operation, flags, report)
    except DataCleaningError as exc:
        st.error(t("preview_error").format(err=exc))

    _preview_section()

    flags = st.session_state.get("outlier_flags")
    if flags is not None:
        st.subheader(t("stored_flags_sub"))
        st.dataframe(flags.head(50), use_container_width=True)

    st.divider()
    col1, col2 = st.columns(2)
    if col1.button(t("reset_btn")):
        st.session_state.df = st.session_state.df_original.copy(deep=True)
        st.session_state.cleaning_history = []
        st.session_state.clean_preview = None
        st.session_state.outlier_flags = None
        st.success(t("reset_success"))
        st.rerun()
    history = st.session_state.get("cleaning_history", [])
    col2.write(t("history_applied").format(n=len(history)))
    # Export reads the working dataset only, in memory — it never modifies
    # df, df_original, or the original upload file. Guarded so an empty
    # working dataset does not raise at render time.
    if len(df) > 0 and len(df.columns) > 0:
        base = st.session_state.get("df_name", "dataset") or "dataset"
        safe_base = "".join(
            c if c.isalnum() or c in ("-", "_") else "_" for c in base
        )[:40]
        st.download_button(
            t("download_cleaned"),
            data=dataframe_to_xlsx_bytes(st.session_state.df),
            file_name=f"{safe_base}_cleaned.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
