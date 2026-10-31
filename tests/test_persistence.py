"""Tests for core/persistence.py.

All state is redirected to a temporary directory via the ``directory``
parameter, so these tests never touch the real ``data/persisted/`` folder
or any file under ``data/uploads/``.
"""

import tempfile
from pathlib import Path

import pandas as pd
import pandas.testing as tm

from core.persistence import clear_state, load_state, save_state


def _working() -> pd.DataFrame:
    return pd.DataFrame({"name": ["Ada", "Grace"], "age": [36, 41]})


def _original() -> pd.DataFrame:
    return pd.DataFrame({"name": ["Ada", "Grace", "Linus"], "age": [36, 41, 54]})


def test_load_state_returns_none_when_nothing_persisted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert load_state(directory=Path(tmp)) is None


def test_round_trip_restores_frames_name_source_and_history() -> None:
    history = [{"operation": "Drop missing values", "rows_before": 3, "rows_after": 2}]
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        assert save_state(
            _working(),
            _original(),
            "people.csv",
            "/somewhere/people.csv",
            history,
            directory=directory,
        )
        assert (directory / "working.parquet").exists()
        assert (directory / "original.parquet").exists()
        assert (directory / "manifest.json").exists()
        restored = load_state(directory=directory)
        assert restored is not None
        tm.assert_frame_equal(restored["df"], _working())
        tm.assert_frame_equal(restored["df_original"], _original())
        assert restored["df_name"] == "people.csv"
        assert restored["df_source"] == "/somewhere/people.csv"
        assert restored["cleaning_history"] == history


def test_restored_working_mutation_does_not_change_restored_original() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        save_state(_working(), _original(), "people.csv", None, [], directory=directory)
        restored = load_state(directory=directory)
        assert restored is not None
        restored["df"].loc[0, "age"] = 999
        restored["df"] = pd.concat(
            [restored["df"], pd.DataFrame({"name": ["New"], "age": [1]})],
            ignore_index=True,
        )
        # The restored original is a separate object read from its own file.
        tm.assert_frame_equal(restored["df_original"], _original())


def test_clear_state_removes_persisted_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        save_state(_working(), _original(), "people.csv", None, [], directory=directory)
        assert load_state(directory=directory) is not None
        assert clear_state(directory=directory)
        assert not (directory / "working.parquet").exists()
        assert not (directory / "original.parquet").exists()
        assert not (directory / "manifest.json").exists()
        assert load_state(directory=directory) is None
        # Clearing an already-empty directory is still a success, not an error.
        assert clear_state(directory=directory)


def test_oversized_frame_is_skipped() -> None:
    # A tiny threshold override stands in for the 50 MB production limit,
    # so the test never needs to allocate tens of megabytes.
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        assert not save_state(
            _working(),
            _original(),
            "people.csv",
            None,
            [],
            max_bytes=1,
            directory=directory,
        )
        assert load_state(directory=directory) is None


def test_save_state_with_no_frame_returns_false_and_writes_nothing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        assert not save_state(None, None, "", None, [], directory=directory)
        assert load_state(directory=directory) is None
