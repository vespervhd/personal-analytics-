"""Tests for core/ml_engine.py (small synthetic data, fixed seeds)."""

import numpy as np
import pandas as pd

from core.ml_engine import (
    MLEngineError,
    classify,
    cluster_kmeans,
    detect_anomalies_isolation_forest,
    forecast_series,
    zscore_outliers,
)


def test_isolation_forest_finds_clear_outlier() -> None:
    rng = np.random.default_rng(0)
    normal = rng.normal(0, 1, size=(100, 2))
    frame = pd.DataFrame(normal, columns=["x", "y"])
    frame.loc[100] = [50, 50]
    result = detect_anomalies_isolation_forest(frame, contamination=0.05)
    assert result["anomalies"] >= 1
    assert "100" in result["anomaly_index"]


def test_zscore_outliers() -> None:
    frame = pd.DataFrame({"v": [10, 11, 12, 13, 14, 15, 100]})
    result = zscore_outliers(frame, threshold=2.0)
    assert result["outliers"] >= 1


def test_kmeans_two_blobs() -> None:
    rng = np.random.default_rng(1)
    blob_a = rng.normal(0, 0.5, size=(20, 2))
    blob_b = rng.normal(10, 0.5, size=(20, 2))
    frame = pd.DataFrame(np.vstack([blob_a, blob_b]), columns=["x", "y"])
    result = cluster_kmeans(frame, n_clusters=2)
    assert sorted(result["cluster_sizes"].values()) == [20, 20]
    assert len(result["labels"]) == 40


def test_classification_separable() -> None:
    rng = np.random.default_rng(2)
    n = 60
    feature = np.concatenate([rng.normal(0, 0.5, n), rng.normal(10, 0.5, n)])
    label = ["low"] * n + ["high"] * n
    frame = pd.DataFrame({"feature": feature, "label": label})
    result = classify(frame, "label", ["feature"], model="random_forest")
    assert result["accuracy"] >= 0.9
    assert result["test_rows"] > 0


def test_ml_validation_errors() -> None:
    frame = pd.DataFrame({"a": [1, 2, 3]})
    for call in (
        lambda: detect_anomalies_isolation_forest(frame, contamination=0.9),
        lambda: cluster_kmeans(frame, n_clusters=1),
        lambda: classify(frame, "a", ["a"]),
    ):
        try:
            call()
        except MLEngineError:
            pass
        else:
            raise AssertionError("Expected MLEngineError")


def _monthly_frame() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    months = pd.date_range("2023-01-01", periods=36, freq="MS")
    trend = np.arange(36) * 5.0
    season = 20 * np.sin(2 * np.pi * np.arange(36) / 12)
    values = 100 + trend + season + rng.normal(0, 3, 36)
    return pd.DataFrame({"month": months, "sales": values})


def test_forecast_monthly_shape_and_dates() -> None:
    result = forecast_series(_monthly_frame(), "month", "sales", horizon=3)
    assert result["method"] == "holt_winters"
    assert result["points"] == 36
    assert len(result["forecast"]) == 3
    assert result["forecast_dates"] == ["2026-01-01", "2026-02-01", "2026-03-01"]
    assert result["history_dates"][-1] == "2025-12-01"
    assert all(isinstance(v, float) for v in result["forecast"])
    # Follows the upward trend: last history value is ~280, so the
    # forecast must stay above it instead of collapsing.
    assert result["forecast"][0] > result["history_values"][-1]
    assert result["note"] is None


def test_forecast_daily_weekly_season() -> None:
    rng = np.random.default_rng(1)
    days = pd.date_range("2025-01-01", periods=90, freq="D")
    values = 500 + np.arange(90) + 100 * np.sin(2 * np.pi * np.arange(90) / 7)
    values = values + rng.normal(0, 10, 90)
    frame = pd.DataFrame({"date": days, "amount": values})
    result = forecast_series(frame, "date", "amount", horizon=7)
    assert result["method"] == "holt_winters"
    assert len(result["forecast"]) == 7
    assert result["forecast_dates"][0] == "2025-04-01"
    assert all(v > 0 for v in result["forecast"])


def test_forecast_short_series_fallback() -> None:
    frame = pd.DataFrame(
        {
            "d": pd.date_range("2025-01-01", periods=5, freq="D"),
            "v": [1, 2, 3, 4, 5],
        }
    )
    result = forecast_series(frame, "d", "v")
    assert result["method"] == "insufficient_data"
    assert result["forecast"] == []
    assert result["forecast_dates"] == []
    assert result["note"] == "too_few_points"
    assert result["points"] == 5


def test_forecast_string_dates_and_duplicates() -> None:
    # String dates aggregate per day; duplicate dates are summed.
    frame = pd.DataFrame(
        {
            "date": [
                "2025-01-01",
                "2025-01-01",
                "2025-01-02",
                "2025-01-03",
                "2025-01-04",
                "2025-01-05",
                "2025-01-06",
                "2025-01-07",
                "2025-01-08",
                "2025-01-09",
            ],
            "v": [10, 5, 20, 30, 40, 50, 60, 70, 80, 90],
        }
    )
    result = forecast_series(frame, "date", "v", horizon=2)
    assert result["points"] == 9
    assert result["history_values"][0] == 15  # 10 + 5 on 2025-01-01
    assert len(result["forecast"]) == 2


def test_forecast_validation_errors() -> None:
    frame = pd.DataFrame({"d": pd.date_range("2025-01-01", periods=10, freq="D"), "v": range(10)})
    for call in (
        lambda: forecast_series(frame, "nope", "v"),
        lambda: forecast_series(frame, "d", "nope"),
        lambda: forecast_series(frame, "d", "v", horizon=0),
        lambda: forecast_series(frame, "d", "v", horizon=25),
        lambda: forecast_series(frame, "v", "v"),
    ):
        try:
            call()
        except MLEngineError:
            pass
        else:
            raise AssertionError("Expected MLEngineError")


def test_forecast_result_is_json_safe() -> None:
    import json

    result = forecast_series(_monthly_frame(), "month", "sales", horizon=3)
    json.dumps(result)
    assert result["history_dates"] and result["history_values"]
