"""
pdf.py — PDF generation using WeasyPrint.

Converts the rendered HTML report to a PDF file.
WeasyPrint renders the HTML (including CSS) and outputs a print-quality PDF.

Requirements:
  - weasyprint >= 61
  - System packages: pango, cairo, gdk-pixbuf (see README Installation for platform setup)
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def render_pdf(html_string: str, output_path: Path) -> None:
    """
    Render HTML to a PDF file using WeasyPrint.

    Args:
        html_string:  Fully rendered HTML document string.
        output_path:  Filesystem path to write the PDF file.

    Raises:
        ImportError: If WeasyPrint is not installed.
        OSError: If WeasyPrint system dependencies are missing.
    """
    try:
        from weasyprint import CSS, HTML
    except ImportError as exc:
        raise ImportError(
            "WeasyPrint is required for PDF output. Install it with:\n"
            "  pip install weasyprint\n"
            "On macOS you also need: brew install pango cairo gdk-pixbuf\n"
            "On Ubuntu/Debian: apt-get install libpango-1.0-0 libcairo2 libgdk-pixbuf2.0-0"
        ) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print_css = CSS(string="""
        @page {
            size: A4;
            margin: 1.5cm 1.5cm 2cm 1.5cm;
        }
        body {
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
        }
        .no-print {
            display: none !important;
        }
        table { page-break-inside: avoid; }
        .section { page-break-inside: avoid; }
    """)

    try:
        doc = HTML(string=html_string).write_pdf(stylesheets=[print_css])
        output_path.write_bytes(doc)
        logger.info("PDF report written → %s", output_path)
    except Exception as exc:
        logger.error("PDF generation failed: %s", exc)
        raise RuntimeError(
            f"WeasyPrint failed to generate PDF: {exc}\n"
            "Ensure system dependencies (pango, cairo) are installed."
        ) from exc
