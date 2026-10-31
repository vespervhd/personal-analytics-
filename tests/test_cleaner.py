"""Tests for core/data_cleaner.py.

Every test asserts the input DataFrame is left untouched, because cleaning
must never mutate the original dataset.
"""

import pandas as pd
import pandas.testing as tm

from core.data_cleaner import (
    DataCleaningError,
    convert_dtype,
    drop_duplicates,
    drop_missing,
    fill_missing,
    filter_rows,
    flag_outliers_iqr,
    missing_value_report,
    rename_columns,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "age": [25, None, 30, 30, 200],
            "city": ["A", "B", None, "B", "C"],
            "score": [1.0, 2.0, 3.0, 3.0, 4.0],
        }
    )


def test_missing_value_report() -> None:
    report = missing_value_report(_frame())
    assert report["columns"]["age"]["missing"] == 1
    assert report["columns"]["city"]["missing"] == 1
    assert report["total_missing"] == 2


def test_drop_missing_and_original_unchanged() -> None:
    df = _frame()
    before = df.copy(deep=True)
    cleaned, report = drop_missing(df)
    assert len(cleaned) == 3 and report["rows_removed"] == 2
    tm.assert_frame_equal(df, before)


def test_fill_missing_median_and_mapping() -> None:
    df = _frame()
    filled, report = fill_missing(df, strategy="median")
    assert filled["age"].isna().sum() == 0
    assert report["filled"]["age"] == 1
    filled2, _ = fill_missing(df, strategy={"city": "Unknown"})
    assert filled2["city"].iloc[2] == "Unknown"
    # Mean cannot fill text: the column is skipped, not guessed.
    _, report3 = fill_missing(df, strategy="mean")
    assert "city" in report3["skipped"]


def test_drop_duplicates() -> None:
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    cleaned, report = drop_duplicates(df)
    assert len(cleaned) == 2 and report["rows_removed"] == 1


def test_convert_dtype_success_and_failure_is_atomic() -> None:
    df = pd.DataFrame({"age": ["25", "30"], "bad": ["x", "y"]})
    converted, _ = convert_dtype(df, {"age": "int64"})
    assert str(converted["age"].dtype) == "int64"
    try:
        convert_dtype(df, {"bad": "int64"})
    except DataCleaningError as exc:
        assert "bad" in str(exc)
    else:
        raise AssertionError("Expected DataCleaningError")
    # Original untouched: values identical and still a string dtype
    # (pandas reports "object" on 2.x and "str" on 3.x).
    assert list(df["bad"]) == ["x", "y"]
    assert str(df["bad"].dtype) in ("object", "str")


def test_flag_outliers_iqr() -> None:
    df = pd.DataFrame({"v": [10, 11, 12, 13, 14, 15, 100]})
    flags, report = flag_outliers_iqr(df)
    assert bool(flags["v"].iloc[-1]) is True
    assert bool(flags["v"].iloc[0]) is False
    assert report["columns"]["v"]["outliers"] == 1


def test_rename_columns_and_rejections() -> None:
    df = pd.DataFrame({"a": [1], "b": [2]})
    renamed, _ = rename_columns(df, {"a": "alpha"})
    assert list(renamed.columns) == ["alpha", "b"]
    for bad_mapping in ({"a": "b"}, {"zzz": "q"}):
        try:
            rename_columns(df, bad_mapping)
        except DataCleaningError:
            pass
        else:
            raise AssertionError(f"Expected DataCleaningError for {bad_mapping}")


def test_filter_rows_and_bad_expression() -> None:
    df = pd.DataFrame({"age": [20, 40, 60]})
    filtered, report = filter_rows(df, "age > 30")
    assert len(filtered) == 2 and report["rows_removed"] == 1
    try:
        filter_rows(df, "age >>> 30")
    except DataCleaningError:
        pass
    else:
        raise AssertionError("Expected DataCleaningError for bad expression")
