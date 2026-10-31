"""Data Import page: drag-and-drop upload, preview, dtype detection."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config import SETTINGS
from core.data_loader import DataLoadError, dataset_summary, load_from_bytes
from database.connection import get_session, init_db
from database.repository import record_dataset
from ui.components.common import dataframe_preview
from utils.logger import get_logger
from utils.validators import ValidationError, file_extension

log = get_logger("page_data_import")

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
        st.warning(f"Dataset loaded, but its metadata could not be saved: {exc}")
        log.warning("Metadata recording failed for {}: {}", name, exc)
        return None


def render() -> None:
    st.header("Data Import")
    st.write(
        f"Supported formats: {', '.join(sorted(SETTINGS.allowed_extensions))}. "
        f"Maximum file size: {SETTINGS.max_upload_mb} MB. "
        "Files are stored under `data/uploads/`; only metadata goes to the "
        "database (Phase 4)."
    )

    uploaded = st.file_uploader(
        "Drop a dataset file here",
        type=sorted(SETTINGS.allowed_extensions),
        help="CSV, XLSX, XLS, JSON, or Parquet.",
    )
    if uploaded is not None:
        try:
            data = uploaded.getvalue()
            df, saved_path = load_from_bytes(uploaded.name, data)
        except (ValidationError, DataLoadError) as exc:
            st.error(f"Import failed: {exc}")
            log.warning("Import failed for {}: {}", uploaded.name, exc)
        else:
            _store_dataset(df, uploaded.name, saved_path)
            dataset_id = _record_metadata(
                df, uploaded.name, saved_path,
                file_extension(uploaded.name), len(data),
            )
            st.session_state.dataset_id = dataset_id
            st.success(f"Imported `{uploaded.name}` ({len(df):,} rows × {len(df.columns)} columns).")
            st.write(f"Saved original to `{saved_path}`.")
            log.info("Imported {} ({} rows)", uploaded.name, len(df))

    st.divider()
    if st.button("Load the built-in demo dataset"):
        demo = pd.DataFrame(_DEMO_ROWS)
        _store_dataset(demo, "Demo dataset (built-in)", None)
        st.session_state.dataset_id = _record_metadata(
            demo, "Demo dataset (built-in)", None, "demo", 0
        )
        st.success("Demo dataset loaded. Replace it with your own upload any time.")

    df = st.session_state.get("df")
    if df is not None:
        st.subheader("Preview")
        dataframe_preview(df, rows=10)
        st.subheader("Detected types and summary")
        summary = dataset_summary(df)
        st.write(f"Rows: **{summary['rows']:,}** · Columns: **{summary['columns']}** · "
                 f"Memory: **{summary['memory_mb']} MB**")
        dtype_rows = {
            "column": list(df.columns),
            "detected type": [str(dtype) for dtype in df.dtypes],
        }
        st.dataframe(dtype_rows, use_container_width=True)
