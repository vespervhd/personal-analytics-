"""Tests for Persian reports (item 6): PDF shaping, Excel round-trip,
translated prose, and translated report-dict keys.

PDF text extraction notes (verified, not assumed): pypdf returns the
PDF's shaped presentation forms with words in logical order, but drops
the invisible ZWNJ character (U+200C) itself — the PDF still renders
joined words correctly, as the presentation forms prove. Expected
strings below therefore strip ZWNJ before comparison. If pypdf is not
installed, the PDF extraction test is skipped (pypdf is a local test
tool only, intentionally absent from requirements.txt).
"""

import re
from pathlib import Path
import tempfile

import pandas as pd
import pytest

from core.analyzer import key_insights
from core.report_generator import (
    find_arabic_font,
    font_covers_persian,
    generate_report,
    persian_paragraph_markup,
)
from core.statistics import distribution_analysis
from ui.components.common import report_key_label, translate_report_keys


def _frame_fa() -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "سن": [20, 25, 30, 35, 40, 45, 50, 55],
            "درآمد": [10, 20, 30, 40, 50, 60, 70, 80],
            "شهر": ["تهران"] * 8,
        }
    )
    frame.loc[0:1, "سن"] = None  # 25% missing -> triggers the missing insight
    return frame


def _unshape(text: str) -> str:
    """Map Arabic presentation forms back to base letters (test only)."""
    from arabic_reshaper.letters import LETTERS_ARABIC

    reverse = {}
    for base, forms in LETTERS_ARABIC.items():
        for form in forms:
            if form:
                reverse[form] = base
    return "".join(reverse.get(char, char) for char in text)


def _logical(text: str) -> str:
    """Expected extracted text: unshaped, with ZWNJ dropped by extraction."""
    return _unshape(text).replace("\u200c", "")


def test_arabic_font_found_and_verified() -> None:
    regular, bold = find_arabic_font()
    assert Path(regular).is_file() and Path(bold).is_file()
    assert "NotoSansArabic" in regular or "DejaVuSans" in regular
    assert font_covers_persian(regular) is True


def test_persian_paragraph_markup_switches_fonts() -> None:
    markup = persian_paragraph_markup("گزارش سن")
    assert "NotoArabic" in markup
    assert persian_paragraph_markup("plain english") == "plain english"


def test_persian_pdf_embeds_font_and_logical_text() -> None:
    pypdf = pytest.importorskip("pypdf")
    df = _frame_fa()
    with tempfile.TemporaryDirectory() as tmp:
        pdf = generate_report(df, "pdf", Path(tmp) / "fa.pdf", lang="fa")
        assert pdf.read_bytes()[:4] == b"%PDF"
        reader = pypdf.PdfReader(str(pdf))
        fonts = reader.pages[0]["/Resources"]["/Font"]
        base_fonts = [str(font.get("/BaseFont")) for font in fonts.values()]
        assert any("NotoSansArabic" in name for name in base_fonts), base_fonts
        assert any("Helvetica" in name for name in base_fonts)
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        # Shaping really happened: extraction holds presentation forms.
        assert any(0xFB50 <= ord(c) <= 0xFEFF for c in text)
        # Logical order, proven by unshaping the extracted title/heading.
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        unshaped = [_logical(line) for line in lines]
        assert "گزارش تحلیل داده‌های شخصی".replace("\u200c", "") in unshaped
        assert "نمای کلی مجموعه‌داده".replace("\u200c", "") in unshaped
        # Translated prose made it into the PDF.
        assert any("ستون" in line for line in unshaped)
        assert any("همبستگی" in line for line in unshaped)


def test_english_pdf_still_plain() -> None:
    pypdf = pytest.importorskip("pypdf")
    df = pd.DataFrame({"a": [1, 2, 3, 4], "b": [2, 4, 6, 8]})
    with tempfile.TemporaryDirectory() as tmp:
        pdf = generate_report(df, "pdf", Path(tmp) / "en.pdf", lang="en")
        text = "\n".join(
            (page.extract_text() or "") for page in pypdf.PdfReader(str(pdf)).pages
        )
        assert "Personal Data Analytics Report" in text
        assert "Key insights" in text


def test_excel_persian_round_trip() -> None:
    import openpyxl

    df = _frame_fa()
    with tempfile.TemporaryDirectory() as tmp:
        xlsx = generate_report(df, "xlsx", Path(tmp) / "fa.xlsx", lang="fa")
        workbook = openpyxl.load_workbook(xlsx)
        overview = [row for row in workbook["Overview"].iter_rows(values_only=True)]
        assert any("ردیف‌ها" in str(cell) for row in overview for cell in row)
        stats = [row for row in workbook["Column stats"].iter_rows(values_only=True)]
        assert any("سن" in str(cell) for row in stats for cell in row)
        insights = [row[0] for row in workbook["Insights"].iter_rows(values_only=True)
                    if row[0]]
        assert any("ستون" in str(cell) and "سن" in str(cell) for cell in insights)
        assert workbook["Overview"].sheet_view.rightToLeft is True


def test_csv_persian_insight() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = generate_report(_frame_fa(), "csv", Path(tmp) / "fa.csv", lang="fa")
        text = csv_path.read_text(encoding="utf-8")
        assert "ستون" in text and "سن" in text


def test_html_persian_rtl_and_labels() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        html_path = generate_report(_frame_fa(), "html", Path(tmp) / "fa.html", lang="fa")
        text = html_path.read_text(encoding="utf-8")
        assert 'lang="fa"' in text and 'dir="rtl"' in text
        assert "گزارش تحلیل داده‌های شخصی" in text
        assert "نمای کلی مجموعه‌داده" in text


def test_key_insights_translated_both_languages() -> None:
    df = _frame_fa()
    fa_insights = key_insights(df, lang="fa")
    en_insights = key_insights(df, lang="en")
    assert any("ستون" in text and "سن" in text for text in fa_insights)
    assert not any("Column" in text for text in fa_insights)
    assert any("Column 'سن'" in text for text in en_insights)
    assert any("Strongest correlation" in text for text in en_insights)
    assert any("همبستگی" in text for text in fa_insights)


def test_shapiro_note_translated_both_languages() -> None:
    small = distribution_analysis(pd.Series([1, 2, 3, 4, 5, 6, 7, 8]), lang="fa")
    assert "نرمال" in small["shapiro_note"]
    big = distribution_analysis(pd.Series(range(6000)), lang="fa")
    assert "شاپیرو-ویلک" in big["shapiro_note"]
    small_en = distribution_analysis(pd.Series([1, 2, 3, 4, 5, 6, 7, 8]), lang="en")
    assert "consistent with normality" in small_en["shapiro_note"]


def test_show_report_key_labels() -> None:
    assert report_key_label("rows_before", lang="fa") == "ردیف‌های پیش از عملیات"
    assert report_key_label("rows_before", lang="en") == "rows before"
    assert report_key_label("unknown_key_xyz", lang="fa") == "unknown_key_xyz"
    translated = translate_report_keys(
        {"rows_before": 10, "columns": {"سن": {"missing": 2, "percent": 25.0}}},
        lang="fa",
    )
    assert translated["ردیف‌های پیش از عملیات"] == 10
    assert translated["ستون‌ها"]["سن"]["خالی"] == 2


def test_report_prose_has_no_latin_digits_problem() -> None:
    # Persian insight templates must not smuggle Persian digits in.
    persian_digits = set("۰۱۲۳۴۵۶۷۸۹")
    for insight in key_insights(_frame_fa(), lang="fa"):
        assert not (set(insight) & persian_digits)
        assert not re.search(r"[۰-۹]", insight)
