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
    _init_state()
    SETTINGS.ensure_directories()

    st.sidebar.title(SETTINGS.app_name)
    st.sidebar.caption("Upload · Clean · Explore · Visualize")
    choice = st.sidebar.radio(
        "Navigation", options=list(PAGES), key="nav",
        label_visibility="collapsed",
    )
    current = st.session_state.get("df_name")
    if current:
        st.sidebar.divider()
        st.sidebar.write(f"**Dataset:** {current}")
        st.sidebar.write(
            f"{len(st.session_state.df):,} rows × "
            f"{len(st.session_state.df.columns)} columns"
        )
    st.sidebar.divider()
    st.sidebar.caption(f"Uploads: `{SETTINGS.uploads_dir}`")

    log.debug("Rendering page {}", choice)
    PAGES[choice]()


if __name__ == "__main__":
    main()
