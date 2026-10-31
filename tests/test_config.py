"""Phase 1 tests: configuration defaults and validation.

Pure-assert tests: runnable with plain ``python`` (see README) or pytest.
"""

from pathlib import Path
import tempfile

from config import ALLOWED_EXTENSIONS, SETTINGS, Settings


def test_allowed_extensions_cover_all_import_formats() -> None:
    assert {"csv", "xlsx", "xls", "json", "parquet"} <= set(ALLOWED_EXTENSIONS)


def test_default_max_upload_is_positive() -> None:
    assert SETTINGS.max_upload_mb > 0
    assert SETTINGS.max_upload_bytes == SETTINGS.max_upload_mb * 1024 * 1024


def test_invalid_max_upload_is_rejected() -> None:
    try:
        Settings(max_upload_mb=0)
    except ValueError:
        return
    raise AssertionError("Settings(max_upload_mb=0) should raise ValueError")


def test_db_url_points_inside_database_dir() -> None:
    assert SETTINGS.db_path.parent == SETTINGS.database_dir
    assert SETTINGS.db_url == f"sqlite:///{SETTINGS.db_path}"


def test_ensure_directories_creates_the_tree() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        settings = Settings(
            uploads_dir=root / "uploads",
            exports_dir=root / "exports",
            database_dir=root / "database",
            logs_dir=root / "logs",
        )
        settings.ensure_directories()
        for directory in (
            settings.uploads_dir,
            settings.exports_dir,
            settings.database_dir,
            settings.logs_dir,
        ):
            assert directory.is_dir()
