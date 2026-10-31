"""Reports page: generate and download PDF, Excel, CSV, and HTML reports."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from config import SETTINGS
from core.report_generator import ReportError, generate_report
from database.connection import get_session, init_db
from database.repository import record_report
from ui.components.common import require_dataset
from ui.i18n import t


def render() -> None:
    st.header(t("page_reports"))
    df = require_dataset()
    if df is None:
        return

    anomalies = st.session_state.get("ml_anomalies")
    if anomalies:
        st.write(t("anomaly_available").format(n=anomalies["anomalies"], method=anomalies["method"]))
    else:
        st.write(t("no_anomaly"))

    fmt = st.selectbox(t("report_format"), options=["pdf", "xlsx", "csv", "html"])
    base = st.session_state.get("df_name", "dataset") or "dataset"
    safe_base = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in base)[:40]
    filename = f"{safe_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{fmt}"

    if st.button(t("generate_btn")):
        target = SETTINGS.exports_dir / filename
        try:
            path = generate_report(df, fmt, target, anomalies)
        except ReportError as exc:
            st.error(t("report_failed").format(err=exc))
        else:
            st.success(t("report_generated").format(path=path))
            dataset_id = st.session_state.get("dataset_id")
            try:
                init_db()
                with get_session() as session:
                    record_report(session, report_format=fmt, path=str(path),
                                  dataset_id=dataset_id)
            except Exception as exc:
                st.warning(t("report_record_warn").format(err=exc))
            st.download_button(
                t("download_report_btn"),
                data=path.read_bytes(),
                file_name=path.name,
                mime="application/octet-stream",
            )

    st.subheader(t("prev_reports_sub"))
    SETTINGS.ensure_directories()
    files = sorted(
        SETTINGS.exports_dir.iterdir(),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:10]
    if not files:
        st.write(t("no_reports"))
    for file in files:
        col1, col2 = st.columns([3, 1])
        col1.write(f"`{file.name}` ({file.stat().st_size / 1024:.1f} KB)")
        col2.download_button(
            t("download_btn"),
            data=file.read_bytes(),
            file_name=file.name,
            mime="application/octet-stream",
            key=f"dl_{file.name}",
        )
