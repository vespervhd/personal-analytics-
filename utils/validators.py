"""Upload and dataset validation helpers.

Pure functions: no I/O, no global state. Every failure raises
:class:`ValidationError` with a message the UI can show directly.
"""

from __future__ import annotations

import re
from pathlib import Path

from config import ALLOWED_EXTENSIONS, SETTINGS

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


class ValidationError(ValueError):
    """Raised when an upload or dataset fails validation."""


def file_extension(filename: str) -> str:
    """Return the lowercase extension of ``filename`` without the dot."""
    return Path(filename).suffix.lower().lstrip(".")


def validate_extension(filename: str) -> str:
    """Return the extension if allowed, else raise :class:`ValidationError`."""
    if not filename or not filename.strip():
        raise ValidationError("A filename is required.")
    extension = file_extension(filename)
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValidationError(
            f"Unsupported file type '.{extension}'. Allowed types: {allowed}."
        )
    return extension


def validate_size(num_bytes: int, max_bytes: int = SETTINGS.max_upload_bytes) -> None:
    """Raise :class:`ValidationError` when ``num_bytes`` exceeds the limit."""
    if num_bytes < 0:
        raise ValidationError("File size must not be negative.")
    if num_bytes > max_bytes:
        raise ValidationError(
            f"File is {num_bytes / 1024 / 1024:.1f} MB, exceeding the "
            f"{max_bytes / 1024 / 1024:.0f} MB limit."
        )


def validate_upload(filename: str, num_bytes: int) -> str:
    """Validate extension and size together; return the extension."""
    extension = validate_extension(filename)
    validate_size(num_bytes)
    if num_bytes == 0:
        raise ValidationError("Uploaded file is empty (0 bytes).")
    return extension


def safe_filename(filename: str) -> str:
    """Return a filesystem-safe basename for ``filename``.

    Directory components are stripped, unsafe characters become underscores,
    and an empty result falls back to ``dataset`` plus the original
    extension (so the extension allowlist still applies downstream).
    """
    base = Path(filename).name
    extension = file_extension(base)
    stem = Path(base).stem
    clean_stem = _UNSAFE_CHARS.sub("_", stem).strip("._") or "dataset"
    return f"{clean_stem}.{extension}" if extension else clean_stem


def validate_not_empty(df, label: str = "dataset") -> None:
    """Raise :class:`ValidationError` when a DataFrame has no rows/columns."""
    if df is None or df.shape[0] == 0 or df.shape[1] == 0:
        raise ValidationError(
            f"The {label} is empty (no rows or no columns to analyse)."
        )
