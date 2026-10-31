"""Overview page: dataset health at a glance."""

from __future__ import annotations

import streamlit as st

from core.data_loader import DataLoadError, load_from_path
from ui.components.common import dataframe_preview, metric_row, nav_to
from ui.i18n import t
from ui.pages.data_import import (
    SAMPLE_DISPLAY_NAME,
    SAMPLE_PATH,
    _record_metadata,
    _store_dataset,
)
from utils.validators import file_extension


def render() -> None:
    st.header(t("page_overview"))
    df = st.session_state.get("df")
    if df is None:
        st.info(t("welcome"))
        st.write(t("welcome_about"))
        col_import, col_sample = st.columns(2)
        if col_import.button(t("import_dataset_btn")):
            nav_to("Data Import")
        if col_sample.button(t("try_sample_btn")):
            try:
                sample = load_from_path(SAMPLE_PATH)
            except DataLoadError as exc:
                st.error(t("sample_load_error").format(err=exc))
            else:
                _store_dataset(sample, SAMPLE_DISPLAY_NAME, SAMPLE_PATH)
                st.session_state.dataset_id = _record_metadata(
                    sample, SAMPLE_DISPLAY_NAME, SAMPLE_PATH,
                    file_extension(SAMPLE_PATH.name), SAMPLE_PATH.stat().st_size,
                )
                st.success(
                    t("sample_loaded").format(rows=f"{len(sample):,}", cols=len(sample.columns))
                )
                df = st.session_state.get("df")
        if df is None:
            return

    st.subheader(st.session_state.get("df_name") or t("dataset_default"))
    missing_total = int(df.isna().sum().sum())
    duplicate_rows = int(df.duplicated().sum())
    metric_row(
        {
            t("metric_rows"): f"{len(df):,}",
            t("metric_columns"): f"{len(df.columns):,}",
            t("metric_missing"): f"{missing_total:,}",
            t("metric_duplicates"): f"{duplicate_rows:,}",
            t("metric_memory"): f"{df.memory_usage(deep=True).sum() / 1024 / 1024:.2f} MB",
        }
    )

    st.subheader(t("preview_sub"))
    dataframe_preview(df, rows=10)

    st.subheader(t("columns_sub"))
    info = {
        t("col_column"): list(df.columns),
        t("col_dtype"): [str(dtype) for dtype in df.dtypes],
        t("col_non_null"): [int(df[col].notna().sum()) for col in df.columns],
        t("col_unique"): [int(df[col].nunique(dropna=True)) for col in df.columns],
    }
    st.dataframe(info, use_container_width=True)

    history = st.session_state.get("cleaning_history", [])
    st.subheader(t("cleaning_history_sub"))
    if history:
        st.write(t("history_applied").format(n=len(history)))
        st.write(t("history_last").format(op=history[-1].get("operation", "—")))
    else:
        st.write(t("history_none"))

    st.subheader(t("next_steps_sub"))
    col1, col2, col3 = st.columns(3)
    if col1.button(t("explore_btn")):
        nav_to("Data Explorer")
    if col2.button(t("clean_btn")):
        nav_to("Data Cleaning")
    if col3.button(t("visualize_btn")):
        nav_to("Visualizations")
