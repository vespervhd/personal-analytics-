"""Reusable dashboard components.

Every helper here is used by at least one page and performs real work:
navigation, dataset gating, metrics, and human-readable reports.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.i18n import current_lang, t

#: Cleaning/analysis report dict keys -> i18n keys for display labels.
#: Values are never translated (they are data or internal identifiers);
#: unknown keys fall back to the raw key.
REPORT_KEY_LABELS = {
    "rows_before": "rk_rows_before",
    "rows_after": "rk_rows_after",
    "rows_removed": "rk_rows_removed",
    "columns": "rk_columns",
    "how": "rk_how",
    "strategy": "rk_strategy",
    "filled": "rk_filled",
    "skipped": "rk_skipped",
    "subset": "rk_subset",
    "conversions": "rk_conversions",
    "mapping": "rk_mapping",
    "query": "rk_query",
    "total_missing": "rk_total_missing",
    "total_percent": "rk_total_percent",
    "lower": "rk_lower",
    "upper": "rk_upper",
    "outliers": "rk_outliers",
    "missing": "col_missing",
    "percent": "col_percent",
}


def report_key_label(key: str, lang: str | None = None) -> str:
    """Display label for a report dict key in the active language."""
    label_key = REPORT_KEY_LABELS.get(key)
    if label_key is None:
        return key
    return t(label_key, lang=lang if lang is not None else current_lang())


def translate_report_keys(value, lang: str | None = None):
    """Copy ``value`` with every dict key replaced by its display label."""
    code = lang if lang is not None else current_lang()
    if isinstance(value, dict):
        return {report_key_label(k, lang=code): translate_report_keys(v, lang=code)
                for k, v in value.items()}
    if isinstance(value, list):
        return [translate_report_keys(item, lang=code) for item in value]
    return value


def nav_to(page: str) -> None:
    """Switch the sidebar navigation to ``page`` and rerun.

    The assignment must NOT happen after the ``nav`` widget was already
    created in this run (Streamlit raises
    StreamlitWidgetAlreadyInstantiatedError), so the request is parked
    under ``nav_pending`` and applied at the top of the next run, before
    the widget exists.
    """
    st.session_state["nav_pending"] = page
    st.rerun()


def require_dataset() -> pd.DataFrame | None:
    """Return the session DataFrame, or prompt for an import and return None."""
    df = st.session_state.get("df")
    if df is None:
        st.info(t("no_dataset"))
        if st.button(t("go_to_import")):
            nav_to("Data Import")
        return None
    return df


def metric_row(metrics: dict[str, str]) -> None:
    """Render ``{label: value}`` as a row of Streamlit metrics."""
    columns = st.columns(len(metrics))
    for column, (label, value) in zip(columns, metrics.items()):
        column.metric(label, value)


def show_report(report: dict) -> None:
    """Render a cleaning/analysis report dict as readable lines.

    Dict keys are shown through their translated labels (Persian when
    fa is active); values are shown as-is. ``nav_to`` and its
    ``nav_pending`` mechanism live above and are untouched here.
    """
    st.write(f"**{t('operation_label')}:** `{report.get('operation', '—')}`")
    for key, value in report.items():
        if key == "operation":
            continue
        label = report_key_label(key)
        if isinstance(value, dict):
            st.write(f"**{label}:**")
            st.json(translate_report_keys(value))
        else:
            st.write(f"**{label}:** {value}")


def dataframe_preview(df: pd.DataFrame, rows: int = 10) -> None:
    """Show the first ``rows`` rows plus the dataset shape."""
    st.dataframe(df.head(rows), use_container_width=True)
    st.caption(t("preview_caption").format(shown=min(rows, len(df)), total=len(df), cols=len(df.columns)))
