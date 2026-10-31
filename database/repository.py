"""CRUD helpers for the metadata database.

Every function takes an explicit SQLAlchemy session and commits its own
write, so callers never guess about transaction state. Read helpers never
mutate.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import (
    AnalysisHistory,
    CleaningOperation,
    DatasetMetadata,
    GeneratedReport,
    ModelConfig,
    UserPreference,
)
from utils.logger import get_logger

log = get_logger("repository")


def record_dataset(
    session: Session,
    *,
    filename: str,
    file_format: str,
    rows: int,
    columns: int,
    dtypes: dict,
    saved_path: str | None = None,
    file_size_bytes: int = 0,
) -> DatasetMetadata:
    """Insert a dataset metadata row and return it (with its new id)."""
    row = DatasetMetadata(
        filename=filename,
        saved_path=saved_path,
        file_format=file_format,
        file_size_bytes=file_size_bytes,
        rows=rows,
        columns=columns,
        dtypes=dtypes,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    log.info("Recorded dataset {} (id={})", filename, row.id)
    return row


def get_dataset(session: Session, dataset_id: int) -> DatasetMetadata | None:
    """Return one dataset row by id, or None."""
    return session.get(DatasetMetadata, dataset_id)


def list_datasets(session: Session, limit: int = 50) -> list[DatasetMetadata]:
    """Return the most recently uploaded datasets, newest first."""
    stmt = (
        select(DatasetMetadata)
        .order_by(DatasetMetadata.uploaded_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def record_analysis(
    session: Session,
    *,
    analysis_type: str,
    parameters: dict,
    result_summary: dict,
    dataset_id: int | None = None,
) -> AnalysisHistory:
    """Insert an analysis history row and return it."""
    row = AnalysisHistory(
        dataset_id=dataset_id,
        analysis_type=analysis_type,
        parameters=parameters,
        result_summary=result_summary,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    log.info("Recorded analysis {} (id={})", analysis_type, row.id)
    return row


def record_cleaning(
    session: Session,
    *,
    operation: str,
    parameters: dict,
    rows_before: int | None = None,
    rows_after: int | None = None,
    dataset_id: int | None = None,
) -> CleaningOperation:
    """Insert a cleaning operation row and return it."""
    row = CleaningOperation(
        dataset_id=dataset_id,
        operation=operation,
        parameters=parameters,
        rows_before=rows_before,
        rows_after=rows_after,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    log.info("Recorded cleaning {} (id={})", operation, row.id)
    return row


def set_preference(session: Session, key: str, value: dict) -> UserPreference:
    """Upsert a preference by key and return it."""
    row = session.scalars(
        select(UserPreference).where(UserPreference.key == key)
    ).first()
    if row is None:
        row = UserPreference(key=key, value=value)
        session.add(row)
    else:
        row.value = value
    session.commit()
    session.refresh(row)
    return row


def get_preference(session: Session, key: str, default: dict | None = None) -> dict:
    """Return a preference value, or ``default`` when the key is absent."""
    row = session.scalars(
        select(UserPreference).where(UserPreference.key == key)
    ).first()
    return dict(row.value) if row is not None else dict(default or {})


def record_report(
    session: Session,
    *,
    report_format: str,
    path: str,
    dataset_id: int | None = None,
) -> GeneratedReport:
    """Insert a generated-report row and return it."""
    row = GeneratedReport(
        dataset_id=dataset_id, report_format=report_format, path=path
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    log.info("Recorded report {} at {}", report_format, path)
    return row


def record_model_config(
    session: Session,
    *,
    name: str,
    model_type: str,
    parameters: dict,
    dataset_id: int | None = None,
) -> ModelConfig:
    """Insert a model configuration row and return it."""
    row = ModelConfig(
        name=name, model_type=model_type, parameters=parameters, dataset_id=dataset_id
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    log.info("Recorded model config {} (id={})", name, row.id)
    return row
