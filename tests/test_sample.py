"""Tests for the bundled in-app sample dataset.

The sample file ships under ``data/sample/`` (tracked, unlike user uploads
under ``data/uploads/``) and is loaded read-only via ``load_from_path``.
Row counts are asserted from the file itself, not hardcoded, so a future
sample refresh does not break these tests.
"""

import pandas as pd

from config import SETTINGS
from core.data_loader import load_from_path
from ui.pages.data_import import SAMPLE_DISPLAY_NAME, SAMPLE_PATH

EXPECTED_COLUMNS = {"Model", "Organization", "Release Year"}


def test_bundled_sample_file_exists() -> None:
    assert SAMPLE_PATH == SETTINGS.base_dir / "data" / "sample" / "ai-models-sample.csv"
    assert SAMPLE_PATH.is_file()
    assert SAMPLE_PATH.stat().st_size > 0
    assert SAMPLE_DISPLAY_NAME


def test_sample_loads_via_load_from_path() -> None:
    df = load_from_path(SAMPLE_PATH)
    # Measured from the file at test time, not hardcoded.
    assert len(df) > 100
    assert len(df.columns) >= 1
    assert EXPECTED_COLUMNS <= set(df.columns)


def test_store_dataset_style_state_is_a_deep_copy() -> None:
    """Mirror ``_store_dataset``: df + a deep copy as df_original.

    ``_store_dataset`` itself writes to ``st.session_state`` (Streamlit
    runtime only), so the test verifies the exact state invariant it
    establishes: the stored original equals the dataset, and later
    mutations of the working frame must not leak into the original.
    """
    df = load_from_path(SAMPLE_PATH)
    state = {"df": df, "df_original": df.copy(deep=True)}
    pd.testing.assert_frame_equal(state["df"], state["df_original"])
    # Mutate a string column (the first column is an int ID, which pandas
    # refuses to overwrite with a string).
    original_first_value = state["df_original"]["Model"].iloc[0]
    state["df"].loc[state["df"].index[0], "Model"] = "__mutated__"
    assert state["df_original"]["Model"].iloc[0] == original_first_value
