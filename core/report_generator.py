"""Report generation: PDF, Excel, CSV, HTML.

Every report contains the same honest sections — dataset overview, data
quality assessment, statistical summaries, detected anomalies, and key
insights derived from the actual numbers (see ``core.analyzer``). Charts
in PDF/Excel are matplotlib figures (no extra renderer needed); the HTML
report embeds interactive Plotly figures.

An ``anomalies`` argument is the result dict of an ml_engine run (or
``None`` when no detection was run — the report says so instead of
pretending otherwise).

Persian (``lang="fa"``) reports translate every user-visible label and
prose sentence through the i18n dictionary; internal identifiers (sheet
names, CSV section names, dtype keys) stay English. PDF reports embed
Noto Sans Arabic (system font, verified programmatically for the
presentation forms ``arabic_reshaper`` produces) and reshape + reorder
Persian text with ``arabic_reshaper`` + ``python-bidi`` before handing
it to ReportLab, which has no shaping engine of its own. If no verified
Arabic-capable font is available, a Persian PDF is refused with a clear
error instead of a file full of missing glyphs.
"""

from __future__ import annotations

import csv
import html
import io
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from core.analyzer import eda_report, key_insights
from core.visualization import (
    correlation_graph,
    heatmap,
    histogram,
    matplotlib_histogram,
)
from utils.logger import get_logger

log = get_logger("report_generator")

REPORT_FORMATS = ("pdf", "xlsx", "csv", "html")


class ReportError(ValueError):
    """Raised when a report cannot be generated."""


def _t(key: str, lang: str) -> str:
    """Translate ``key`` in ``lang`` (local import: core never imports UI)."""
    from ui.i18n import t

    return t(key, lang=lang)


# ---------------------------------------------------------------------------
# Persian text handling (ReportLab / matplotlib have no shaping engine)
# ---------------------------------------------------------------------------

#: Arabic-script ranges (base letters, supplements, presentation forms).
_ARABIC_RANGES = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x08A0, 0x08FF),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
)


def _is_arabic_char(char: str) -> bool:
    code = ord(char)
    return any(start <= code <= end for start, end in _ARABIC_RANGES)


def contains_arabic(text: str) -> bool:
    """Return True when ``text`` holds any Arabic-script character."""
    return any(_is_arabic_char(char) for char in text)


def reshape_persian(text: str) -> str:
    """Reshape + reorder Persian text into visual order for dumb renderers.

    ``arabic_reshaper`` joins letters into their presentation forms and
    ``python-bidi`` reorders the line so a left-to-right renderer (PDF,
    matplotlib) draws it correctly. Non-Arabic text passes through
    unchanged apart from the bidi pass, which leaves pure Latin order
    intact.
    """
    import arabic_reshaper
    from bidi.algorithm import get_display

    return get_display(arabic_reshaper.reshape(text))


#: Candidate (regular, bold) system font pairs, best first. Noto Sans
#: Arabic covers 751/832 Arabic presentation forms (verified with
#: fontTools); DejaVu Sans is the matplotlib-bundled fallback and covers
#: every form ``arabic_reshaper`` produces for common Persian words.
_ARABIC_FONT_CANDIDATES: tuple[tuple[str, str], ...] = (
    (
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
    ),
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
)

#: Pangram covering every Persian letter, used for coverage verification.
_ARABIC_COVERAGE_SAMPLE = "ابپتثجچحخدرذزژسشصضطظعغفقکگلمنوهی می‌شود داده‌ها 0123456789"


def font_covers_persian(path: str) -> bool:
    """Check the font's cmap holds every glyph reshaping needs.

    Renders the coverage pangram through the real reshape+bidi pipeline
    and requires every resulting code point (except spaces) in the
    font's cmap. A font that fails this would print missing glyphs.
    """
    from fontTools.ttLib import TTFont

    try:
        cmap = TTFont(path).getBestCmap()
    except Exception:
        return False
    visual = reshape_persian(_ARABIC_COVERAGE_SAMPLE)
    return all(ord(char) in cmap or char == " " for char in visual)


def find_arabic_font() -> tuple[str, str]:
    """Return the first verified (regular, bold) Arabic font pair.

    Raises :class:`ReportError` when no candidate exists on disk or
    passes coverage verification, so callers fail honestly instead of
    shipping a broken PDF.
    """
    for regular, bold in _ARABIC_FONT_CANDIDATES:
        if Path(regular).is_file() and font_covers_persian(regular):
            if Path(bold).is_file() and font_covers_persian(bold):
                return regular, bold
            return regular, regular
    raise ReportError(
        "No Arabic-capable font found on this system: Persian PDF reports "
        "need Noto Sans Arabic (or DejaVu Sans) installed. Install "
        "fonts-noto-core and retry."
    )


_PDF_FONTS_REGISTERED = False
_PDF_FONT_NAMES: tuple[str, str] = ("NotoArabic", "NotoArabic-Bold")


def ensure_pdf_fonts() -> tuple[str, str]:
    """Register the verified Arabic font with ReportLab (once)."""
    global _PDF_FONTS_REGISTERED
    if not _PDF_FONTS_REGISTERED:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        regular, bold = find_arabic_font()
        pdfmetrics.registerFont(TTFont(_PDF_FONT_NAMES[0], regular))
        pdfmetrics.registerFont(TTFont(_PDF_FONT_NAMES[1], bold))
        _PDF_FONTS_REGISTERED = True
    return _PDF_FONT_NAMES


def persian_paragraph_markup(text: str, bold: bool = False) -> str:
    """Turn ``text`` into ReportLab Paragraph markup with font switching.

    Persian runs (in visual order, after reshape+bidi) render in the
    embedded Arabic font (bold variant when ``bold``); Latin/digit runs
    render in Helvetica, which the Arabic font lacks. Pure Latin text
    is returned escaped but otherwise untouched, so English reports
    never change.
    """
    escaped = html.escape(str(text))
    if not contains_arabic(str(text)):
        return escaped
    ensure_pdf_fonts()
    visual = reshape_persian(str(text))
    arabic_font = _PDF_FONT_NAMES[1] if bold else _PDF_FONT_NAMES[0]
    parts: list[str] = []
    current_font: str | None = None
    current_run: list[str] = []

    def flush() -> None:
        if current_run:
            font = arabic_font if current_font == "arabic" else "Helvetica"
            parts.append(f'<font name="{font}">{"".join(current_run)}</font>')

    for char in visual:
        # Spaces ride with the current run so word spacing uses that font.
        kind = current_font if char == " " else ("arabic" if _is_arabic_char(char) else "latin")
        if kind is None:
            kind = "arabic" if _is_arabic_char(char) else "latin"
        if kind != current_font and current_run:
            flush()
            current_run = []
        current_font = kind
        current_run.append(html.escape(char))
    flush()
    return "".join(parts)


def _localize_matplotlib_figure(fig: plt.Figure, lang: str) -> None:
    """Reshape Persian text inside a matplotlib figure (fa reports only).

    Pure Persian texts switch to the Noto Sans Arabic family; mixed
    Latin/Persian texts keep matplotlib's default DejaVu Sans, which
    covers Latin plus every common reshaped Persian form. If no Arabic
    font is available the figure is left untouched (English titles)
    rather than failing the whole report.
    """
    if lang != "fa":
        return
    from matplotlib.text import Text

    try:
        regular, _bold = find_arabic_font()
    except ReportError:
        return
    from matplotlib import font_manager

    try:
        font_manager.fontManager.addfont(regular)
        arabic_family = font_manager.FontProperties(fname=regular).get_name()
    except Exception:
        arabic_family = None
    for obj in fig.findobj(lambda item: isinstance(item, Text)):
        text = obj.get_text()
        if text and contains_arabic(text):
            obj.set_text(reshape_persian(text))
            if arabic_family and not any("A" <= c <= "z" for c in text):
                obj.set_fontfamily(arabic_family)


# ---------------------------------------------------------------------------
# Shared context and labels
# ---------------------------------------------------------------------------

_OVERVIEW_LABEL_KEYS = {
    "rows": "ov_rows",
    "columns": "ov_columns",
    "column_names": "ov_column_names",
    "dtypes": "ov_dtypes",
    "memory_mb": "ov_memory_mb",
    "duplicate_rows": "ov_duplicate_rows",
    "total_missing": "ov_total_missing",
}

_TYPE_LABEL_KEYS = {
    "numeric": "report_type_numeric",
    "categorical": "report_type_categorical",
}


def overview_labels(eda: dict, lang: str) -> list[tuple[str, str]]:
    """Overview rows as (translated label, value) pairs.

    In Persian, list/dict values are joined with a Persian comma instead
    of Python's repr: a repr's brackets and quotes reorder badly under
    the bidi algorithm, while a plain joined list reads correctly.
    """
    rows = []
    for key, value in eda["overview"].items():
        label_key = _OVERVIEW_LABEL_KEYS.get(key)
        label = _t(label_key, lang) if label_key else key
        if lang == "fa" and isinstance(value, list):
            text = "، ".join(str(item) for item in value)
        elif lang == "fa" and isinstance(value, dict):
            text = "، ".join(f"{k}: {v}" for k, v in value.items())
        else:
            text = str(value)
        rows.append((label, text))
    return rows


def type_label(column_type: str, lang: str) -> str:
    """Translate a column type (numeric/categorical); anything else raw."""
    label_key = _TYPE_LABEL_KEYS.get(column_type)
    return _t(label_key, lang) if label_key else column_type


def build_report_context(
    df: pd.DataFrame, anomalies: dict | None = None, lang: str = "en"
) -> dict:
    """Compute the shared context every report format renders."""
    eda = eda_report(df)
    return {
        "eda": eda,
        "insights": key_insights(df, eda, lang=lang),
        "anomalies": anomalies,
    }


def _stats_rows(eda: dict) -> list[dict]:
    rows = []
    for column, summary in eda["columns"].items():
        rows.append(
            {
                "column": column,
                "type": summary["type"],
                "mean": summary.get("mean"),
                "median": summary.get("median"),
                "std": summary.get("std"),
                "min": summary.get("min"),
                "max": summary.get("max"),
                "unique": summary.get("unique"),
            }
        )
    return rows


def _chart_figures(df: pd.DataFrame, lang: str = "en") -> list[tuple[str, plt.Figure]]:
    """Matplotlib figures for static reports (histogram + correlation)."""
    figures = []
    numeric = df.select_dtypes(include="number")
    if len(numeric.columns) >= 1:
        fig, _ = matplotlib_histogram(df, str(numeric.columns[0]))
        _localize_matplotlib_figure(fig, lang)
        figures.append((_t("report_distribution", lang).format(column=numeric.columns[0]), fig))
    if len(numeric.columns) >= 2:
        fig, _ = correlation_graph(df)
        _localize_matplotlib_figure(fig, lang)
        figures.append((_t("report_correlation_graph", lang), fig))
    return figures


def _figure_png_bytes(fig: plt.Figure) -> bytes:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    return buffer.read()


def _anomaly_line(anomalies: dict, lang: str) -> str:
    return _t("report_anomaly_line", lang).format(
        method=anomalies["method"], n=anomalies["anomalies"],
        rows=anomalies["rows_analysed"],
    )


def generate_csv_report(
    df: pd.DataFrame, path: str | Path, anomalies: dict | None = None, lang: str = "en"
) -> Path:
    """Write the report as CSV (overview, column stats, insights)."""
    context = build_report_context(df, anomalies, lang=lang)
    eda = context["eda"]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["section", "key", "value"])
        for key, value in eda["overview"].items():
            writer.writerow(["overview", key, value])
        for row in _stats_rows(eda):
            writer.writerow(["column_stats", row["column"],
                             "; ".join(f"{k}={v}" for k, v in row.items() if k != "column")])
        for insight in context["insights"]:
            writer.writerow(["insight", "", insight])
        if anomalies:
            writer.writerow(["anomalies", "method", anomalies["method"]])
            writer.writerow(["anomalies", "count", anomalies["anomalies"]])
        else:
            writer.writerow(["anomalies", "note", _t("report_no_anomaly", lang)])
    log.info("CSV report written to {}", path)
    return path


def generate_excel_report(
    df: pd.DataFrame, path: str | Path, anomalies: dict | None = None, lang: str = "en"
) -> Path:
    """Write the report as a multi-sheet Excel workbook (XlsxWriter).

    XlsxWriter writes Unicode natively, so Persian text round-trips
    intact; Persian workbooks additionally get a right-to-left sheet
    view.
    """
    import xlsxwriter

    context = build_report_context(df, anomalies, lang=lang)
    eda = context["eda"]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(str(path))
    header = workbook.add_format({"bold": True, "bg_color": "#D9E2F3"})
    try:
        sheet = workbook.add_worksheet("Overview")
        if lang == "fa":
            sheet.right_to_left()
        sheet.write_row(0, 0, [_t("report_key", lang), _t("col_value", lang)], header)
        for row, (label, value) in enumerate(overview_labels(eda, lang), start=1):
            sheet.write_row(row, 0, [label, value])
        sheet.set_column(0, 1, 24)

        sheet = workbook.add_worksheet("Column stats")
        if lang == "fa":
            sheet.right_to_left()
        sheet.write_row(0, 0, [_t("col_column", lang), _t("col_type", lang),
                               _t("col_mean", lang), _t("col_median", lang),
                               _t("col_std", lang), _t("col_min", lang),
                               _t("col_max", lang), _t("col_unique", lang)], header)
        for row, stats in enumerate(_stats_rows(eda), start=1):
            values = [stats["column"], type_label(stats["type"], lang)]
            values += ["" if stats[c] is None else stats[c]
                       for c in ["mean", "median", "std", "min", "max", "unique"]]
            sheet.write_row(row, 0, values)
        sheet.set_column(0, 7, 18)

        sheet = workbook.add_worksheet("Missing values")
        if lang == "fa":
            sheet.right_to_left()
        sheet.write_row(0, 0, [_t("col_column", lang), _t("col_missing", lang),
                               _t("col_percent", lang)], header)
        for row, (col, info) in enumerate(eda["missing"]["columns"].items(), start=1):
            sheet.write_row(row, 0, [col, info["missing"], info["percent"]])
        sheet.set_column(0, 2, 18)

        if eda["correlation"] is not None:
            sheet = workbook.add_worksheet("Correlation")
            if lang == "fa":
                sheet.right_to_left()
            labels = list(eda["correlation"])
            sheet.write_row(0, 1, labels, header)
            for row, label in enumerate(labels, start=1):
                sheet.write(row, 0, label)
                for col, other in enumerate(labels, start=1):
                    value = eda["correlation"][label][other]
                    sheet.write(row, col, "" if value is None else value)

        sheet = workbook.add_worksheet("Insights")
        if lang == "fa":
            sheet.right_to_left()
        sheet.write_row(0, 0, [_t("report_insights", lang)], header)
        for row, insight in enumerate(context["insights"], start=1):
            sheet.write(row, 0, insight)
        sheet.set_column(0, 0, 110)

        sheet = workbook.add_worksheet("Anomalies")
        if lang == "fa":
            sheet.right_to_left()
        if anomalies:
            sheet.write_row(0, 0, ["Method", "Anomalies", "Rows analysed"], header)
            sheet.write_row(1, 0, [anomalies["method"], anomalies["anomalies"],
                                   anomalies["rows_analysed"]])
            rows = anomalies.get("anomaly_rows") or []
            if rows:
                sheet.write_row(3, 0, list(rows[0]), header)
                for row, record in enumerate(rows, start=4):
                    sheet.write_row(row, 0, [str(v) for v in record.values()])
        else:
            sheet.write(0, 0, _t("report_no_anomaly", lang))

        sheet = workbook.add_worksheet("Charts")
        if lang == "fa":
            sheet.right_to_left()
        row = 0
        for title, fig in _chart_figures(df, lang=lang):
            sheet.write(row, 0, title, header)
            sheet.insert_image(row + 1, 0, "chart.png",
                               {"image_data": io.BytesIO(_figure_png_bytes(fig))})
            row += 28
    finally:
        workbook.close()
    log.info("Excel report written to {}", path)
    return path


def generate_html_report(
    df: pd.DataFrame, path: str | Path, anomalies: dict | None = None, lang: str = "en"
) -> Path:
    """Write the report as a self-contained HTML page (Jinja2 + Plotly)."""
    from jinja2 import Environment, FileSystemLoader

    context = build_report_context(df, anomalies, lang=lang)
    eda = context["eda"]
    charts_html: list[str] = []
    numeric = df.select_dtypes(include="number")
    if len(numeric.columns) >= 1:
        charts_html.append(histogram(df, str(numeric.columns[0])).to_html(
            full_html=False, include_plotlyjs="cdn"))
    if len(numeric.columns) >= 2:
        charts_html.append(heatmap(df).to_html(full_html=False, include_plotlyjs=False))
    # Normalise column summaries so every key exists for the template.
    columns = {
        col: {
            "type": type_label(summary["type"], lang),
            "mean": summary.get("mean"),
            "median": summary.get("median"),
            "std": summary.get("std"),
            "min": summary.get("min"),
            "max": summary.get("max"),
            "unique": summary.get("unique"),
        }
        for col, summary in eda["columns"].items()
    }
    template_dir = Path(__file__).resolve().parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
    template = env.get_template("report.html.j2")
    rendered = template.render(
        title=_t("report_title", lang),
        lang=lang,
        direction="rtl" if lang == "fa" else "ltr",
        overview=overview_labels(eda, lang),
        missing=eda["missing"],
        columns=columns,
        anomalies=anomalies,
        anomaly_line=_anomaly_line(anomalies, lang) if anomalies else None,
        no_anomaly_note=_t("report_no_anomaly", lang),
        insights=context["insights"],
        charts_html=charts_html,
        labels={
            "overview": _t("report_overview", lang),
            "quality": _t("report_quality", lang),
            "stats": _t("report_stats", lang),
            "anomalies": _t("report_anomalies", lang),
            "insights": _t("report_insights", lang),
            "chart": _t("report_chart", lang),
            "generated_by": _t("report_generated_by", lang),
            "key": _t("report_key", lang),
            "value": _t("col_value", lang),
            "column": _t("col_column", lang),
            "missing": _t("col_missing", lang),
            "missing_pct": _t("col_percent", lang),
            "type": _t("col_type", lang),
            "mean": _t("col_mean", lang),
            "median": _t("col_median", lang),
            "std": _t("col_std", lang),
            "min": _t("col_min", lang),
            "max": _t("col_max", lang),
            "unique": _t("col_unique", lang),
        },
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    log.info("HTML report written to {}", path)
    return path


def generate_pdf_report(
    df: pd.DataFrame, path: str | Path, anomalies: dict | None = None, lang: str = "en"
) -> Path:
    """Write the report as PDF (ReportLab Platypus + matplotlib charts).

    Persian text is reshaped + reordered and set in the embedded Arabic
    font; when the report is Persian (or any cell holds Persian text)
    and no verified Arabic font exists, this raises ReportError instead
    of writing a broken file.
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Image,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    context = build_report_context(df, anomalies, lang=lang)
    eda = context["eda"]

    def needs_arabic_font() -> bool:
        if lang == "fa":
            return True
        probes = [str(c) for c in eda["overview"].values()]
        probes += list(eda["columns"])
        probes += context["insights"]
        return any(contains_arabic(probe) for probe in probes)

    if needs_arabic_font():
        ensure_pdf_fonts()

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sample = getSampleStyleSheet()
    if lang == "fa":
        regular, bold = _PDF_FONT_NAMES
        title_style = ParagraphStyle("FaTitle", parent=sample["Title"], fontName=bold,
                                     alignment=TA_CENTER)
        heading_style = ParagraphStyle("FaHeading2", parent=sample["Heading2"], fontName=bold,
                                       alignment=TA_RIGHT)
        body_style = ParagraphStyle("FaBody", parent=sample["BodyText"], fontName=regular,
                                    alignment=TA_RIGHT)
        cell_style = ParagraphStyle("FaCell", parent=sample["BodyText"], fontName=regular,
                                    fontSize=9, leading=12, alignment=TA_RIGHT)
    else:
        title_style, heading_style, body_style = sample["Title"], sample["Heading2"], sample["BodyText"]
        cell_style = ParagraphStyle("EnCell", parent=sample["BodyText"], fontSize=9, leading=12)

    def cell(value) -> object:
        """Render text cells as Paragraphs when Persian shaping is needed."""
        if isinstance(value, str) and (lang == "fa" or contains_arabic(value)):
            return Paragraph(persian_paragraph_markup(value), cell_style)
        return value

    def para(text: str, style, bold: bool = False) -> Paragraph:
        if lang == "fa" or contains_arabic(text):
            return Paragraph(persian_paragraph_markup(text, bold=bold), style)
        return Paragraph(html.escape(text), style)

    story: list = [para(_t("report_title", lang), title_style, bold=True)]
    story.append(para(_t("report_overview", lang), heading_style, bold=True))
    overview_data = [[cell(_t("report_key", lang)), cell(_t("col_value", lang))]] + [
        [cell(label), cell(value)] for label, value in overview_labels(eda, lang)
    ]
    table = Table(overview_data, colWidths=[5 * cm, 11 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(table)

    story.append(para(_t("report_quality", lang), heading_style, bold=True))
    missing_data = [[cell(_t("col_column", lang)), cell(_t("col_missing", lang)),
                     cell(_t("col_percent", lang))]] + [
        [cell(col), info["missing"], info["percent"]]
        for col, info in eda["missing"]["columns"].items()
    ]
    table = Table(missing_data, colWidths=[7 * cm, 4 * cm, 5 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(table)

    story.append(para(_t("report_stats", lang), heading_style, bold=True))
    stats_header = [cell(_t("col_column", lang)), cell(_t("col_type", lang)),
                    cell(_t("col_mean", lang)), cell(_t("col_median", lang)),
                    cell(_t("col_std", lang)), cell(_t("col_min", lang)),
                    cell(_t("col_max", lang))]
    stats_data = [stats_header] + [
        [cell(row["column"]), cell(type_label(row["type"], lang)),
         "" if row["mean"] is None else round(row["mean"], 3),
         "" if row["median"] is None else round(row["median"], 3),
         "" if row["std"] is None else round(row["std"], 3),
         "" if row["min"] is None else round(row["min"], 3),
         "" if row["max"] is None else round(row["max"], 3)]
        for row in _stats_rows(eda)
    ]
    table = Table(stats_data, colWidths=[3.2 * cm, 2.2 * cm] + [1.9 * cm] * 5)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    story.append(table)

    story.append(para(_t("report_anomalies", lang), heading_style, bold=True))
    if anomalies:
        story.append(para(_anomaly_line(anomalies, lang), body_style))
    else:
        story.append(para(_t("report_no_anomaly", lang), body_style))

    story.append(para(_t("report_insights", lang), heading_style, bold=True))
    for insight in context["insights"]:
        story.append(para(f"• {insight}", body_style))

    for title, fig in _chart_figures(df, lang=lang):
        story.append(Spacer(1, 0.4 * cm))
        story.append(para(title, heading_style, bold=True))
        story.append(Image(io.BytesIO(_figure_png_bytes(fig)), width=16 * cm, height=9 * cm))

    SimpleDocTemplate(str(path), pagesize=A4).build(story)
    log.info("PDF report written to {}", path)
    return path


_GENERATORS = {
    "pdf": generate_pdf_report,
    "xlsx": generate_excel_report,
    "csv": generate_csv_report,
    "html": generate_html_report,
}


def generate_report(
    df: pd.DataFrame,
    fmt: str,
    path: str | Path,
    anomalies: dict | None = None,
    lang: str = "en",
) -> Path:
    """Generate a report in ``fmt`` (pdf, xlsx, csv, html) at ``path``."""
    generator = _GENERATORS.get(fmt)
    if generator is None:
        raise ReportError(f"Unknown report format '{fmt}'. Choose from {REPORT_FORMATS}.")
    return generator(df, path, anomalies, lang=lang)
