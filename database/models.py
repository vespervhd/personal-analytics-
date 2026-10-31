"""Database models (SQLite + SQLAlchemy).

Only metadata lives here. Uploaded files stay on disk under
``data/uploads/``; reports under ``data/exports/``. JSON columns hold
parameters and summaries so the schema stays stable as features grow.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base for all models."""


class DatasetMetadata(Base):
    """One row per imported dataset (file itself stays on disk)."""

    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    saved_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    file_format: Mapped[str] = mapped_column(String(16), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows: Mapped[int] = mapped_column(Integer, nullable=False)
    columns: Mapped[int] = mapped_column(Integer, nullable=False)
    dtypes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class AnalysisHistory(Base):
    """Record of an analysis run against a dataset."""

    __tablename__ = "analysis_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("datasets.id"), nullable=True
    )
    analysis_type: Mapped[str] = mapped_column(String(128), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class UserPreference(Base):
    """Key/value user preferences (theme choices, defaults, ...)."""

    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    value: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now, nullable=False
    )


class CleaningOperation(Base):
    """One applied cleaning step, for audit and reproducibility."""

    __tablename__ = "cleaning_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("datasets.id"), nullable=True
    )
    operation: Mapped[str] = mapped_column(String(128), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    rows_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class GeneratedReport(Base):
    """A report file produced from a dataset."""

    __tablename__ = "generated_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("datasets.id"), nullable=True
    )
    report_format: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class ModelConfig(Base):
    """Configuration of a trained model (artifacts stay out of the DB)."""

    __tablename__ = "model_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    model_type: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("datasets.id"), nullable=True
    )
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
