"""Report generation: PDF, Excel, CSV, HTML.

Every report contains the same honest sections — dataset overview, data
quality assessment, statistical summaries, detected anomalies, and key
insights derived from the actual numbers (see ``core.analyzer``). Charts
in PDF/Excel are matplotlib figures (no extra renderer needed); the HTML
report embeds interactive Plotly figures.

An ``anomalies`` argument is the result dict of an ml_engine run (or
``None`` when no detection was run — the report says so instead of
pretending otherwise).
"""

from __future__ import annotations

import csv
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


def build_report_context(df: pd.DataFrame, anomalies: dict | None = None) -> dict:
    """Compute the shared context every report format renders."""
    eda = eda_report(df)
    return {
        "eda": eda,
        "insights": key_insights(df, eda),
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


def _chart_figures(df: pd.DataFrame) -> list[tuple[str, plt.Figure]]:
    """Matplotlib figures for static reports (histogram + correlation)."""
    figures = []
    numeric = df.select_dtypes(include="number")
    if len(numeric.columns) >= 1:
        fig, _ = matplotlib_histogram(df, str(numeric.columns[0]))
        figures.append((f"Distribution of {numeric.columns[0]}", fig))
    if len(numeric.columns) >= 2:
        fig, _ = correlation_graph(df)
        figures.append(("Correlation graph", fig))
    return figures


def _figure_png_bytes(fig: plt.Figure) -> bytes:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    return buffer.read()


def generate_csv_report(
    df: pd.DataFrame, path: str | Path, anomalies: dict | None = None
) -> Path:
    """Write the report as CSV (overview, column stats, insights)."""
    context = build_report_context(df, anomalies)
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
            writer.writerow(["anomalies", "note", "No anomaly detection was run."])
    log.info("CSV report written to {}", path)
    return path


def generate_excel_report(
    df: pd.DataFrame, path: str | Path, anomalies: dict | None = None
) -> Path:
    """Write the report as a multi-sheet Excel workbook (XlsxWriter)."""
    import xlsxwriter

    context = build_report_context(df, anomalies)
    eda = context["eda"]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(str(path))
    header = workbook.add_format({"bold": True, "bg_color": "#D9E2F3"})
    try:
        sheet = workbook.add_worksheet("Overview")
        sheet.write_row(0, 0, ["Key", "Value"], header)
        for row, (key, value) in enumerate(eda["overview"].items(), start=1):
            sheet.write_row(row, 0, [key, str(value)])
        sheet.set_column(0, 1, 24)

        sheet = workbook.add_worksheet("Column stats")
        columns = ["column", "type", "mean", "median", "std", "min", "max", "unique"]
        sheet.write_row(0, 0, columns, header)
        for row, stats in enumerate(_stats_rows(eda), start=1):
            sheet.write_row(row, 0, ["" if stats[c] is None else stats[c] for c in columns])
        sheet.set_column(0, 7, 18)

        sheet = workbook.add_worksheet("Missing values")
        sheet.write_row(0, 0, ["Column", "Missing", "Percent"], header)
        for row, (col, info) in enumerate(eda["missing"]["columns"].items(), start=1):
            sheet.write_row(row, 0, [col, info["missing"], info["percent"]])
        sheet.set_column(0, 2, 18)

        if eda["correlation"] is not None:
            sheet = workbook.add_worksheet("Correlation")
            labels = list(eda["correlation"])
            sheet.write_row(0, 1, labels, header)
            for row, label in enumerate(labels, start=1):
                sheet.write(row, 0, label)
                for col, other in enumerate(labels, start=1):
                    value = eda["correlation"][label][other]
                    sheet.write(row, col, "" if value is None else value)

        sheet = workbook.add_worksheet("Insights")
        sheet.write_row(0, 0, ["Insight"], header)
        for row, insight in enumerate(context["insights"], start=1):
            sheet.write(row, 0, insight)
        sheet.set_column(0, 0, 110)

        sheet = workbook.add_worksheet("Anomalies")
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
            sheet.write(0, 0, "No anomaly detection was run for this report.")

        sheet = workbook.add_worksheet("Charts")
        row = 0
        for title, fig in _chart_figures(df):
            sheet.write(row, 0, title, header)
            sheet.insert_image(row + 1, 0, "chart.png",
                               {"image_data": io.BytesIO(_figure_png_bytes(fig))})
            row += 28
    finally:
        workbook.close()
    log.info("Excel report written to {}", path)
    return path


def generate_html_report(
    df: pd.DataFrame, path: str | Path, anomalies: dict | None = None
) -> Path:
    """Write the report as a self-contained HTML page (Jinja2 + Plotly)."""
    from jinja2 import Environment, FileSystemLoader

    context = build_report_context(df, anomalies)
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
            "type": summary["type"],
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
        title="Personal Data Analytics Report",
        overview={k: str(v) for k, v in eda["overview"].items()},
        missing=eda["missing"],
        columns=columns,
        anomalies=anomalies,
        insights=context["insights"],
        charts_html=charts_html,
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    log.info("HTML report written to {}", path)
    return path


def generate_pdf_report(
    df: pd.DataFrame, path: str | Path, anomalies: dict | None = None
) -> Path:
    """Write the report as PDF (ReportLab Platypus + matplotlib charts)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Image,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    context = build_report_context(df, anomalies)
    eda = context["eda"]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    story: list = [Paragraph("Personal Data Analytics Report", styles["Title"])]
    story.append(Paragraph("Dataset overview", styles["Heading2"]))
    overview_data = [["Key", "Value"]] + [
        [str(k), str(v)] for k, v in eda["overview"].items()
    ]
    table = Table(overview_data, colWidths=[5 * cm, 11 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(table)

    story.append(Paragraph("Data quality assessment", styles["Heading2"]))
    missing_data = [["Column", "Missing", "Percent"]] + [
        [col, info["missing"], info["percent"]]
        for col, info in eda["missing"]["columns"].items()
    ]
    table = Table(missing_data, colWidths=[7 * cm, 4 * cm, 5 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(table)

    story.append(Paragraph("Statistical summaries", styles["Heading2"]))
    stats_header = ["Column", "Type", "Mean", "Median", "Std", "Min", "Max"]
    stats_data = [stats_header] + [
        [row["column"], row["type"],
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

    story.append(Paragraph("Detected anomalies", styles["Heading2"]))
    if anomalies:
        story.append(Paragraph(
            f"Method: {anomalies['method']} — {anomalies['anomalies']} anomalies "
            f"in {anomalies['rows_analysed']} analysed rows.", styles["BodyText"]))
    else:
        story.append(Paragraph("No anomaly detection was run for this report.",
                               styles["BodyText"]))

    story.append(Paragraph("Key insights", styles["Heading2"]))
    for insight in context["insights"]:
        story.append(Paragraph(f"• {insight}", styles["BodyText"]))

    for title, fig in _chart_figures(df):
        story.append(Spacer(1, 0.4 * cm))
        story.append(Paragraph(title, styles["Heading2"]))
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
) -> Path:
    """Generate a report in ``fmt`` (pdf, xlsx, csv, html) at ``path``."""
    generator = _GENERATORS.get(fmt)
    if generator is None:
        raise ReportError(f"Unknown report format '{fmt}'. Choose from {REPORT_FORMATS}.")
    return generator(df, path, anomalies)
