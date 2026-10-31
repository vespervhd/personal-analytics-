"""Persistence of the working dataset across page refreshes.

Streamlit session state vanishes when the browser reloads, so the working
dataset, its original copy, the dataset name/source, and the cleaning
history are mirrored to disk under ``data/persisted/`` (new files only —
the original upload under ``data/uploads/`` is never touched, and cleaning
always works on DataFrame copies).

Layout inside the persisted directory::

    working.parquet    the current working dataset
    original.parquet   the pristine original dataset
    manifest.json      df_name, df_source, cleaning_history, saved_at

Every function fails soft: file I/O is wrapped in try/except, the failure
is logged, and the caller gets a falsy/None result instead of an exception
reaching the UI. Datasets whose working frame exceeds 50 MB of deep memory
are skipped (logged), so a giant upload never slows every run.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from config import DATA_DIR
from utils.logger import get_logger

log = get_logger("persistence")

#: Deep-memory ceiling for the working frame; larger frames are not persisted.
MAX_PERSIST_BYTES = 50 * 1024 * 1024

_WORKING_FILE = "working.parquet"
_ORIGINAL_FILE = "original.parquet"
_MANIFEST_FILE = "manifest.json"


def persisted_dir() -> Path:
    """Return the directory holding the persisted dataset files."""
    return DATA_DIR / "persisted"


def _paths(directory: Path | None) -> tuple[Path, Path, Path]:
    base = Path(directory) if directory is not None else persisted_dir()
    return base / _WORKING_FILE, base / _ORIGINAL_FILE, base / _MANIFEST_FILE


def save_state(
    df: pd.DataFrame | None,
    df_original: pd.DataFrame | None,
    df_name: str | None,
    df_source: str | Path | None,
    cleaning_history: list[Any] | None,
    *,
    max_bytes: int = MAX_PERSIST_BYTES,
    directory: Path | None = None,
) -> bool:
    """Persist the working dataset, original, name, source, and history.

    Returns True when the state was written, False when it was skipped
    (nothing to save, or the working frame exceeds ``max_bytes``) or when
    writing failed. Never raises.
    """
    if df is None:
        return False
    try:
        memory_bytes = int(df.memory_usage(deep=True).sum())
    except Exception as exc:
        log.warning("Persistence skipped: could not measure dataset size: {}", exc)
        return False
    if memory_bytes > max_bytes:
        log.warning(
            "Persistence skipped: working dataset is {} bytes, over the {} byte limit",
            memory_bytes,
            max_bytes,
        )
        return False
    working_path, original_path, manifest_path = _paths(directory)
    try:
        working_path.parent.mkdir(parents=True, exist_ok=True)
        # Parquet files first, manifest last: the manifest is the commit
        # marker, so load_state() only trusts a complete set of files.
        # Write via temporary files + replace so a crash mid-write never
        # leaves a half-written parquet behind.
        tmp_working = working_path.with_suffix(".parquet.tmp")
        tmp_original = original_path.with_suffix(".parquet.tmp")
        df.to_parquet(tmp_working, engine="pyarrow", index=True)
        tmp_working.replace(working_path)
        if df_original is not None:
            df_original.to_parquet(tmp_original, engine="pyarrow", index=True)
            tmp_original.replace(original_path)
        elif original_path.exists():
            original_path.unlink()
        manifest = {
            "df_name": df_name or "",
            "df_source": str(df_source) if df_source is not None else None,
            "cleaning_history": cleaning_history or [],
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, default=str), encoding="utf-8"
        )
    except Exception as exc:
        log.warning("Failed to persist dataset state: {}", exc)
        return False
    log.debug("Persisted dataset state for {}", df_name or "")
    return True


def load_state(directory: Path | None = None) -> dict[str, Any] | None:
    """Restore a previously persisted dataset state, or None.

    Returns a dict with ``df``, ``df_original``, ``df_name``,
    ``df_source``, and ``cleaning_history``. The two DataFrames are read
    from separate files, so mutating one never affects the other. Returns
    None when nothing is persisted, the set is incomplete, or any read
    fails. Never raises.
    """
    working_path, original_path, manifest_path = _paths(directory)
    if not (working_path.exists() and manifest_path.exists()):
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        df = pd.read_parquet(working_path, engine="pyarrow")
        df_original = (
            pd.read_parquet(original_path, engine="pyarrow")
            if original_path.exists()
            else df.copy(deep=True)
        )
        history = manifest.get("cleaning_history", [])
        if not isinstance(history, list):
            history = []
        return {
            "df": df,
            "df_original": df_original,
            "df_name": manifest.get("df_name") or "",
            "df_source": manifest.get("df_source"),
            "cleaning_history": history,
        }
    except Exception as exc:
        log.warning("Failed to restore persisted dataset state: {}", exc)
        return None


def clear_state(directory: Path | None = None) -> bool:
    """Remove all persisted dataset files. Returns True on success.

    Missing files are fine; a removal failure is logged and returns False.
    Never raises.
    """
    try:
        for path in _paths(directory):
            path.unlink(missing_ok=True)
    except Exception as exc:
        log.warning("Failed to clear persisted dataset state: {}", exc)
        return False
    log.debug("Cleared persisted dataset state")
    return True
