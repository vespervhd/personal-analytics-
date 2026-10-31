"""Reusable dashboard components.

Every helper here is used by at least one page and performs real work:
navigation, dataset gating, metrics, and human-readable reports.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st


def nav_to(page: str) -> None:
    """Switch the sidebar navigation to ``page`` and rerun."""
    st.session_state.nav = page
    st.rerun()


def require_dataset() -> pd.DataFrame | None:
    """Return the session DataFrame, or prompt for an import and return None."""
    df = st.session_state.get("df")
    if df is None:
        st.info("No dataset loaded yet. Import one first.")
        if st.button("Go to Data Import"):
            nav_to("Data Import")
        return None
    return df


def metric_row(metrics: dict[str, str]) -> None:
    """Render ``{label: value}`` as a row of Streamlit metrics."""
    columns = st.columns(len(metrics))
    for column, (label, value) in zip(columns, metrics.items()):
        column.metric(label, value)


def show_report(report: dict) -> None:
    """Render a cleaning/analysis report dict as readable lines."""
    st.write(f"**Operation:** `{report.get('operation', '—')}`")
    for key, value in report.items():
        if key == "operation":
            continue
        if isinstance(value, dict):
            st.write(f"**{key}:**")
            st.json(value)
        else:
            st.write(f"**{key}:** {value}")


def dataframe_preview(df: pd.DataFrame, rows: int = 10) -> None:
    """Show the first ``rows`` rows plus the dataset shape."""
    st.dataframe(df.head(rows), use_container_width=True)
    st.caption(f"Showing {min(rows, len(df))} of {len(df)} rows × {len(df.columns)} columns.")
