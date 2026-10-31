"""Application configuration for the Personal Data Analytics Platform.

Single source of truth for paths, limits, and feature flags. Defaults are
sane for local use; override with ``PDA_`` environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
EXPORTS_DIR = DATA_DIR / "exports"
DATABASE_DIR = DATA_DIR / "database"
LOGS_DIR = DATA_DIR / "logs"

APP_NAME = "Personal Data Analytics Platform"

#: File formats the Data Import phase accepts. ``xlrd`` covers ``.xls`` and
#: ``pyarrow`` covers ``.parquet``; both are in requirements.txt.
ALLOWED_EXTENSIONS = frozenset({"csv", "xlsx", "xls", "json", "parquet"})

DEFAULT_MAX_UPLOAD_MB = 200


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings."""

    app_name: str = APP_NAME
    base_dir: Path = BASE_DIR
    uploads_dir: Path = UPLOADS_DIR
    exports_dir: Path = EXPORTS_DIR
    database_dir: Path = DATABASE_DIR
    logs_dir: Path = LOGS_DIR
    max_upload_mb: int = int(os.environ.get("PDA_MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB))
    log_level: str = os.environ.get("PDA_LOG_LEVEL", "INFO")
    allowed_extensions: frozenset[str] = ALLOWED_EXTENSIONS

    def __post_init__(self) -> None:
        if self.max_upload_mb <= 0:
            raise ValueError("max_upload_mb must be a positive number of megabytes")
        if not self.allowed_extensions:
            raise ValueError("allowed_extensions must not be empty")

    @property
    def db_path(self) -> Path:
        """SQLite file for metadata, history, and preferences."""
        return self.database_dir / "analytics.db"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def ensure_directories(self) -> None:
        """Create every storage directory the app writes to."""
        for directory in (
            self.uploads_dir,
            self.exports_dir,
            self.database_dir,
            self.logs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


SETTINGS = Settings()
