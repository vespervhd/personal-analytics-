"""Export helpers: write a DataFrame to in-memory bytes.

Exporting never touches the original upload: it reads the working
DataFrame only and writes to an in-memory buffer, never to disk.
"""

from __future__ import annotations

import io

import pandas as pd


def dataframe_to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    """Return *df* as .xlsx bytes (openpyxl, no index column).

    Raises ValueError for an empty input (no rows or no columns).
    """
    if df.shape[0] == 0 or df.shape[1] == 0:
        raise ValueError("Cannot export an empty dataset to Excel.")
    buffer = io.BytesIO()
    df.to_excel(buffer, engine="openpyxl", index=False)
    return buffer.getvalue()
