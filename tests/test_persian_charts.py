"""Tests for the bundled Vazirmatn font fixes (item: Persian fonts).

Covers every surface the fix touches: the bundled font files, the
embedded web ``@font-face``, matplotlib reshaping + font registration,
and the Vazirmatn family on Plotly figures. Nothing here needs the
network: the font files ship in ``assets/fonts/``.
"""

import io
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from core.persian_text import (
    bundled_font_pair,
    ensure_matplotlib_persian,
    font_face_css,
    reshape_persian,
)
from core.report_generator import font_covers_persian
from core.visualization import (
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


def _frame_fa() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "فروش": [10, 20, 15, 12, 22, 18],
            "سود": [1, 2, 1, 2, 3, 2],
            "شهر": ["تهران", "اصفهان", "تهران", "اصفهان", "تهران", "اصفهان"],
        }
    )


def test_bundled_vazirmatn_pair_exists_and_covers_persian() -> None:
    pair = bundled_font_pair()
    assert pair is not None
    for path in pair:
        assert Path(path).is_file(), f"missing bundled font: {path}"
        assert font_covers_persian(path), f"bundled font lacks Persian glyphs: {path}"


def test_font_face_css_embeds_vazirmatn_without_network() -> None:
    css = font_face_css()
    assert "@font-face" in css
    assert "font-family: 'Vazirmatn'" in css
    assert "data:font/woff2;base64," in css
    assert "fonts.googleapis.com" not in css
    assert "fonts.gstatic.com" not in css


def test_matplotlib_registers_vazirmatn() -> None:
    assert ensure_matplotlib_persian() == "Vazirmatn"
    assert "Vazirmatn" in plt.rcParams["font.family"]


def test_matplotlib_histogram_reshapes_persian_labels() -> None:
    df = _frame_fa()
    fig, ax = matplotlib_histogram(df, "فروش")
    try:
        assert ax.get_title() == reshape_persian("Distribution of فروش")
        assert ax.get_xlabel() == reshape_persian("فروش")
        # The figure must render to PNG without error (missing glyphs
        # would not raise, but a broken font registration would).
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        assert len(buf.getvalue()) > 1000
    finally:
        plt.close(fig)


def test_matplotlib_box_reshapes_persian_group_labels() -> None:
    df = _frame_fa()
    fig, ax = matplotlib_box(df, "فروش", by="شهر")
    try:
        fig.canvas.draw()
        labels = [tick.get_text() for tick in ax.get_xticklabels()]
        assert labels, "expected category tick labels"
        assert set(labels) == {reshape_persian("تهران"), reshape_persian("اصفهان")}
        assert ax.get_title() == reshape_persian("Box plot of فروش by شهر")
    finally:
        plt.close(fig)


def test_correlation_graph_reshapes_persian_columns() -> None:
    df = _frame_fa()
    fig, ax = correlation_graph(df, ["فروش", "سود"])
    try:
        fig.canvas.draw()
        x_labels = [tick.get_text() for tick in ax.get_xticklabels()]
        y_labels = [tick.get_text() for tick in ax.get_yticklabels()]
        assert set(x_labels) == {reshape_persian("فروش"), reshape_persian("سود")}
        assert set(y_labels) == {reshape_persian("فروش"), reshape_persian("سود")}
    finally:
        plt.close(fig)


def test_plotly_figures_use_vazirmatn() -> None:
    df = _frame_fa()
    figs = (
        bar_chart(df, "شهر", "فروش"),
        line_chart(df, "فروش", "سود"),
        scatter_plot(df, "فروش", "سود", color="شهر"),
        histogram(df, "فروش", bins=3),
        box_plot(df, "فروش", by="شهر"),
        heatmap(df, ["فروش", "سود"]),
        pie_chart(df, "شهر"),
    )
    for fig in figs:
        assert fig.layout.font.family == "Vazirmatn"
