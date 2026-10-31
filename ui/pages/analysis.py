"""Statistical Analysis page: EDA report, distributions, OLS, insights."""

from __future__ import annotations

import streamlit as st

from core.analyzer import eda_report, key_insights
from core.statistics import StatisticsError, distribution_analysis, ols_regression
from core.visualization import VisualizationError, heatmap
from database.connection import get_session, init_db
from database.repository import record_analysis
from ui.components.common import require_dataset
from ui.i18n import current_lang, t


def render() -> None:
    st.header(t("page_analysis"))
    df = require_dataset()
    if df is None:
        return

    report = eda_report(df)
    overview = report["overview"]

    st.subheader(t("dataset_overview_sub"))
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(t("metric_rows"), f"{overview['rows']:,}")
    col2.metric(t("metric_columns"), f"{overview['columns']:,}")
    col3.metric(t("metric_missing"), f"{overview['total_missing']:,}")
    col4.metric(t("metric_duplicates"), f"{overview['duplicate_rows']:,}")

    st.subheader(t("missing_by_col_sub"))
    missing_rows = [
        {t("col_column"): col, t("col_missing"): info["missing"], t("col_percent"): info["percent"]}
        for col, info in report["missing"]["columns"].items()
    ]
    st.dataframe(missing_rows, use_container_width=True)

    st.subheader(t("column_summaries_sub"))
    summary_rows = []
    for column, summary in report["columns"].items():
        row = {t("col_column"): column, t("col_type"): summary["type"]}
        if summary["type"] == "numeric":
            row.update(
                {
                    t("col_mean"): summary["mean"],
                    t("col_median"): summary["median"],
                    t("col_std"): summary["std"],
                    t("col_min"): summary["min"],
                    t("col_max"): summary["max"],
                    t("col_unique"): None,
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
                    t("col_unique"): summary["unique"],
                }
            )
        summary_rows.append(row)
    st.dataframe(summary_rows, use_container_width=True)

    if report["correlation"] is not None:
        st.subheader(t("correlation_sub"))
        try:
            st.plotly_chart(heatmap(df), use_container_width=True)
        except VisualizationError as exc:
            st.error(t("heatmap_error").format(err=exc))

    st.subheader(t("insights_sub"))
    for insight in key_insights(df, report, lang=current_lang()):
        st.write(f"- {insight}")

    st.subheader(t("dist_detail_sub"))
    numeric = [str(c) for c in df.select_dtypes(include="number").columns]
    if numeric:
        column = st.selectbox(t("numeric_col_label"), options=numeric, key="dist_col")
        try:
            detail = distribution_analysis(df[column], lang=current_lang())
            st.write(t("skew_line").format(v=detail["skew"], v2=detail["kurtosis"]))
            st.write(t("shapiro_line").format(s=detail["shapiro_statistic"], p=detail["shapiro_p_value"]))
            st.caption(detail["shapiro_note"])
        except StatisticsError as exc:
            st.error(t("dist_error").format(err=exc))
    else:
        st.write(t("no_numeric_dist"))

    st.subheader(t("ols_sub"))
    if len(numeric) >= 2:
        target = st.selectbox(t("target_label"), options=numeric, key="ols_target")
        features = st.multiselect(
            t("features_label"), options=[c for c in numeric if c != target], key="ols_features"
        )
        if st.button(t("fit_ols_btn")):
            try:
                result = ols_regression(df, target, features)
            except StatisticsError as exc:
                st.error(t("ols_error").format(err=exc))
            else:
                st.write(t("ols_result").format(r2=result["r_squared"], adj=result["adj_r_squared"], used=result["rows_used"], dropped=result["rows_dropped_missing"]))
                st.dataframe(
                    {
                        t("col_term"): list(result["coefficients"]),
                        t("col_coefficient"): list(result["coefficients"].values()),
                        t("col_pvalue"): list(result["p_values"].values()),
                    },
                    use_container_width=True,
                )
    else:
        st.write(t("ols_needs"))

    st.divider()
    if st.button(t("save_analysis_btn")):
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
                        "insights": key_insights(df, report, lang=current_lang()),
                    },
                    dataset_id=dataset_id,
                )
            st.success(t("analysis_saved"))
        except Exception as exc:
            st.error(t("save_analysis_error").format(err=exc))
