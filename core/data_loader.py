"""Dataset loading: CSV, XLSX, XLS, JSON, Parquet.

Entry points:

- :func:`load_from_path` — read a file already on disk.
- :func:`load_from_bytes` — validate, persist under ``data/uploads/`` with a
  safe unique filename, then load. This is the upload path.
- :func:`detect_encoding` — CSV encoding detection with a strict fallback
  chain (utf-8 -> utf-8-sig -> latin-1).

The original file is never modified. Every failure raises
:class:`DataLoadError` with a message suitable for the UI.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

from config import SETTINGS
from utils.logger import get_logger
from utils.validators import (
    ValidationError,
    file_extension,
    safe_filename,
    validate_not_empty,
    validate_upload,
)

log = get_logger("data_loader")

_ENCODING_FALLBACKS = ("utf-8", "utf-8-sig", "latin-1")


class DataLoadError(ValueError):
    """Raised when a dataset cannot be loaded or parsed."""


def detect_encoding(data: bytes) -> str:
    """Return the first encoding that strictly decodes ``data``.

    Tries utf-8, then utf-8-sig (BOM), and finally latin-1, which always
    succeeds — so this function never raises for non-empty input.
    """
    for encoding in _ENCODING_FALLBACKS:
        try:
            data.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "latin-1"


def _load_csv(path: Path) -> pd.DataFrame:
    raw = path.read_bytes()
    encoding = detect_encoding(raw)
    try:
        return pd.read_csv(io.BytesIO(raw), encoding=encoding)
    except Exception as exc:  # pandas raises ParserError and friends
        raise DataLoadError(f"Could not parse CSV (tried encoding {encoding}): {exc}") from exc


def _load_excel(path: Path) -> pd.DataFrame:
    extension = file_extension(path.name)
    engine = "openpyxl" if extension == "xlsx" else "xlrd"
    try:
        return pd.read_excel(path, engine=engine)
    except ImportError as exc:
        raise DataLoadError(
            f"Reading .{extension} files needs the '{engine}' package, "
            f"which is not installed: {exc}"
        ) from exc
    except Exception as exc:
        raise DataLoadError(f"Could not parse .{extension} file: {exc}") from exc


def _load_json(path: Path) -> pd.DataFrame:
    try:
        return pd.read_json(path)
    except ValueError:
        # Newline-delimited JSON is common for exported datasets.
        try:
            return pd.read_json(path, lines=True)
        except Exception as exc:
            raise DataLoadError(f"Could not parse JSON file: {exc}") from exc


def _load_parquet(path: Path) -> pd.DataFrame:
    try:
        return pd.read_parquet(path, engine="pyarrow")
    except ImportError as exc:
        raise DataLoadError(
            "Reading .parquet files needs the 'pyarrow' package, "
            "which is not installed."
        ) from exc
    except Exception as exc:
        raise DataLoadError(f"Could not parse Parquet file: {exc}") from exc


_LOADERS = {
    "csv": _load_csv,
    "xlsx": _load_excel,
    "xls": _load_excel,
    "json": _load_json,
    "parquet": _load_parquet,
}


def load_from_path(path: str | Path) -> pd.DataFrame:
    """Load a dataset from ``path`` and return it as a DataFrame."""
    path = Path(path)
    if not path.exists():
        raise DataLoadError(f"File not found: {path}")
    if path.stat().st_size == 0:
        raise DataLoadError(f"File is empty (0 bytes): {path}")
    extension = file_extension(path.name)
    loader = _LOADERS.get(extension)
    if loader is None:
        raise DataLoadError(f"Unsupported file type '.{extension}'.")
    log.info("Loading {} (.{}) from {}", path.name, extension, path.parent)
    df = loader(path)
    try:
        validate_not_empty(df, label=f"dataset in {path.name}")
    except ValidationError as exc:
        raise DataLoadError(str(exc)) from exc
    log.info("Loaded {} rows x {} columns from {}", len(df), len(df.columns), path.name)
    return df


def _unique_upload_path(filename: str) -> Path:
    """Return a non-colliding path under ``data/uploads/``."""
    SETTINGS.ensure_directories()
    safe = safe_filename(filename)
    candidate = SETTINGS.uploads_dir / safe
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    counter = 2
    while (candidate := SETTINGS.uploads_dir / f"{stem}_{counter}{suffix}").exists():
        counter += 1
    return candidate


def load_from_bytes(filename: str, data: bytes) -> tuple[pd.DataFrame, Path]:
    """Validate, persist, and load an uploaded file.

    Returns ``(dataframe, saved_path)``. The saved copy is the user's
    original upload; cleaning and analysis always work on DataFrame copies
    and never rewrite this file.
    """
    validate_upload(filename, len(data))
    saved_path = _unique_upload_path(filename)
    saved_path.write_bytes(data)
    log.info("Saved upload {} ({} bytes) to {}", filename, len(data), saved_path)
    return load_from_path(saved_path), saved_path


def dataset_summary(df: pd.DataFrame) -> dict:
    """Return a light, loader-level summary (deep stats live in analyzer)."""
    memory_bytes = int(df.memory_usage(deep=True).sum())
    return {
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "column_names": list(df.columns),
        "dtypes": {str(col): str(dtype) for col, dtype in df.dtypes.items()},
        # Rounded MB for display; exact bytes alongside (tiny frames round to 0.0 MB).
        "memory_mb": round(memory_bytes / 1024 / 1024, 3),
        "memory_bytes": memory_bytes,
    }
