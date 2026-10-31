"""Settings page: real configuration display and session maintenance."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from config import SETTINGS
from core.persistence import load_state, save_state
from core.workspaces import (
    create_project,
    delete_project,
    load_projects,
    project_dir,
)
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

    st.subheader(t("projects_sub"))
    token = st.session_state.get("ws_token")
    active_project = st.session_state.get("project_id")
    if token:
        projects = load_projects(token)
        for project in projects:
            pid = project.get("id")
            pname = project.get("name", "")
            is_active = pid == active_project
            label = pname + (" *" if is_active else "")
            col_name, col_del = st.columns([4, 1])
            col_name.write(label)
            if st.session_state.get("confirm_delete_project") == pid:
                st.warning(t("project_delete_confirm").format(name=pname))
                yes_col, no_col = st.columns(2)
                if yes_col.button(t("yes_delete"), key=f"confirm_project_delete_{pid}"):
                    if delete_project(token, pid):
                        st.session_state["confirm_delete_project"] = None
                        if is_active:
                            remaining = load_projects(token)
                            fallback = remaining[0] if remaining else create_project(
                                token, t("project_default_name")
                            )
                            if fallback is not None:
                                st.session_state["project_id"] = fallback["id"]
                                st.session_state["project_select_pending"] = fallback["id"]
                                fdir = project_dir(token, fallback["id"])
                                restored = load_state(directory=fdir) if fdir is not None else None
                                if restored is not None:
                                    st.session_state["df"] = restored["df"]
                                    st.session_state["df_original"] = restored["df_original"]
                                    st.session_state["df_name"] = restored["df_name"]
                                    st.session_state["df_source"] = restored["df_source"]
                                    st.session_state["cleaning_history"] = restored["cleaning_history"]
                                else:
                                    st.session_state["df"] = None
                                    st.session_state["df_original"] = None
                                    st.session_state["df_name"] = ""
                                    st.session_state["df_source"] = None
                                    st.session_state["cleaning_history"] = []
                                    st.session_state["clean_preview"] = None
                                    st.session_state["outlier_flags"] = None
                                st.session_state["_persistence_restore_done"] = True
                        st.success(t("project_deleted"))
                        st.rerun()
                    else:
                        st.error(t("project_delete_failed"))
                if no_col.button(t("cancel_btn"), key=f"cancel_project_delete_{pid}"):
                    st.session_state["confirm_delete_project"] = None
                    st.rerun()
            elif col_del.button(t("project_delete_btn"), key=f"delete_project_{pid}"):
                st.session_state["confirm_delete_project"] = pid
                st.rerun()
        new_name = st.text_input(t("project_name_label"), key="new_project_name")
        if st.button(t("create_project_btn")):
            # Save the current project first, then switch to the new,
            # empty project. The sidebar selectbox value for the next
            # run is parked under "project_select_pending" (applied at
            # the top of the next run, before the widget exists) — it
            # must never be assigned after the widget was created.
            old_dir = project_dir(token, active_project) if active_project else None
            if st.session_state.get("df") is not None and old_dir is not None:
                save_state(
                    st.session_state["df"],
                    st.session_state.get("df_original"),
                    st.session_state.get("df_name"),
                    st.session_state.get("df_source"),
                    st.session_state.get("cleaning_history"),
                    directory=old_dir,
                )
            created = create_project(token, new_name)
            if created is not None:
                st.session_state["project_id"] = created["id"]
                st.session_state["project_select_pending"] = created["id"]
                st.session_state["df"] = None
                st.session_state["df_original"] = None
                st.session_state["df_name"] = ""
                st.session_state["df_source"] = None
                st.session_state["cleaning_history"] = []
                st.session_state["clean_preview"] = None
                st.session_state["outlier_flags"] = None
                st.session_state["_persistence_restore_done"] = True
                st.success(t("project_created").format(name=created["name"]))
                st.rerun()

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
