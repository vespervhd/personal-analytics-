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
from ui.i18n import t


def _save_model_config(name: str, model_type: str, parameters: dict) -> None:
    dataset_id = st.session_state.get("dataset_id")
    try:
        init_db()
        with get_session() as session:
            record_model_config(
                session, name=name, model_type=model_type,
                parameters=parameters, dataset_id=dataset_id,
            )
        st.success(t("model_saved").format(name=name))
    except Exception as exc:
        st.error(t("model_save_error").format(err=exc))


def render() -> None:
    st.header(t("page_ml"))
    df = require_dataset()
    if df is None:
        return

    numeric = [str(c) for c in df.select_dtypes(include="number").columns]

    st.subheader(t("anomaly_if_sub"))
    if numeric:
        columns = st.multiselect(t("numeric_cols_label"), options=numeric, default=numeric,
                                 key="iso_cols")
        contamination = st.slider(t("anomaly_share"), 0.01, 0.5, 0.1, 0.01,
                                  key="iso_cont")
        if st.button(t("run_anomaly_btn")):
            try:
                st.session_state.ml_anomalies = detect_anomalies_isolation_forest(
                    df, columns or None, contamination=contamination
                )
            except MLEngineError as exc:
                st.error(t("anomaly_failed").format(err=exc))
        result = st.session_state.get("ml_anomalies")
        if result:
            st.write(t("analysed_line").format(rows=f"{result['rows_analysed']:,}", dropped=result["rows_dropped_missing"]))
            st.write(t("anomalies_found").format(n=result["anomalies"], c=result["contamination"]))
            if result["anomaly_rows"]:
                st.dataframe(result["anomaly_rows"], use_container_width=True)
            if st.button(t("save_anomaly_btn")):
                _save_model_config("isolation_forest", "isolation_forest",
                                   {"columns": result["columns"],
                                    "contamination": result["contamination"]})
    else:
        st.write(t("anomaly_needs"))

    st.subheader(t("anomaly_z_sub"))
    if numeric:
        z_cols = st.multiselect(t("numeric_cols_label"), options=numeric, default=numeric,
                                key="z_cols")
        threshold = st.slider(t("z_thresh"), 1.0, 5.0, 3.0, 0.5, key="z_thresh")
        if st.button(t("run_z_btn")):
            try:
                st.session_state.ml_zscores = zscore_outliers(df, z_cols or None,
                                                              threshold=threshold)
            except MLEngineError as exc:
                st.error(t("z_failed").format(err=exc))
        z_result = st.session_state.get("ml_zscores")
        if z_result:
            st.write(t("outliers_found").format(n=z_result["outliers"], t=z_result["threshold"]))
            st.dataframe(z_result["per_column"], use_container_width=True)
    else:
        st.write(t("z_needs"))

    st.subheader(t("clustering_sub"))
    if len(numeric) >= 1:
        n_clusters = st.slider(t("n_clusters"), 2, 10, 3, key="km_k")
        if st.button(t("run_clustering_btn")):
            try:
                st.session_state.ml_clusters = cluster_kmeans(
                    df, numeric, n_clusters=n_clusters
                )
            except MLEngineError as exc:
                st.error(t("clustering_failed").format(err=exc))
        clusters = st.session_state.get("ml_clusters")
        if clusters:
            st.write(t("inertia_line").format(v=clusters["inertia"], rows=f"{clusters['rows_clustered']:,}"))
            st.dataframe(
                {t("col_cluster"): list(clusters["cluster_sizes"]),
                 t("col_size"): list(clusters["cluster_sizes"].values())},
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
            if st.button(t("save_clustering_btn")):
                _save_model_config("kmeans", "kmeans",
                                   {"columns": clusters["columns"],
                                    "n_clusters": clusters["n_clusters"]})
    else:
        st.write(t("clustering_needs"))

    st.subheader(t("classification_sub"))
    categorical = [
        str(c) for c in df.columns if df[c].nunique(dropna=True) <= 20
    ]
    if categorical:
        target = st.selectbox(t("target_col_label"), options=categorical, key="clf_target")
        features = st.multiselect(
            t("features_label"), options=[c for c in df.columns if c != target],
            key="clf_features",
        )
        model = st.selectbox(t("model_label"), options=["random_forest", "xgboost"],
                             key="clf_model")
        if st.button(t("train_btn")):
            try:
                st.session_state.ml_classification = classify(
                    df, target, features or None, model=model
                )
            except MLEngineError as exc:
                st.error(t("clf_failed").format(err=exc))
        clf = st.session_state.get("ml_classification")
        if clf:
            st.write(t("accuracy_line").format(acc=f"{clf['accuracy']:.3f}", test=clf["test_rows"], dropped=clf["rows_dropped_missing"]))
            st.write(t("confusion_caption"))
            st.dataframe(clf["confusion_matrix"], use_container_width=True)
            st.write(t("per_class_caption"))
            st.dataframe(clf["per_class"], use_container_width=True)
            if clf["top_feature_importances"]:
                st.write(t("top_features_caption"))
                st.dataframe(clf["top_feature_importances"], use_container_width=True)
            if st.button(t("save_clf_btn")):
                _save_model_config(f"classifier_{clf['target']}", clf["method"],
                                   {"target": clf["target"],
                                    "features": clf["features"]})
    else:
        st.write(t("clf_needs"))
