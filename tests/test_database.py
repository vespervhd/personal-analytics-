"""Tests for database/connection.py, models.py, repository.py.

Runs against a tmp SQLite file by swapping the connection module's
SETTINGS. Skipped when SQLAlchemy is unavailable (the venv run covers it).
"""

from pathlib import Path
import tempfile

from config import Settings

try:
    import sqlalchemy  # noqa: F401

    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False


def test_crud_roundtrip() -> None:
    if not HAS_SQLALCHEMY:
        print("SKIP database tests (sqlalchemy not installed)")
        return
    import database.connection as connection
    from database.repository import (
        get_dataset,
        get_preference,
        list_datasets,
        record_analysis,
        record_cleaning,
        record_dataset,
        record_model_config,
        record_report,
        set_preference,
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        settings = Settings(
            uploads_dir=root / "uploads",
            exports_dir=root / "exports",
            database_dir=root / "database",
            logs_dir=root / "logs",
        )
        old_settings, old_engine = connection.SETTINGS, connection._engine
        connection.SETTINGS = settings
        connection._engine = None
        connection._SessionFactory = None
        try:
            connection.init_db()
            with connection.get_session() as session:
                ds = record_dataset(
                    session, filename="a.csv", file_format="csv", rows=10,
                    columns=3, dtypes={"x": "int64"}, saved_path="/tmp/a.csv",
                    file_size_bytes=123,
                )
                assert ds.id is not None
                assert get_dataset(session, ds.id).filename == "a.csv"
                assert len(list_datasets(session)) == 1
                op = record_cleaning(
                    session, operation="drop_missing", parameters={},
                    rows_before=10, rows_after=8, dataset_id=ds.id,
                )
                assert op.dataset_id == ds.id
                set_preference(session, "theme", {"mode": "dark"})
                assert get_preference(session, "theme") == {"mode": "dark"}
                assert get_preference(session, "missing", {"d": 1}) == {"d": 1}
                rep = record_report(session, report_format="pdf", path="/tmp/r.pdf",
                                    dataset_id=ds.id)
                assert rep.path == "/tmp/r.pdf"
                model = record_model_config(
                    session, name="iso", model_type="isolation_forest",
                    parameters={"contamination": 0.1}, dataset_id=ds.id,
                )
                assert model.model_type == "isolation_forest"
                hist = record_analysis(
                    session, analysis_type="eda", parameters={},
                    result_summary={"rows": 10}, dataset_id=ds.id,
                )
                assert hist.result_summary["rows"] == 10
        finally:
            connection.SETTINGS = old_settings
            connection._engine = old_engine
            connection._SessionFactory = None
