"""Data Import page: drag-and-drop upload, preview, dtype detection."""

from __future__ import annotations

from urllib.parse import urlparse

import pandas as pd
import streamlit as st

from config import SETTINGS
from core.alerts import (
    AlertError,
    add_alert_rule,
    delete_alert_rule,
    evaluate_rules,
    load_alert_events,
    load_alert_rules,
    mark_alerts_seen,
    notify_alert_events,
    record_alert_events,
    unseen_alert_count,
)
from core.data_loader import DataLoadError, dataset_summary, load_from_bytes, load_from_path
from core.gsheets import GSheetsError, fetch_gsheet_csv, gsheets_export_url
from core.live_source import (
    INTERVAL_CHOICES,
    LiveSourceError,
    clear_live_source,
    fetch_live_csv,
    load_live_source,
    note_live_refresh,
    refresh_live_source,
    save_live_source,
    schedule_live_refresh,
    unschedule_live_refresh,
    validate_live_url,
)
from core.persistence import load_state
from core.workspaces import project_dir
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


def _live_directory():
    """The active project's directory, or None when it cannot resolve."""
    token = st.session_state.get("ws_token")
    project_id = st.session_state.get("project_id")
    if not token or not project_id:
        return None
    return project_dir(token, project_id)


def _render_live_source() -> None:
    """Live-source section: connect a CSV URL, show status, refresh."""
    st.divider()
    st.subheader(t("live_sub"))
    st.write(t("live_intro"))
    live_dir = _live_directory()
    record = load_live_source(live_dir) if live_dir is not None else None
    if record is not None:
        st.write(t("live_status").format(url=record.get("url", "")))
        st.write(
            t("live_every_min").format(n=record.get("interval_minutes", 60))
        )
        last = record.get("last_refreshed_at")
        st.write(t("live_last_refresh").format(t=last) if last else t("live_never"))
        if record.get("last_rows") is not None:
            st.write(t("live_rows").format(n=f"{record['last_rows']:,}"))
        if record.get("last_error"):
            st.warning(t("live_error").format(err=record["last_error"]))
        col_refresh, col_disconnect = st.columns(2)
        if col_refresh.button(t("live_refresh_btn")):
            status = refresh_live_source(live_dir)
            if status is None:
                st.info(t("live_disconnected"))
            elif status.get("error"):
                st.error(t("live_refresh_failed").format(err=status["error"]))
            elif status.get("changed"):
                restored = load_state(directory=live_dir)
                if restored is not None:
                    st.session_state.df = restored["df"]
                    st.session_state.df_original = restored["df_original"]
                    st.session_state.df_name = restored["df_name"]
                    st.session_state.df_source = restored["df_source"]
                    st.session_state.cleaning_history = restored["cleaning_history"]
                    st.session_state.clean_preview = None
                    st.session_state.outlier_flags = None
                st.success(t("live_refreshed").format(rows=f"{status['rows']:,}"))
                st.rerun()
            else:
                st.info(t("live_no_change"))
        if col_disconnect.button(t("live_disconnect_btn")):
            token = st.session_state.get("ws_token")
            project_id = st.session_state.get("project_id")
            clear_live_source(live_dir)
            if token and project_id:
                unschedule_live_refresh(token, project_id)
            st.success(t("live_disconnected"))
            st.rerun()
        _render_alerts(live_dir)
        return

    url = st.text_input(t("live_url_label"))
    interval = st.selectbox(
        t("live_interval_label"),
        options=list(INTERVAL_CHOICES),
        index=INTERVAL_CHOICES.index(60),
        format_func=lambda m: t("live_every_min").format(n=m),
    )
    if st.button(t("live_connect_btn")):
        try:
            clean = validate_live_url(url)
            df_live, digest, size = fetch_live_csv(clean)
        except LiveSourceError as exc:
            st.error(t("live_failed").format(err=exc))
            log.warning("Live connect failed for {}: {}", url, exc)
        else:
            parsed = urlparse(clean)
            name = parsed.path.rsplit("/", 1)[-1] or parsed.netloc
            _store_dataset(df_live, name, clean)
            st.session_state.dataset_id = _record_metadata(
                df_live, name, clean, "csv", size
            )
            if live_dir is not None:
                save_live_source(live_dir, clean, interval, name=name)
                note_live_refresh(live_dir, digest, len(df_live))
                token = st.session_state.get("ws_token")
                project_id = st.session_state.get("project_id")
                if token and project_id:
                    schedule_live_refresh(token, project_id, interval)
            st.success(
                t("live_connected").format(rows=f"{len(df_live):,}", cols=len(df_live.columns))
            )
            log.info("Live source connected: {} ({} rows)", clean, len(df_live))
            st.rerun()


def _render_alerts(live_dir) -> None:
    """Alert rules and triggered events for the connected live source."""
    st.divider()
    st.subheader(t("alert_sub"))
    st.write(t("alert_intro"))
    events = load_alert_events(live_dir)
    if unseen_alert_count(live_dir) > 0:
        st.warning(t("alert_new"))
        # Viewing the section marks the current events as seen.
        mark_alerts_seen(live_dir)

    df = st.session_state.get("df")
    numeric_cols: list[str] = []
    if df is not None:
        try:
            numeric_cols = list(df.select_dtypes(include="number").columns)
        except Exception:
            numeric_cols = []
    if numeric_cols:
        col_pick = st.selectbox(t("alert_column_label"), options=numeric_cols)
        cond_pick = st.selectbox(
            t("alert_condition_label"),
            options=["above", "below"],
            format_func=lambda c: t("alert_condition_above")
            if c == "above"
            else t("alert_condition_below"),
        )
        threshold = st.number_input(t("alert_threshold_label"), value=0.0)
        if st.button(t("alert_add_btn")):
            try:
                rule = add_alert_rule(live_dir, col_pick, cond_pick, threshold)
            except AlertError as exc:
                st.error(t("alert_add_failed").format(err=exc))
            else:
                # Evaluate at once against the current data, so a rule
                # that already holds shows up immediately.
                if df is not None:
                    triggered = evaluate_rules(df, [rule])
                    if triggered:
                        record_alert_events(live_dir, triggered)
                        notify_alert_events(triggered)
                st.success(t("alert_added"))
                st.rerun()
    rules = load_alert_rules(live_dir)
    st.write(t("alert_rules_label"))
    if not rules:
        st.write(t("alert_no_rules"))
    for rule in rules:
        cond_text = (
            t("alert_condition_above")
            if rule.get("condition") == "above"
            else t("alert_condition_below")
        )
        col_rule, col_del = st.columns([4, 1])
        col_rule.write(
            t("alert_rule_line").format(
                column=rule.get("column"),
                cond=cond_text,
                threshold=rule.get("threshold"),
            )
        )
        if col_del.button(
            t("alert_delete_btn"), key=f"alert_del_{rule.get('id')}"
        ):
            delete_alert_rule(live_dir, rule.get("id"))
            st.success(t("alert_deleted"))
            st.rerun()
    st.write(t("alert_events_label"))
    if not events:
        st.write(t("alert_no_events"))
    for event in events[:10]:
        cond_text = (
            t("alert_condition_above")
            if event.get("condition") == "above"
            else t("alert_condition_below")
        )
        st.write(
            t("alert_event_line").format(
                column=event.get("column"),
                cond=cond_text,
                value=event.get("value"),
                at=event.get("at"),
            )
        )


def _render_gsheets() -> None:
    """Google Sheets import: public sheets only, no sign-in."""
    st.divider()
    st.subheader(t("gsheets_sub"))
    st.write(t("gsheets_intro"))
    url = st.text_input(t("gsheets_url_label"))
    if st.button(t("gsheets_import_btn")):
        try:
            df_sheet, sheet_id, gid, size = fetch_gsheet_csv(url)
        except GSheetsError as exc:
            st.error(t("gsheets_failed").format(err=exc))
            log.warning("Google Sheets import failed for {}: {}", url, exc)
        else:
            export_url = gsheets_export_url(sheet_id, gid)
            name = f"Google Sheet {sheet_id[:10]}"
            _store_dataset(df_sheet, name, export_url)
            st.session_state.dataset_id = _record_metadata(
                df_sheet, name, export_url, "csv", size
            )
            st.success(
                t("gsheets_imported").format(
                    rows=f"{len(df_sheet):,}", cols=len(df_sheet.columns)
                )
            )
            log.info("Imported Google Sheet {} ({} rows)", sheet_id, len(df_sheet))
            st.rerun()


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

    _render_live_source()
    _render_gsheets()

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
