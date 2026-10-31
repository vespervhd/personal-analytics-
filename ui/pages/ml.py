"""Machine Learning page: anomaly detection, clustering, classification.

Nothing trains on page load — every model runs only when its "Run"
button is pressed, and results persist in session state until replaced.
"""

from __future__ import annotations

import streamlit as st

from core.ml_engine import (
    MLEngineError,
    classify,
    cluster_kmeans,
    detect_anomalies_isolation_forest,
    zscore_outliers,
)
from core.visualization import scatter_plot
from database.connection import get_session, init_db
from database.repository import record_model_config
from ui.components.common import require_dataset


def _save_model_config(name: str, model_type: str, parameters: dict) -> None:
    dataset_id = st.session_state.get("dataset_id")
    try:
        init_db()
        with get_session() as session:
            record_model_config(
                session, name=name, model_type=model_type,
                parameters=parameters, dataset_id=dataset_id,
            )
        st.success(f"Model configuration '{name}' saved.")
    except Exception as exc:
        st.error(f"Could not save model configuration: {exc}")


def render() -> None:
    st.header("Machine Learning")
    df = require_dataset()
    if df is None:
        return

    numeric = [str(c) for c in df.select_dtypes(include="number").columns]

    st.subheader("Anomaly detection — Isolation Forest")
    if numeric:
        columns = st.multiselect("Numeric columns", options=numeric, default=numeric,
                                 key="iso_cols")
        contamination = st.slider("Expected anomaly share", 0.01, 0.5, 0.1, 0.01,
                                  key="iso_cont")
        if st.button("Run anomaly detection"):
            try:
                st.session_state.ml_anomalies = detect_anomalies_isolation_forest(
                    df, columns or None, contamination=contamination
                )
            except MLEngineError as exc:
                st.error(f"Anomaly detection failed: {exc}")
        result = st.session_state.get("ml_anomalies")
        if result:
            st.write(f"Analysed **{result['rows_analysed']:,}** rows "
                     f"({result['rows_dropped_missing']} dropped for missing values).")
            st.write(f"Anomalies found: **{result['anomalies']}** "
                     f"(contamination={result['contamination']}).")
            if result["anomaly_rows"]:
                st.dataframe(result["anomaly_rows"], use_container_width=True)
            if st.button("Save this anomaly configuration"):
                _save_model_config("isolation_forest", "isolation_forest",
                                   {"columns": result["columns"],
                                    "contamination": result["contamination"]})
    else:
        st.write("Anomaly detection needs numeric columns.")

    st.subheader("Anomaly detection — Z-score")
    if numeric:
        z_cols = st.multiselect("Numeric columns", options=numeric, default=numeric,
                                key="z_cols")
        threshold = st.slider("Std-dev threshold", 1.0, 5.0, 3.0, 0.5, key="z_thresh")
        if st.button("Run Z-score detection"):
            try:
                st.session_state.ml_zscores = zscore_outliers(df, z_cols or None,
                                                              threshold=threshold)
            except MLEngineError as exc:
                st.error(f"Z-score detection failed: {exc}")
        z_result = st.session_state.get("ml_zscores")
        if z_result:
            st.write(f"Outliers found: **{z_result['outliers']}** "
                     f"(threshold={z_result['threshold']} std devs).")
            st.dataframe(z_result["per_column"], use_container_width=True)
    else:
        st.write("Z-score detection needs numeric columns.")

    st.subheader("Clustering — K-Means")
    if len(numeric) >= 1:
        n_clusters = st.slider("Number of clusters", 2, 10, 3, key="km_k")
        if st.button("Run clustering"):
            try:
                st.session_state.ml_clusters = cluster_kmeans(
                    df, numeric, n_clusters=n_clusters
                )
            except MLEngineError as exc:
                st.error(f"Clustering failed: {exc}")
        clusters = st.session_state.get("ml_clusters")
        if clusters:
            st.write(f"Inertia: **{clusters['inertia']}** · "
                     f"Rows clustered: **{clusters['rows_clustered']:,}**")
            st.dataframe(
                {"cluster": list(clusters["cluster_sizes"]),
                 "size": list(clusters["cluster_sizes"].values())},
                use_container_width=True,
            )
            if len(numeric) >= 2:
                # Labels cover only complete rows, so plot those same rows.
                plotted = df[numeric].dropna().copy()
                plotted["cluster"] = clusters["labels"]
                st.plotly_chart(
                    scatter_plot(plotted, numeric[0], numeric[1], color="cluster"),
                    use_container_width=True,
                )
            if st.button("Save this clustering configuration"):
                _save_model_config("kmeans", "kmeans",
                                   {"columns": clusters["columns"],
                                    "n_clusters": clusters["n_clusters"]})
    else:
        st.write("Clustering needs at least one numeric column.")

    st.subheader("Classification")
    categorical = [
        str(c) for c in df.columns if df[c].nunique(dropna=True) <= 20
    ]
    if categorical:
        target = st.selectbox("Target column", options=categorical, key="clf_target")
        features = st.multiselect(
            "Features", options=[c for c in df.columns if c != target],
            key="clf_features",
        )
        model = st.selectbox("Model", options=["random_forest", "xgboost"],
                             key="clf_model")
        if st.button("Train and evaluate"):
            try:
                st.session_state.ml_classification = classify(
                    df, target, features or None, model=model
                )
            except MLEngineError as exc:
                st.error(f"Classification failed: {exc}")
        clf = st.session_state.get("ml_classification")
        if clf:
            st.write(f"Accuracy: **{clf['accuracy']:.3f}** on "
                     f"{clf['test_rows']} test rows "
                     f"({clf['rows_dropped_missing']} rows dropped for missing values).")
            st.write("Confusion matrix (rows = actual, columns = predicted):")
            st.dataframe(clf["confusion_matrix"], use_container_width=True)
            st.write("Per-class report:")
            st.dataframe(clf["per_class"], use_container_width=True)
            if clf["top_feature_importances"]:
                st.write("Top feature importances:")
                st.dataframe(clf["top_feature_importances"], use_container_width=True)
            if st.button("Save this classification configuration"):
                _save_model_config(f"classifier_{clf['target']}", clf["method"],
                                   {"target": clf["target"],
                                    "features": clf["features"]})
    else:
        st.write("Classification needs a categorical or low-cardinality target column.")
