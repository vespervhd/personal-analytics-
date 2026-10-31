"""Reports page: generate and download PDF, Excel, CSV, and HTML reports."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from config import SETTINGS
from core.report_generator import ReportError, generate_report
from database.connection import get_session, init_db
from database.repository import record_report
from ui.components.common import require_dataset


def render() -> None:
    st.header("Reports")
    df = require_dataset()
    if df is None:
        return

    anomalies = st.session_state.get("ml_anomalies")
    if anomalies:
        st.write(f"Anomaly data available: **{anomalies['anomalies']}** anomalies "
                 f"({anomalies['method']}) — they will be included in the report.")
    else:
        st.write("No anomaly detection run yet — reports will note that.")

    fmt = st.selectbox("Report format", options=["pdf", "xlsx", "csv", "html"])
    base = st.session_state.get("df_name", "dataset") or "dataset"
    safe_base = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in base)[:40]
    filename = f"{safe_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{fmt}"

    if st.button("Generate report"):
        target = SETTINGS.exports_dir / filename
        try:
            path = generate_report(df, fmt, target, anomalies)
        except ReportError as exc:
            st.error(f"Report generation failed: {exc}")
        else:
            st.success(f"Report generated: `{path}`")
            dataset_id = st.session_state.get("dataset_id")
            try:
                init_db()
                with get_session() as session:
                    record_report(session, report_format=fmt, path=str(path),
                                  dataset_id=dataset_id)
            except Exception as exc:
                st.warning(f"Report saved, but it could not be recorded: {exc}")
            st.download_button(
                "Download report",
                data=path.read_bytes(),
                file_name=path.name,
                mime="application/octet-stream",
            )

    st.subheader("Previously generated reports")
    SETTINGS.ensure_directories()
    files = sorted(
        SETTINGS.exports_dir.iterdir(),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:10]
    if not files:
        st.write("No reports generated yet.")
    for file in files:
        col1, col2 = st.columns([3, 1])
        col1.write(f"`{file.name}` ({file.stat().st_size / 1024:.1f} KB)")
        col2.download_button(
            "Download",
            data=file.read_bytes(),
            file_name=file.name,
            mime="application/octet-stream",
            key=f"dl_{file.name}",
        )
