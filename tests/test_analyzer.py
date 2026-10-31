"""Tests for core/statistics.py and core/analyzer.py."""

import pandas as pd

from core.analyzer import dataset_overview, eda_report, key_insights
from core.statistics import (
    StatisticsError,
    column_summary,
    correlation_matrix,
    describe_numeric,
    distribution_analysis,
    ols_regression,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "a": [1, 2, 3, 4, 5, 6],
            "b": [2, 4, 6, 8, 10, 12],
            "c": ["x", "y", "x", "y", "x", "y"],
        }
    )


def test_describe_numeric_and_column_summary() -> None:
    summary = describe_numeric(pd.Series([1, 2, 3, 4]))
    assert summary["mean"] == 2.5 and summary["median"] == 2.5
    assert summary["min"] == 1 and summary["max"] == 4
    columns = column_summary(_frame())
    assert columns["a"]["type"] == "numeric"
    assert columns["c"]["type"] == "categorical"
    assert columns["c"]["unique"] == 2


def test_correlation_matrix_and_errors() -> None:
    corr = correlation_matrix(_frame(), ["a", "b"])
    assert round(corr.loc["a", "b"], 6) == 1.0
    try:
        correlation_matrix(_frame(), ["a"])
    except StatisticsError:
        pass
    else:
        raise AssertionError("Expected StatisticsError for a single column")


def test_distribution_analysis() -> None:
    detail = distribution_analysis(pd.Series([1, 2, 3, 4, 5, 6, 7, 8]))
    assert detail["shapiro_p_value"] is not None
    assert detail["skew"] is not None


def test_eda_report_and_insights() -> None:
    df = _frame()
    report = eda_report(df)
    assert report["overview"]["rows"] == 6
    assert report["correlation"] is not None
    insights = key_insights(df, report)
    assert any("Strongest correlation" in text for text in insights)


def test_dataset_overview_counts() -> None:
    df = pd.DataFrame({"a": [1, 1, 2], "b": [None, 2, 3]})
    overview = dataset_overview(df)
    assert overview["duplicate_rows"] == 0  # rows differ in column b
    assert overview["total_missing"] == 1


def test_ols_regression() -> None:
    df = pd.DataFrame({"y": [3, 5, 7, 9], "x": [1, 2, 3, 4]})
    result = ols_regression(df, "y", ["x"])
    assert result["rows_used"] == 4
    assert abs(result["coefficients"]["x"] - 2.0) < 1e-6
    assert result["r_squared"] is not None and result["r_squared"] > 0.99
