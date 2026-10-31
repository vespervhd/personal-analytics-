"""Tests for core/export.py (cleaned-data Excel export)."""

import io

import pandas as pd
import pandas.testing as tm
import pytest

from core.export import dataframe_to_xlsx_bytes


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "name": ["A", "B", "C"],
            "age": [25, 30, 40],
            "score": [1.5, 2.5, 3.5],
        }
    )


def test_returns_non_empty_zip_bytes() -> None:
    data = dataframe_to_xlsx_bytes(_frame())
    assert isinstance(data, bytes)
    assert len(data) > 0
    assert data[:2] == b"PK"


def test_round_trips_values_and_columns() -> None:
    df = _frame()
    before = df.copy(deep=True)
    data = dataframe_to_xlsx_bytes(df)
    round_tripped = pd.read_excel(io.BytesIO(data), engine="openpyxl")
    tm.assert_frame_equal(round_tripped, df)
    # Export must not modify its input.
    tm.assert_frame_equal(df, before)


def test_empty_input_raises_value_error() -> None:
    with pytest.raises(ValueError):
        dataframe_to_xlsx_bytes(pd.DataFrame())
    with pytest.raises(ValueError):
        dataframe_to_xlsx_bytes(pd.DataFrame({"a": []}))
    with pytest.raises(ValueError):
        dataframe_to_xlsx_bytes(pd.DataFrame(index=[0, 1]))
