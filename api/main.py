"""FastAPI backend for the Personal Data Analytics Platform.

Run with::

    uvicorn api.main:app

Endpoints:
- GET  /health — liveness check.
- POST /datasets/summary — upload a file, get overview + missing stats.
  The upload is saved under ``data/uploads/`` (same as the dashboard) and
  its metadata is recorded; ``metadata_saved`` reports whether that step
  succeeded.
- GET  /datasets — recent dataset metadata, newest first.
- GET  /datasets/{dataset_id} — one metadata row, or 404.
"""

from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, UploadFile

from api.schemas import (
    DatasetMetadataResponse,
    DatasetSummaryResponse,
    HealthResponse,
)
from config import SETTINGS
from core.data_cleaner import missing_value_report
from core.data_loader import DataLoadError, dataset_summary, load_from_bytes
from database.connection import get_session, init_db
from database.repository import get_dataset, list_datasets, record_dataset
from utils.logger import get_logger
from utils.validators import ValidationError

log = get_logger("api")

app = FastAPI(title=SETTINGS.app_name)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness check."""
    return HealthResponse()


@app.post("/datasets/summary", response_model=DatasetSummaryResponse)
async def dataset_summary_endpoint(file: UploadFile = File(...)) -> DatasetSummaryResponse:
    """Upload a dataset and return its overview plus missing-value stats."""
    data = await file.read()
    try:
        df, saved_path = load_from_bytes(file.filename or "upload", data)
    except (ValidationError, DataLoadError) as exc:
        log.warning("API upload rejected for {}: {}", file.filename, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    summary = dataset_summary(df)
    missing = missing_value_report(df)
    dataset_id: int | None = None
    metadata_saved = False
    try:
        init_db()
        with get_session() as session:
            row = record_dataset(
                session,
                filename=file.filename or "upload",
                file_format=(file.filename or "").rsplit(".", 1)[-1].lower(),
                rows=len(df),
                columns=len(df.columns),
                dtypes={str(col): str(dtype) for col, dtype in df.dtypes.items()},
                saved_path=str(saved_path),
                file_size_bytes=len(data),
            )
            dataset_id = row.id
        metadata_saved = True
    except Exception as exc:  # metadata failure must not lose the summary
        log.warning("API metadata recording failed: {}", exc)
    return DatasetSummaryResponse(
        dataset_id=dataset_id,
        filename=file.filename or "upload",
        file_format=(file.filename or "").rsplit(".", 1)[-1].lower(),
        rows=summary["rows"],
        columns=summary["columns"],
        dtypes=summary["dtypes"],
        memory_mb=summary["memory_mb"],
        missing_total=missing["total_missing"],
        missing_by_column={
            col: info["missing"] for col, info in missing["columns"].items()
        },
        metadata_saved=metadata_saved,
    )


@app.get("/datasets", response_model=list[DatasetMetadataResponse])
def list_datasets_endpoint(limit: int = 50) -> list[DatasetMetadataResponse]:
    """Return recent dataset metadata, newest first."""
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500.")
    try:
        init_db()
        with get_session() as session:
            rows = list_datasets(session, limit=limit)
            return [
                DatasetMetadataResponse(
                    id=row.id,
                    filename=row.filename,
                    saved_path=row.saved_path,
                    file_format=row.file_format,
                    file_size_bytes=row.file_size_bytes,
                    rows=row.rows,
                    columns=row.columns,
                    uploaded_at=row.uploaded_at,
                )
                for row in rows
            ]
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("API dataset listing failed: {}", exc)
        raise HTTPException(status_code=500, detail="Could not read dataset metadata.") from exc


@app.get("/datasets/{dataset_id}", response_model=DatasetMetadataResponse)
def get_dataset_endpoint(dataset_id: int) -> DatasetMetadataResponse:
    """Return one dataset metadata row, or 404."""
    try:
        init_db()
        with get_session() as session:
            row = get_dataset(session, dataset_id)
    except Exception as exc:
        log.warning("API dataset lookup failed: {}", exc)
        raise HTTPException(status_code=500, detail="Could not read dataset metadata.") from exc
    if row is None:
        raise HTTPException(status_code=404, detail=f"No dataset with id {dataset_id}.")
    return DatasetMetadataResponse(
        id=row.id,
        filename=row.filename,
        saved_path=row.saved_path,
        file_format=row.file_format,
        file_size_bytes=row.file_size_bytes,
        rows=row.rows,
        columns=row.columns,
        uploaded_at=row.uploaded_at,
    )
