"""Machine learning: anomaly detection, clustering, classification.

Every function is an explicit, user-triggered operation that returns a
plain, JSON-safe result dict — no training ever happens implicitly, and
nothing here touches the dashboard. Scores, counts, and top rows are
reported in understandable terms; raw model objects are never returned.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from utils.logger import get_logger

log = get_logger("ml_engine")

#: Anomaly rows included in full in results (the total count is always exact).
MAX_ANOMALY_ROWS = 50


class MLEngineError(ValueError):
    """Raised when an ML operation cannot run on the given data."""


def _json_safe(value):
    """Convert numpy scalars/arrays to plain Python (NaN -> None)."""
    if isinstance(value, np.ndarray):
        return [_json_safe(v) for v in value.tolist()]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        number = float(value)
        return None if np.isnan(number) or np.isinf(number) else number
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def _numeric_frame(df: pd.DataFrame, columns: list[str] | None) -> pd.DataFrame:
    numeric = df.select_dtypes(include="number")
    targets = columns if columns else list(numeric.columns)
    unknown = [c for c in targets if c not in df.columns]
    if unknown:
        raise MLEngineError(f"Unknown columns: {unknown}")
    non_numeric = [c for c in targets if c not in numeric.columns]
    if non_numeric:
        raise MLEngineError(f"This operation needs numeric columns: {non_numeric}")
    if not targets:
        raise MLEngineError("No numeric columns available.")
    return df[targets]


def detect_anomalies_isolation_forest(
    df: pd.DataFrame,
    columns: list[str] | None = None,
    contamination: float = 0.1,
    random_state: int = 42,
) -> dict:
    """Isolation Forest anomaly detection.

    Returns the anomaly count, their index labels, anomaly scores, and
    the first :data:`MAX_ANOMALY_ROWS` anomaly rows as records.
    """
    if not 0 < contamination <= 0.5:
        raise MLEngineError("contamination must be in (0, 0.5].")
    frame = _numeric_frame(df, columns)
    work = frame.dropna()
    dropped = len(frame) - len(work)
    if len(work) < 10:
        raise MLEngineError("Isolation Forest needs at least 10 complete rows.")
    model = IsolationForest(contamination=contamination, random_state=random_state)
    labels = model.fit_predict(work)
    scores = model.decision_function(work)
    anomaly_mask = labels == -1
    anomaly_index = [str(i) for i in work.index[anomaly_mask]]
    anomaly_rows = work[anomaly_mask].head(MAX_ANOMALY_ROWS).to_dict(orient="records")
    result = {
        "method": "isolation_forest",
        "columns": list(frame.columns),
        "contamination": contamination,
        "rows_analysed": int(len(work)),
        "rows_dropped_missing": int(dropped),
        "anomalies": int(anomaly_mask.sum()),
        "anomaly_index": anomaly_index,
        "anomaly_scores": [_json_safe(s) for s in scores[anomaly_mask][:MAX_ANOMALY_ROWS]],
        "anomaly_rows": [{str(k): _json_safe(v) for k, v in row.items()} for row in anomaly_rows],
    }
    log.info("isolation_forest found {} anomalies in {} rows", result["anomalies"], len(work))
    return result


def zscore_outliers(
    df: pd.DataFrame, columns: list[str] | None = None, threshold: float = 3.0
) -> dict:
    """Flag rows where any analysed column exceeds ``threshold`` std devs."""
    if threshold <= 0:
        raise MLEngineError("threshold must be positive.")
    frame = _numeric_frame(df, columns)
    work = frame.dropna()
    means, stds = work.mean(), work.std(ddof=0)
    stds = stds.replace(0, np.nan)
    z_scores = (work - means) / stds
    mask = (z_scores.abs() > threshold).any(axis=1)
    result = {
        "method": "zscore",
        "columns": list(frame.columns),
        "threshold": threshold,
        "rows_analysed": int(len(work)),
        "rows_dropped_missing": int(len(frame) - len(work)),
        "outliers": int(mask.sum()),
        "outlier_index": [str(i) for i in work.index[mask]],
        "per_column": {
            str(col): int((z_scores[col].abs() > threshold).sum()) for col in frame.columns
        },
    }
    log.info("zscore_outliers found {} outliers", result["outliers"])
    return result


def cluster_kmeans(
    df: pd.DataFrame,
    columns: list[str] | None = None,
    n_clusters: int = 3,
    random_state: int = 42,
) -> dict:
    """K-Means clustering on standardised numeric columns.

    Centres are inverse-transformed back to the original units so the
    result is readable. Labels align with the input row order.
    """
    frame = _numeric_frame(df, columns)
    work = frame.dropna()
    dropped = len(frame) - len(work)
    if n_clusters < 2:
        raise MLEngineError("n_clusters must be at least 2.")
    if len(work) <= n_clusters:
        raise MLEngineError("Need more complete rows than clusters.")
    scaler = StandardScaler()
    scaled = scaler.fit_transform(work)
    model = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
    labels = model.fit_predict(scaled)
    centres = scaler.inverse_transform(model.cluster_centers_)
    sizes = pd.Series(labels).value_counts().sort_index()
    result = {
        "method": "kmeans",
        "columns": list(frame.columns),
        "n_clusters": n_clusters,
        "rows_clustered": int(len(work)),
        "rows_dropped_missing": int(dropped),
        "inertia": _json_safe(model.inertia_),
        "cluster_sizes": {int(k): int(v) for k, v in sizes.items()},
        "centres": {
            str(col): {int(i): _json_safe(centres[i, j]) for i in range(n_clusters)}
            for j, col in enumerate(frame.columns)
        },
        "labels": [int(label) for label in labels],
    }
    log.info("kmeans fitted {} clusters on {} rows", n_clusters, len(work))
    return result


def classify(
    df: pd.DataFrame,
    target: str,
    features: list[str] | None = None,
    model: str = "random_forest",
    test_size: float = 0.25,
    random_state: int = 42,
) -> dict:
    """Basic classification with a train/test split.

    ``model`` is ``"random_forest"`` or ``"xgboost"``. Categorical
    features are one-hot encoded; rows with missing values in the used
    columns are dropped and the count is reported. The target must be
    categorical or low-cardinality (<= 20 distinct values).
    """
    if target not in df.columns:
        raise MLEngineError(f"Unknown target column: {target}")
    if model not in ("random_forest", "xgboost"):
        raise MLEngineError("model must be 'random_forest' or 'xgboost'.")
    if not 0 < test_size < 1:
        raise MLEngineError("test_size must be between 0 and 1.")
    feature_cols = features if features else [c for c in df.columns if c != target]
    unknown = [c for c in feature_cols if c not in df.columns]
    if unknown:
        raise MLEngineError(f"Unknown feature columns: {unknown}")
    target_series = df[target]
    if target_series.nunique(dropna=True) > 20:
        raise MLEngineError(
            f"Target '{target}' has more than 20 distinct values; "
            "classification needs a categorical or low-cardinality target."
        )
    work = df[[target] + feature_cols].dropna()
    dropped = len(df) - len(work)
    if len(work) < 20:
        raise MLEngineError("Classification needs at least 20 complete rows.")
    X = pd.get_dummies(work[feature_cols], drop_first=False)
    y = work[target].astype(str)
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, stratify=y
        )
    except ValueError:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state
        )
    if model == "random_forest":
        estimator = RandomForestClassifier(random_state=random_state)
    else:
        try:
            from xgboost import XGBClassifier
        except ImportError as exc:
            raise MLEngineError(
                "XGBoost is not installed; choose random_forest instead."
            ) from exc
        estimator = XGBClassifier(eval_metric="mlogloss")
    estimator.fit(X_train, y_train)
    predictions = estimator.predict(X_test)
    labels = sorted(y.unique())
    matrix = confusion_matrix(y_test, predictions, labels=labels)
    report = classification_report(y_test, predictions, labels=labels,
                                   output_dict=True, zero_division=0)
    importances = {}
    if hasattr(estimator, "feature_importances_"):
        order = np.argsort(estimator.feature_importances_)[::-1][:10]
        importances = {
            str(X.columns[i]): _json_safe(estimator.feature_importances_[i]) for i in order
        }
    result = {
        "method": model,
        "target": target,
        "features": list(feature_cols),
        "rows_used": int(len(work)),
        "rows_dropped_missing": int(dropped),
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "accuracy": _json_safe(accuracy_score(y_test, predictions)),
        "labels": labels,
        "confusion_matrix": {
            str(row): {str(col): int(val) for col, val in zip(labels, row_values)}
            for row, row_values in zip(labels, matrix)
        },
        "per_class": {
            label: {
                "precision": _json_safe(metrics["precision"]),
                "recall": _json_safe(metrics["recall"]),
                "f1": _json_safe(metrics["f1-score"]),
                "support": int(metrics["support"]),
            }
            for label, metrics in report.items()
            if label in labels
        },
        "top_feature_importances": importances,
    }
    log.info("classify ({}) accuracy {}", model, result["accuracy"])
    return result
