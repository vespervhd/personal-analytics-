"""Tests for core/report_generator.py (all four formats, tmp dirs)."""

import csv
from pathlib import Path
import tempfile

import pandas as pd

from core.report_generator import generate_report


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "a": [1, 2, 3, 4, 5, 6],
            "b": [2, 4, 6, 8, 10, 12],
            "c": ["x", "y", "x", "y", "x", "y"],
        }
    )


def _anomalies() -> dict:
    return {
        "method": "isolation_forest",
        "anomalies": 1,
        "rows_analysed": 6,
        "anomaly_rows": [{"a": 6, "b": 12}],
    }


def test_all_formats_generate_nonempty_files() -> None:
    df = _frame()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for fmt in ("pdf", "xlsx", "csv", "html"):
            path = generate_report(df, fmt, root / f"report.{fmt}",
                                   anomalies=_anomalies())
            assert path.exists() and path.stat().st_size > 0, fmt


def test_pdf_magic_and_csv_parseable() -> None:
    df = _frame()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pdf = generate_report(df, "pdf", root / "r.pdf")
        assert pdf.read_bytes()[:4] == b"%PDF"
        csv_path = generate_report(df, "csv", root / "r.csv")
        with csv_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        assert len(rows) > 5 and rows[0] == ["section", "key", "value"]


def test_excel_sheets_and_html_content() -> None:
    df = _frame()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        xlsx = generate_report(df, "xlsx", root / "r.xlsx")
        import openpyxl

        workbook = openpyxl.load_workbook(xlsx)
        assert "Overview" in workbook.sheetnames
        assert "Insights" in workbook.sheetnames
        html = generate_report(df, "html", root / "r.html")
        text = html.read_text(encoding="utf-8")
        assert "Personal Data Analytics Report" in text
        assert "Key insights" in text


def test_unknown_format_rejected() -> None:
    try:
        generate_report(_frame(), "docx", Path("/tmp/x.docx"))
    except Exception as exc:
        assert "Unknown report format" in str(exc)
        return
    raise AssertionError("Expected ReportError for unknown format")
