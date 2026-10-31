"""Data Import page: drag-and-drop upload, preview, dtype detection."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config import SETTINGS
from core.data_loader import DataLoadError, dataset_summary, load_from_bytes, load_from_path
from database.connection import get_session, init_db
from database.repository import record_dataset
from ui.components.common import dataframe_preview
from ui.i18n import t
from utils.logger import get_logger
from utils.validators import ValidationError, file_extension

log = get_logger("page_data_import")

#: Bundled sample dataset shipped with the app (read-only; never written to).
SAMPLE_PATH = SETTINGS.base_dir / "data" / "sample" / "ai-models-sample.csv"
SAMPLE_DISPLAY_NAME = "AI models sample dataset"

_DEMO_ROWS = [
    {"date": "2026-01-05", "product": "Keyboard", "region": "North", "units": 12, "revenue": 540.0},
    {"date": "2026-01-06", "product": "Mouse", "region": "South", "units": 30, "revenue": 750.0},
    {"date": "2026-01-07", "product": "Keyboard", "region": "South", "units": 8, "revenue": 360.0},
    {"date": "2026-01-08", "product": "Monitor", "region": "North", "units": 5, "revenue": 1250.0},
    {"date": "2026-01-09", "product": "Mouse", "region": "North", "units": 22, "revenue": 550.0},
    {"date": "2026-01-10", "product": "Monitor", "region": "South", "units": 3, "revenue": 750.0},
]


def _store_dataset(df: pd.DataFrame, name: str, source) -> None:
    st.session_state.df = df
    st.session_state.df_original = df.copy(deep=True)
    st.session_state.df_name = name
    st.session_state.df_source = str(source) if source else None
    st.session_state.dataset_id = None
    st.session_state.cleaning_history = []
    st.session_state.clean_preview = None
    st.session_state.outlier_flags = None


def _record_metadata(
    df: pd.DataFrame, name: str, source, file_format: str, file_size: int
) -> int | None:
    """Persist dataset metadata (never the file itself). Returns the row id.

    A database failure only warns: the dataset stays usable in session.
    """
    try:
        init_db()
        with get_session() as session:
            row = record_dataset(
                session,
                filename=name,
                file_format=file_format,
                rows=len(df),
                columns=len(df.columns),
                dtypes={str(col): str(dtype) for col, dtype in df.dtypes.items()},
                saved_path=str(source) if source else None,
                file_size_bytes=file_size,
            )
            return row.id
    except Exception as exc:
        st.warning(t("metadata_warn").format(err=exc))
        log.warning("Metadata recording failed for {}: {}", name, exc)
        return None


def render() -> None:
    st.header(t("page_data_import"))
    st.write(
        t("import_intro").format(
            formats=", ".join(sorted(SETTINGS.allowed_extensions)),
            mb=SETTINGS.max_upload_mb,
        )
    )

    uploaded = st.file_uploader(
        t("uploader_label"),
        type=sorted(SETTINGS.allowed_extensions),
        help=t("uploader_help"),
    )
    if uploaded is not None:
        try:
            data = uploaded.getvalue()
            df, saved_path = load_from_bytes(uploaded.name, data)
        except (ValidationError, DataLoadError) as exc:
            st.error(t("import_failed").format(err=exc))
            log.warning("Import failed for {}: {}", uploaded.name, exc)
        else:
            _store_dataset(df, uploaded.name, saved_path)
            dataset_id = _record_metadata(
                df, uploaded.name, saved_path,
                file_extension(uploaded.name), len(data),
            )
            st.session_state.dataset_id = dataset_id
            st.success(t("imported_success").format(name=uploaded.name, rows=f"{len(df):,}", cols=len(df.columns)))
            st.write(t("saved_original").format(path=saved_path))
            log.info("Imported {} ({} rows)", uploaded.name, len(df))

    st.divider()
    if st.button(t("demo_btn")):
        demo = pd.DataFrame(_DEMO_ROWS)
        _store_dataset(demo, "Demo dataset (built-in)", None)
        st.session_state.dataset_id = _record_metadata(
            demo, "Demo dataset (built-in)", None, "demo", 0
        )
        st.success(t("demo_loaded"))

    st.write(t("sample_prompt"))
    if st.button(t("try_sample_btn")):
        try:
            sample = load_from_path(SAMPLE_PATH)
        except DataLoadError as exc:
            st.error(t("sample_load_error").format(err=exc))
            log.warning("Sample dataset load failed: {}", exc)
        else:
            _store_dataset(sample, SAMPLE_DISPLAY_NAME, SAMPLE_PATH)
            st.session_state.dataset_id = _record_metadata(
                sample, SAMPLE_DISPLAY_NAME, SAMPLE_PATH,
                file_extension(SAMPLE_PATH.name), SAMPLE_PATH.stat().st_size,
            )
            st.success(
                t("sample_loaded_replace").format(rows=f"{len(sample):,}", cols=len(sample.columns))
            )
            log.info("Loaded sample dataset ({} rows)", len(sample))

    df = st.session_state.get("df")
    if df is not None:
        st.subheader(t("preview_sub"))
        dataframe_preview(df, rows=10)
        st.subheader(t("detected_types_sub"))
        summary = dataset_summary(df)
        st.write(t("summary_line").format(rows=f"{summary['rows']:,}", cols=summary["columns"], mb=summary["memory_mb"]))
        dtype_rows = {
            t("col_column"): list(df.columns),
            t("col_detected_type"): [str(dtype) for dtype in df.dtypes],
        }
        st.dataframe(dtype_rows, use_container_width=True)
