"""Personal Data Analytics Platform — Streamlit dashboard entry point.

Navigation lives in the sidebar; each page module owns one screen and all
state lives in ``st.session_state`` (current DataFrame, its original copy,
cleaning history, previews, flags). Business logic stays in ``core/`` —
pages only wire controls to core functions.

Run with::

    streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from config import SETTINGS
from core.persistence import clear_state, load_state, save_state
from core.workspaces import (
    ensure_default_project,
    load_projects,
    migrate_legacy_state,
    project_dir,
    resolve_token,
    touch_project,
)
from ui.i18n import rtl_style, t
from ui.mobile_style import mobile_style
from ui.pages import (
    analysis,
    charts,
    cleaning,
    data_import,
    explorer,
    ml,
    overview,
    reports,
    settings_page,
)
from utils.logger import get_logger

log = get_logger("app")

#: All nine dashboard pages, each backed by a working engine.
PAGES = {
    "Overview": overview.render,
    "Data Import": data_import.render,
    "Data Explorer": explorer.render,
    "Data Cleaning": cleaning.render,
    "Statistical Analysis": analysis.render,
    "Visualizations": charts.render,
    "Machine Learning": ml.render,
    "Reports": reports.render,
    "Settings": settings_page.render,
}

_STATE_DEFAULTS = {
    "nav": "Overview",
    "lang": "fa",
    "df": None,
    "df_original": None,
    "df_name": "",
    "df_source": None,
    "dataset_id": None,
    "cleaning_history": [],
    "clean_preview": None,
    "outlier_flags": None,
    "log_level": SETTINGS.log_level,
    "confirm_delete": False,
    "ws_token": None,
    "project_id": None,
}


def _init_state() -> None:
    for key, value in _STATE_DEFAULTS.items():
        st.session_state.setdefault(key, value)


def main() -> None:
    st.set_page_config(
        page_title=SETTINGS.app_name,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.5rem; padding-bottom: 1rem; }
        h1, h2, h3 { letter-spacing: -0.01em; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    # ITEM 8 — phone layout (separate additive block; the style block
    # above is untouched). Global mobile CSS from ui/mobile_style.py:
    # media queries only, so desktop rendering is unchanged.
    st.markdown(mobile_style(), unsafe_allow_html=True)
    _init_state()
    # Apply a pending navigation request BEFORE the nav widget is created.
    # Assigning session_state["nav"] after the widget exists raises
    # StreamlitWidgetAlreadyInstantiatedError.
    if "nav_pending" in st.session_state:
        st.session_state["nav"] = st.session_state.pop("nav_pending")
    # Resolve the workspace token BEFORE any restore, from ?ws=. An
    # invalid or missing token generates a fresh one, which is written
    # back to the URL at once (and used in memory immediately, so the
    # rerun that setting the param causes is harmless: resolution is
    # idempotent). The token is validated, never used raw as a path,
    # so one visitor's persisted dataset is never restored for another.
    raw_ws = st.query_params.get("ws")
    token = resolve_token(raw_ws if isinstance(raw_ws, str) else None)
    if raw_ws != token:
        st.query_params["ws"] = token
    st.session_state["ws_token"] = token
    # One-time legacy adoption: a pre-workspace top-level persisted
    # state moves into this first token's first project, then the
    # legacy files are gone, so no later visitor can inherit them.
    migrate_legacy_state(token)
    # Resolve the active project before the sidebar widgets exist.
    projects = load_projects(token)
    active_id = st.session_state.get("project_id")
    if not any(p.get("id") == active_id for p in projects):
        default = ensure_default_project(token, name=t("project_default_name"))
        active_id = default["id"] if default else None
        st.session_state["project_id"] = active_id
        projects = load_projects(token)
    # Apply a pending project-select value (set by the Settings page
    # when it creates/switches/deletes a project) BEFORE the selectbox
    # widget is created — assigning it afterwards would raise the same
    # widget error as "nav". A pending value that is no longer a real
    # project is dropped and the active project is used instead.
    pending_select = st.session_state.pop("project_select_pending", None)
    if pending_select and any(p.get("id") == pending_select for p in projects):
        st.session_state["project_select"] = pending_select
    if st.session_state.get("project_select") not in [p.get("id") for p in projects]:
        st.session_state["project_select"] = active_id
    # Restore a persisted dataset once per session, before the nav widget.
    # A browser refresh starts a fresh session, so this is what brings the
    # dataset back with no user action. The once-per-session marker matters:
    # the Settings-page delete sets df to None and reruns, which aborts the
    # run before the end-of-main clear below — without the marker, restore
    # on the next run would resurrect the just-deleted dataset. dataset_id
    # is intentionally left as None on restore (the DB metadata row is not
    # required); the nav key is never touched here. Restore is scoped to
    # the active project only.
    if st.session_state.get("df") is None and not st.session_state.get(
        "_persistence_restore_done"
    ):
        st.session_state["_persistence_restore_done"] = True
        directory = project_dir(token, active_id) if active_id else None
        restored = load_state(directory=directory) if directory is not None else None
        if restored is not None:
            st.session_state["df"] = restored["df"]
            st.session_state["df_original"] = restored["df_original"]
            st.session_state["df_name"] = restored["df_name"]
            st.session_state["df_source"] = restored["df_source"]
            st.session_state["cleaning_history"] = restored["cleaning_history"]
    SETTINGS.ensure_directories()

    st.sidebar.title(SETTINGS.app_name)
    st.sidebar.caption(t("app_tagline"))
    # Language selector ABOVE the nav radio, on its own widget key ("lang").
    # It never touches "nav": navigation still goes through nav_to() only.
    st.sidebar.selectbox(
        t("lang_label"), options=["fa", "en"], key="lang",
        format_func=lambda code: t("lang_name_fa") if code == "fa" else t("lang_name_en"),
    )
    # RTL + Vazirmatn for Persian only; English injects nothing (default LTR).
    # Read after the selector above so a just-changed language applies at once.
    rtl = rtl_style()
    if rtl:
        st.markdown(rtl, unsafe_allow_html=True)
    _PAGE_TITLE_KEYS = {
        "Overview": "page_overview",
        "Data Import": "page_data_import",
        "Data Explorer": "page_data_explorer",
        "Data Cleaning": "page_data_cleaning",
        "Statistical Analysis": "page_analysis",
        "Visualizations": "page_visualizations",
        "Machine Learning": "page_ml",
        "Reports": "page_reports",
        "Settings": "page_settings",
    }
    choice = st.sidebar.radio(
        t("nav_label"), options=list(PAGES), key="nav",
        label_visibility="collapsed",
        format_func=lambda page: t(_PAGE_TITLE_KEYS[page]),
    )
    # Compact project switcher. The widget value is only ever READ here;
    # a change means the user picked another project, so save the current
    # project first, load the target (or an empty state for a new one),
    # and rerun before any page renders.
    project_names = {p.get("id"): p.get("name", "") for p in projects}
    if projects:
        st.sidebar.selectbox(
            t("project_label"), options=[p.get("id") for p in projects],
            key="project_select",
            format_func=lambda pid: project_names.get(pid, pid),
        )
        selected = st.session_state.get("project_select")
        if selected and selected != st.session_state.get("project_id"):
            old_id = st.session_state.get("project_id")
            old_dir = project_dir(token, old_id) if old_id else None
            if st.session_state.get("df") is not None and old_dir is not None:
                save_state(
                    st.session_state["df"],
                    st.session_state.get("df_original"),
                    st.session_state.get("df_name"),
                    st.session_state.get("df_source"),
                    st.session_state.get("cleaning_history"),
                    directory=old_dir,
                )
            st.session_state["project_id"] = selected
            new_dir = project_dir(token, selected)
            restored = load_state(directory=new_dir) if new_dir is not None else None
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
            st.rerun()
    current = st.session_state.get("df_name")
    if current:
        st.sidebar.divider()
        st.sidebar.write(f"**{t('sidebar_dataset')}:** {current}")
        st.sidebar.write(
            t("dataset_shape").format(
                rows=f"{len(st.session_state.df):,}",
                cols=len(st.session_state.df.columns),
            )
        )
    st.sidebar.divider()
    st.sidebar.caption(f"{t('uploads_label')}: `{SETTINGS.uploads_dir}`")

    log.debug("Rendering page {}", choice)
    PAGES[choice]()

    # Mirror the current state to disk at the end of every run, so a later
    # refresh restores it. Pages that mutate state then rerun (cleaning
    # Apply/Reset, Settings delete) skip this block on the rerunning run,
    # but the follow-up run reaches it with the final values. No dataset
    # means no persisted state: this clears leftovers after a delete.
    # Scoped to the active project only — other projects and other
    # visitors' tokens are never touched.
    active_dir = None
    active_project = st.session_state.get("project_id")
    if active_project:
        active_dir = project_dir(token, active_project)
    if st.session_state.get("df") is not None:
        if active_dir is not None:
            save_state(
                st.session_state["df"],
                st.session_state.get("df_original"),
                st.session_state.get("df_name"),
                st.session_state.get("df_source"),
                st.session_state.get("cleaning_history"),
                directory=active_dir,
            )
            touch_project(token, active_project)
    elif active_dir is not None:
        clear_state(directory=active_dir)


if __name__ == "__main__":
    main()
