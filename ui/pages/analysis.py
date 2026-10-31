"""Statistical Analysis page: EDA report, distributions, OLS, insights."""

from __future__ import annotations

import streamlit as st

from core.analyzer import eda_report, key_insights
from core.statistics import StatisticsError, distribution_analysis, ols_regression
from core.visualization import VisualizationError, heatmap
from database.connection import get_session, init_db
from database.repository import record_analysis
from ui.components.common import require_dataset


def render() -> None:
    st.header("Statistical Analysis")
    df = require_dataset()
    if df is None:
        return

    report = eda_report(df)
    overview = report["overview"]

    st.subheader("Dataset overview")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Rows", f"{overview['rows']:,}")
    col2.metric("Columns", f"{overview['columns']:,}")
    col3.metric("Missing cells", f"{overview['total_missing']:,}")
    col4.metric("Duplicate rows", f"{overview['duplicate_rows']:,}")

    st.subheader("Missing values by column")
    missing_rows = [
        {"column": col, "missing": info["missing"], "percent": info["percent"]}
        for col, info in report["missing"]["columns"].items()
    ]
    st.dataframe(missing_rows, use_container_width=True)

    st.subheader("Column summaries")
    summary_rows = []
    for column, summary in report["columns"].items():
        row = {"column": column, "type": summary["type"]}
        if summary["type"] == "numeric":
            row.update(
                {
                    "mean": summary["mean"],
                    "median": summary["median"],
                    "std": summary["std"],
                    "min": summary["min"],
                    "max": summary["max"],
                    "unique": None,
                }
            )
        else:
            row.update(
                {
                    "mean": None,
                    "median": None,
                    "std": None,
                    "min": None,
                    "max": None,
                    "unique": summary["unique"],
                }
            )
        summary_rows.append(row)
    st.dataframe(summary_rows, use_container_width=True)

    if report["correlation"] is not None:
        st.subheader("Correlation matrix")
        try:
            st.plotly_chart(heatmap(df), use_container_width=True)
        except VisualizationError as exc:
            st.error(f"Could not build correlation heatmap: {exc}")

    st.subheader("Key insights")
    for insight in key_insights(df, report):
        st.write(f"- {insight}")

    st.subheader("Distribution detail")
    numeric = [str(c) for c in df.select_dtypes(include="number").columns]
    if numeric:
        column = st.selectbox("Numeric column", options=numeric, key="dist_col")
        try:
            detail = distribution_analysis(df[column])
            st.write(f"Skew: **{detail['skew']}** · Kurtosis: **{detail['kurtosis']}**")
            st.write(f"Shapiro-Wilk statistic: **{detail['shapiro_statistic']}** · "
                     f"p-value: **{detail['shapiro_p_value']}**")
            st.caption(detail["shapiro_note"])
        except StatisticsError as exc:
            st.error(f"Could not analyse distribution: {exc}")
    else:
        st.write("No numeric columns available for distribution analysis.")

    st.subheader("OLS regression (statsmodels)")
    if len(numeric) >= 2:
        target = st.selectbox("Target", options=numeric, key="ols_target")
        features = st.multiselect(
            "Features", options=[c for c in numeric if c != target], key="ols_features"
        )
        if st.button("Fit OLS"):
            try:
                result = ols_regression(df, target, features)
            except StatisticsError as exc:
                st.error(f"Could not fit OLS: {exc}")
            else:
                st.write(f"R²: **{result['r_squared']}** · Adjusted R²: "
                         f"**{result['adj_r_squared']}** · Rows used: "
                         f"**{result['rows_used']}** (dropped "
                         f"{result['rows_dropped_missing']} incomplete rows)")
                st.dataframe(
                    {
                        "term": list(result["coefficients"]),
                        "coefficient": list(result["coefficients"].values()),
                        "p-value": list(result["p_values"].values()),
                    },
                    use_container_width=True,
                )
    else:
        st.write("OLS needs at least 2 numeric columns.")

    st.divider()
    if st.button("Save this analysis to history"):
        dataset_id = st.session_state.get("dataset_id")
        try:
            init_db()
            with get_session() as session:
                record_analysis(
                    session,
                    analysis_type="eda",
                    parameters={},
                    result_summary={
                        "rows": overview["rows"],
                        "columns": overview["columns"],
                        "insights": key_insights(df, report),
                    },
                    dataset_id=dataset_id,
                )
            st.success("Analysis saved to history.")
        except Exception as exc:
            st.error(f"Could not save analysis: {exc}")
