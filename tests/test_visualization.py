"""Tests for core/visualization.py (figure objects, not pixels)."""

import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go

from core.visualization import (
    VisualizationError,
    bar_chart,
    box_plot,
    correlation_graph,
    heatmap,
    histogram,
    line_chart,
    matplotlib_box,
    matplotlib_histogram,
    pie_chart,
    scatter_plot,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "month": ["Jan", "Feb", "Mar", "Jan", "Feb", "Mar"],
            "sales": [10, 20, 15, 12, 22, 18],
            "profit": [1, 2, 1, 2, 3, 2],
            "region": ["E", "E", "W", "W", "E", "W"],
        }
    )


def test_plotly_charts_return_figures_with_data() -> None:
    df = _frame()
    for fig in (
        bar_chart(df, "region", "sales"),
        bar_chart(df, "region"),
        line_chart(df, "sales", "profit"),
        scatter_plot(df, "sales", "profit", color="region"),
        histogram(df, "sales", bins=5),
        box_plot(df, "sales", by="region"),
        heatmap(df, ["sales", "profit"]),
        pie_chart(df, "region"),
    ):
        assert isinstance(fig, go.Figure)
        assert len(fig.data) >= 1


def test_pie_groups_long_tail_explicitly() -> None:
    df = pd.DataFrame({"cat": [f"c{i}" for i in range(30)]})
    fig = pie_chart(df, "cat")
    labels = list(fig.data[0].labels)
    assert any("Other" in label for label in labels)
    assert "grouped" in (fig.layout.title.text or "")


def test_matplotlib_variants_return_figures() -> None:
    df = _frame()
    for fig, _ in (
        matplotlib_histogram(df, "sales"),
        matplotlib_box(df, "sales", by="region"),
        correlation_graph(df, ["sales", "profit"]),
    ):
        assert isinstance(fig, plt.Figure)
        plt.close(fig)


def test_unknown_column_and_non_numeric_rejected() -> None:
    df = _frame()
    for call in (
        lambda: bar_chart(df, "nope"),
        lambda: histogram(df, "region"),
        lambda: heatmap(df, ["sales"]),
    ):
        try:
            call()
        except VisualizationError:
            pass
        else:
            raise AssertionError("Expected VisualizationError")
