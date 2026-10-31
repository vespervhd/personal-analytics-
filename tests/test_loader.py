"""Tests for core/data_loader.py.

Uploads are redirected to a tmp directory by monkeypatching the loader's
SETTINGS (the production API keeps its clean signature). Parquet/XLS tests
are skipped when their engine is unavailable; the venv run exercises them.
"""

from pathlib import Path
import tempfile

import pandas as pd

import core.data_loader as loader
from config import Settings
from core.data_loader import (
    DataLoadError,
    dataset_summary,
    detect_encoding,
    load_from_bytes,
    load_from_path,
)

try:
    import pyarrow  # noqa: F401

    HAS_PYARROW = True
except ImportError:
    HAS_PYARROW = False

try:
    import xlrd  # noqa: F401

    HAS_XLRD = True
except ImportError:
    HAS_XLRD = False


def _tmp_settings(tmp: str) -> Settings:
    root = Path(tmp)
    return Settings(
        uploads_dir=root / "uploads",
        exports_dir=root / "exports",
        database_dir=root / "database",
        logs_dir=root / "logs",
    )


def test_csv_load_from_bytes_and_saved_copy() -> None:
    csv = b"name,age\nAda,36\nGrace,41\n"
    with tempfile.TemporaryDirectory() as tmp:
        old = loader.SETTINGS
        loader.SETTINGS = _tmp_settings(tmp)
        try:
            df, saved = load_from_bytes("people.csv", csv)
            # Assertions must run inside the tmp-dir context: cleanup
            # deletes the saved file as soon as the block exits.
            assert list(df.columns) == ["name", "age"]
            assert len(df) == 2
            assert saved.exists() and saved.read_bytes() == csv
        finally:
            loader.SETTINGS = old


def test_csv_latin1_encoding_detected() -> None:
    raw = "city\ncafé\n".encode("latin-1")
    assert detect_encoding(raw) == "latin-1"
    with tempfile.TemporaryDirectory() as tmp:
        old = loader.SETTINGS
        loader.SETTINGS = _tmp_settings(tmp)
        try:
            df, _ = load_from_bytes("cities.csv", raw)
        finally:
            loader.SETTINGS = old
    assert df["city"].iloc[0] == "café"


def test_json_and_xlsx_load() -> None:
    frame = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        json_path = root / "data.json"
        frame.to_json(json_path)
        assert load_from_path(json_path).shape == (2, 2)
        xlsx_path = root / "data.xlsx"
        frame.to_excel(xlsx_path, index=False)
        assert load_from_path(xlsx_path).shape == (2, 2)


def test_parquet_load() -> None:
    if not HAS_PYARROW:
        print("SKIP parquet test (pyarrow not installed)")
        return
    frame = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "data.parquet"
        frame.to_parquet(path)
        assert load_from_path(path).shape == (2, 2)


def test_xls_invalid_content_raises_useful_error() -> None:
    # No .xls writer is available in the stack, so the success path needs
    # a real .xls file; here the parse-failure path is verified instead.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "broken.xls"
        path.write_bytes(b"this is not a spreadsheet")
        try:
            load_from_path(path)
        except DataLoadError as exc:
            assert "xls" in str(exc).lower()
            return
    raise AssertionError("Expected DataLoadError for invalid .xls content")


def test_empty_file_and_bad_extension_errors() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        empty = Path(tmp) / "empty.csv"
        empty.write_bytes(b"")
        for bad in (empty,):
            try:
                load_from_path(bad)
            except DataLoadError:
                pass
            else:
                raise AssertionError("Expected DataLoadError for empty file")
    try:
        load_from_bytes("notes.txt", b"hello")
    except Exception as exc:
        assert "Unsupported" in str(exc)
        return
    raise AssertionError("Expected validation error for .txt upload")


def test_duplicate_upload_names_stay_unique() -> None:
    csv = b"x\n1\n"
    with tempfile.TemporaryDirectory() as tmp:
        old = loader.SETTINGS
        loader.SETTINGS = _tmp_settings(tmp)
        try:
            _, first = load_from_bytes("data.csv", csv)
            _, second = load_from_bytes("data.csv", csv)
            assert first != second and first.exists() and second.exists()
        finally:
            loader.SETTINGS = old


def test_dataset_summary() -> None:
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    summary = dataset_summary(df)
    assert summary["rows"] == 3 and summary["columns"] == 2
    assert summary["column_names"] == ["a", "b"]
    # Tiny frames round to 0.0 MB, so the exact byte count is the assertion.
    assert summary["memory_bytes"] > 0


def test_xlrd_presence_noted() -> None:
    # Documents the .xls engine situation for the venv run.
    print("xlrd available:", HAS_XLRD)
