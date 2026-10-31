"""Pydantic schemas for the FastAPI backend."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness response for GET /health."""

    status: str = "ok"


class DatasetSummaryResponse(BaseModel):
    """Overview + data-quality summary for an uploaded dataset."""

    dataset_id: int | None = Field(
        default=None, description="Database id when metadata was saved, else null."
    )
    filename: str
    file_format: str
    rows: int
    columns: int
    dtypes: dict[str, str]
    memory_mb: float
    missing_total: int
    missing_by_column: dict[str, int]
    metadata_saved: bool


class DatasetMetadataResponse(BaseModel):
    """One stored dataset metadata row."""

    id: int
    filename: str
    saved_path: str | None
    file_format: str
    file_size_bytes: int
    rows: int
    columns: int
    uploaded_at: datetime
