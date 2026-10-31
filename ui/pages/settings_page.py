"""Settings page: real configuration display and session maintenance."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from config import SETTINGS
from ui.components.common import nav_to
from ui.i18n import t
from utils.logger import get_logger, set_log_level

log = get_logger("page_settings")


def render() -> None:
    st.header(t("page_settings"))

    st.subheader(t("config_sub"))
    st.dataframe(
        {
            t("col_setting"): [
                t("setting_app"),
                t("setting_max_upload"),
                t("setting_allowed"),
                t("setting_uploads_dir"),
                t("setting_exports_dir"),
                t("setting_db"),
                t("setting_log_file"),
                t("setting_log_level"),
            ],
            t("col_value"): [
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
    st.caption(t("config_caption"))

    st.subheader(t("logging_sub"))
    level = st.selectbox(
        t("log_level_label"),
        options=["DEBUG", "INFO", "WARNING", "ERROR"],
        index=["DEBUG", "INFO", "WARNING", "ERROR"].index(
            st.session_state.get("log_level", SETTINGS.log_level)
        ),
    )
    if st.button(t("apply_log_btn")):
        set_log_level(level)
        st.session_state.log_level = level
        log.info("Log level changed to {}", level)
        st.success(t("log_set").format(level=level))

    st.subheader(t("recent_logs_sub"))
    log_file = SETTINGS.logs_dir / "app.log"
    if log_file.exists():
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
        st.code("\n".join(lines) if lines else t("log_empty"))
    else:
        st.write(t("no_log_file"))

    st.subheader(t("session_data_sub"))
    history = st.session_state.get("cleaning_history", [])
    st.write(t("cleaning_ops_count").format(n=len(history)))
    if st.button(t("clear_history_btn")):
        st.session_state.cleaning_history = []
        st.success(t("history_cleared"))

    df_source = st.session_state.get("df_source")
    if df_source:
        st.write(t("current_upload").format(path=df_source))
        if not st.session_state.get("confirm_delete"):
            if st.button(t("delete_upload_btn")):
                st.session_state.confirm_delete = True
                st.rerun()
        else:
            st.warning(t("delete_confirm"))
            col1, col2 = st.columns(2)
            if col1.button(t("yes_delete")):
                try:
                    Path(df_source).unlink(missing_ok=True)
                except OSError as exc:
                    st.error(t("delete_failed").format(err=exc))
                else:
                    for key in ("df", "df_original", "df_name", "df_source",
                                "dataset_id", "cleaning_history", "clean_preview",
                                "outlier_flags"):
                        st.session_state[key] = None if key != "cleaning_history" else []
                    st.session_state.confirm_delete = False
                    st.success(t("upload_deleted"))
                    st.rerun()
            if col2.button(t("cancel_btn")):
                st.session_state.confirm_delete = False
                st.rerun()
    else:
        st.write(t("no_upload_disk"))
        if st.button(t("back_to_import")):
            nav_to("Data Import")
