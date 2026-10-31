"""Settings page: real configuration display and session maintenance."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from config import SETTINGS
from ui.components.common import nav_to
from utils.logger import get_logger, set_log_level

log = get_logger("page_settings")


def render() -> None:
    st.header("Settings")

    st.subheader("Configuration")
    st.dataframe(
        {
            "setting": [
                "Application",
                "Maximum upload size",
                "Allowed extensions",
                "Uploads directory",
                "Exports directory",
                "Database file",
                "Log file",
                "Log level",
            ],
            "value": [
                SETTINGS.app_name,
                f"{SETTINGS.max_upload_mb} MB",
                ", ".join(sorted(SETTINGS.allowed_extensions)),
                str(SETTINGS.uploads_dir),
                str(SETTINGS.exports_dir),
                str(SETTINGS.db_path),
                str(SETTINGS.logs_dir / "app.log"),
                st.session_state.get("log_level", SETTINGS.log_level),
            ],
        },
        use_container_width=True,
    )
    st.caption("Limits and paths come from config.py (PDA_ environment overrides).")

    st.subheader("Logging")
    level = st.selectbox(
        "Log level",
        options=["DEBUG", "INFO", "WARNING", "ERROR"],
        index=["DEBUG", "INFO", "WARNING", "ERROR"].index(
            st.session_state.get("log_level", SETTINGS.log_level)
        ),
    )
    if st.button("Apply log level"):
        set_log_level(level)
        st.session_state.log_level = level
        log.info("Log level changed to {}", level)
        st.success(f"Log level set to {level}.")

    st.subheader("Recent log lines")
    log_file = SETTINGS.logs_dir / "app.log"
    if log_file.exists():
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
        st.code("\n".join(lines) if lines else "(log file is empty)")
    else:
        st.write("No log file yet.")

    st.subheader("Session data")
    history = st.session_state.get("cleaning_history", [])
    st.write(f"Cleaning operations this session: {len(history)}")
    if st.button("Clear cleaning history"):
        st.session_state.cleaning_history = []
        st.success("Cleaning history cleared.")

    df_source = st.session_state.get("df_source")
    if df_source:
        st.write(f"Current upload on disk: `{df_source}`")
        if not st.session_state.get("confirm_delete"):
            if st.button("Delete current upload file"):
                st.session_state.confirm_delete = True
                st.rerun()
        else:
            st.warning("Delete the uploaded file from disk and unload the dataset?")
            col1, col2 = st.columns(2)
            if col1.button("Yes, delete"):
                try:
                    Path(df_source).unlink(missing_ok=True)
                except OSError as exc:
                    st.error(f"Could not delete file: {exc}")
                else:
                    for key in ("df", "df_original", "df_name", "df_source",
                                "dataset_id", "cleaning_history", "clean_preview",
                                "outlier_flags"):
                        st.session_state[key] = None if key != "cleaning_history" else []
                    st.session_state.confirm_delete = False
                    st.success("Upload deleted and dataset unloaded.")
                    st.rerun()
            if col2.button("Cancel"):
                st.session_state.confirm_delete = False
                st.rerun()
    else:
        st.write("No uploaded file on disk for the current dataset.")
        if st.button("Back to Data Import"):
            nav_to("Data Import")
