"""Tests for the smart chart suggestions (core/chart_suggest.py).

Pure-function tests: no Streamlit session is needed. The last test
guards the core promise — every suggested chart type is one the
Visualizations page can actually render.
"""

import pandas as pd

from core.chart_suggest import (
    SUPPORTED_CHARTS,
    classify_columns,
    suggest_charts,
)
from ui.i18n import STRINGS
from ui.pages.charts import _CHARTS


def _by_chart(suggestions):
    # First suggestion per chart type wins: Bar appears twice (value
    # bars, then count bars), and the value variant is the ranked one.
    result = {}
    for suggestion in suggestions:
        result.setdefault(suggestion.chart, suggestion)
    return result


def test_categorical_plus_numeric_suggests_bar():
    df = pd.DataFrame(
        {"country": ["UK", "USA", "UK", "USA"], "score": [80.0, 65.0, 90.0, 70.0]}
    )
    suggestions = _by_chart(suggest_charts(df))
    assert "Bar" in suggestions
    bar = suggestions["Bar"]
    assert bar.x == "country"
    assert bar.y == "score"
    assert bar.use_y is True


def test_two_numeric_suggests_scatter():
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": [2.0, 3.0, 5.0, 7.0]})
    suggestions = _by_chart(suggest_charts(df))
    assert "Scatter" in suggestions
    scatter = suggestions["Scatter"]
    assert {scatter.x, scatter.y} == {"a", "b"}


def test_datetime_plus_numeric_suggests_line():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "value": [10.0, 12.0, 11.0],
        }
    )
    suggestions = _by_chart(suggest_charts(df))
    assert "Line" in suggestions
    line = suggestions["Line"]
    assert line.x == "date"
    assert line.y == "value"


def test_datetime_strings_suggest_line():
    df = pd.DataFrame(
        {"day": ["2024-01-01", "2024-01-02", "2024-01-03"], "value": [1.0, 2.0, 3.0]}
    )
    assert classify_columns(df)["datetime"] == ["day"]
    assert _by_chart(suggest_charts(df))["Line"].x == "day"


def test_single_categorical_suggests_count_bar():
    df = pd.DataFrame({"kind": ["LLM", "Vision", "LLM", "Vision", "LLM"]})
    suggestions = _by_chart(suggest_charts(df))
    assert "Bar" in suggestions
    count = suggestions["Bar"]
    assert count.x == "kind"
    assert count.y is None
    assert count.use_y is False


def test_single_numeric_suggests_histogram():
    df = pd.DataFrame({"score": [1.0, 2.0, 2.0, 3.0, 5.0]})
    suggestions = suggest_charts(df)
    assert [s.chart for s in suggestions] == ["Histogram"]
    assert suggestions[0].column == "score"


def test_categorical_plus_numeric_also_suggests_box():
    df = pd.DataFrame(
        {"kind": ["A", "A", "B", "B"], "score": [1.0, 2.0, 3.0, 4.0]}
    )
    box = _by_chart(suggest_charts(df))["Box"]
    assert box.column == "score"
    assert box.by == "kind"


def test_many_numeric_suggests_heatmap():
    df = pd.DataFrame(
        {"a": [1.0, 2.0, 3.0], "b": [1.0, 1.0, 2.0], "c": [5.0, 4.0, 3.0]}
    )
    heat = _by_chart(suggest_charts(df))["Heatmap"]
    assert list(heat.columns) == ["a", "b", "c"]


def test_small_category_suggests_pie_but_large_does_not():
    small = pd.DataFrame({"kind": ["A", "B", "A", "B", "A"]})
    assert "Pie" in _by_chart(suggest_charts(small))
    large = pd.DataFrame({"kind": [f"k{i}" for i in range(20)] * 2})
    assert "Pie" not in _by_chart(suggest_charts(large))


def test_high_cardinality_text_is_not_categorical():
    df = pd.DataFrame(
        {"model": [f"model-{i}" for i in range(100)], "score": [float(i) for i in range(100)]}
    )
    assert classify_columns(df)["categorical"] == []
    # No category-based suggestion, but the numeric column still counts.
    assert _by_chart(suggest_charts(df))["Histogram"].column == "score"


def test_empty_dataframe_suggests_nothing():
    assert suggest_charts(pd.DataFrame()) == []
    assert suggest_charts(pd.DataFrame({"a": [], "b": []})) == []


def test_all_null_columns_suggest_nothing():
    df = pd.DataFrame({"a": [None, None, None], "b": [None, None, None]})
    assert suggest_charts(df) == []


def test_all_null_column_ignored_but_others_used():
    df = pd.DataFrame(
        {"gone": [None, None, None, None], "score": [1.0, 2.0, 3.0, 4.0]}
    )
    assert classify_columns(df)["numeric"] == ["score"]
    assert _by_chart(suggest_charts(df))["Histogram"].column == "score"


def test_every_suggested_chart_is_supported_by_the_page():
    frames = [
        pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
                "kind": ["A", "B", "A"],
                "a": [1.0, 2.0, 3.0],
                "b": [2.0, 3.0, 4.0],
            }
        ),
        pd.DataFrame({"kind": ["A", "B", "A"]}),
        pd.DataFrame({"score": [1.0, 2.0, 3.0]}),
        pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]}),
    ]
    for df in frames:
        for suggestion in suggest_charts(df):
            assert suggestion.chart in SUPPORTED_CHARTS
            assert suggestion.chart in _CHARTS


def test_every_explanation_key_exists_in_both_languages():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "kind": ["A", "B", "A"],
            "a": [1.0, 2.0, 3.0],
            "b": [2.0, 3.0, 4.0],
        }
    )
    keys = {s.explanation_key for s in suggest_charts(df)}
    assert keys  # the fixture must exercise more than one mapping
    for key in keys:
        assert key in STRINGS["fa"], key
        assert key in STRINGS["en"], key
        assert STRINGS["fa"][key].strip()
        assert STRINGS["en"][key].strip()


def test_suggestions_are_deterministic():
    df = pd.DataFrame(
        {"kind": ["A", "B", "A", "B"], "a": [1.0, 2.0, 3.0, 4.0], "b": [2.0, 1.0, 4.0, 3.0]}
    )
    first = suggest_charts(df)
    second = suggest_charts(df)
    assert first == second
