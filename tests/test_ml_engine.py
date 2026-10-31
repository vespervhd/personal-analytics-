"""Tests for core/ml_engine.py (small synthetic data, fixed seeds)."""

import numpy as np
import pandas as pd

from core.ml_engine import (
    MLEngineError,
    classify,
    cluster_kmeans,
    detect_anomalies_isolation_forest,
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
