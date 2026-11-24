"""Tests for core/statistics.py and core/analyzer.py."""

import pandas as pd

from core.analyzer import business_summary, dataset_overview, eda_report, key_insights
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


def _shop_frame() -> pd.DataFrame:
    """Two categories over 12 months, values rising through the year."""
    rows = []
    for i, month in enumerate(pd.date_range("2025-01-01", periods=12, freq="MS")):
        rows.append({"date": month.strftime("%Y-%m-%d"), "cat": "A", "sales": 100 + i * 10})
        rows.append({"date": month.strftime("%Y-%m-%d"), "cat": "B", "sales": 50 + i * 5})
    return pd.DataFrame(rows)


def test_business_summary_shop() -> None:
    lines = business_summary(_shop_frame())
    joined = "\n".join(lines)
    # Top category A: sum(100..210 step 10) = 1,860.
    assert any("A" in line and "1,860" in line for line in lines)
    # Best month 2025-12 (210 + 105 = 315), worst 2025-01 (100 + 50 = 150).
    assert any("2025-12" in line and "315" in line for line in lines)
    assert any("2025-01" in line and "150" in line for line in lines)
    assert "صعودی" in joined  # rising trend
    assert any("210" in line for line in lines)  # largest single sale
    assert lines  # at least the sentences above


def test_business_summary_english() -> None:
    lines = business_summary(_shop_frame(), lang="en")
    joined = "\n".join(lines)
    assert "rising" in joined
    assert "'A'" in joined


def test_business_summary_no_numeric() -> None:
    lines = business_summary(pd.DataFrame({"c": ["x", "y", "x"]}))
    assert len(lines) == 1
    assert "ستون عددی" in lines[0]


def test_business_summary_single_row_has_no_trend() -> None:
    frame = pd.DataFrame({"date": ["2025-01-01"], "cat": ["A"], "sales": [42]})
    lines = business_summary(frame)
    assert any("42" in line for line in lines)  # largest single value
    assert not any("روند" in line for line in lines)


def test_business_summary_explicit_columns() -> None:
    frame = pd.DataFrame(
        {
            "when": ["2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01"],
            "city": ["Tehran", "Tehran", "Shiraz", "Shiraz"],
            "amount": [10, 20, 100, 200],
            "other": [1, 1, 1, 1],
        }
    )
    lines = business_summary(
        frame, value_column="amount", category_column="city", date_column="when"
    )
    assert any("Shiraz" in line for line in lines)
    assert any("2025-04-01" in line for line in lines)  # best (only) date period
