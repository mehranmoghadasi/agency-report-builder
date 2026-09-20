"""
builder.py — Assembles all data into a rendered HTML report string.

Uses Jinja2 to render the HTML template with GA4 and GSC data,
branding, and computed metrics. The rendered string is then either
written as an HTML file or passed to the PDF renderer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import ReportConfig
from .ga4 import GA4ReportData, pct_change
from .gsc import GSCReportData

logger = logging.getLogger(__name__)

# Resolve template directory relative to this file
TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass
class ReportContext:
    """All data passed to the Jinja2 template."""
    config: ReportConfig

    # Core data
    ga4: GA4ReportData
    gsc: GSCReportData

    # Computed helpers
    ga4_sessions_change: float | None = None
    ga4_users_change: float | None = None
    ga4_conversions_change: float | None = None
    gsc_clicks_change: float | None = None
    gsc_impressions_change: float | None = None

    # Report metadata
    generated_at: str = ""
    report_period: str = ""


def build_report_context(config: ReportConfig, ga4: GA4ReportData, gsc: GSCReportData) -> ReportContext:
    """
    Combine raw API data and config into a ReportContext ready for templating.
    Computes period-over-period change metrics.
    """
    ctx = ReportContext(config=config, ga4=ga4, gsc=gsc)

    # Compute PoP changes
    ctx.ga4_sessions_change = pct_change(ga4.kpis.sessions, ga4.kpis.sessions_prev)
    ctx.ga4_users_change = pct_change(ga4.kpis.users, ga4.kpis.users_prev)
    ctx.ga4_conversions_change = pct_change(ga4.kpis.conversions, ga4.kpis.conversions_prev)
    ctx.gsc_clicks_change = pct_change(gsc.kpis.clicks, gsc.kpis.clicks_prev)
    ctx.gsc_impressions_change = pct_change(gsc.kpis.impressions, gsc.kpis.impressions_prev)

    # Report metadata
    ctx.generated_at = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    ctx.report_period = f"{config.date_range.start} to {config.date_range.end}"

    return ctx


def render_html(ctx: ReportContext) -> str:
    """
    Render the HTML report from the Jinja2 template.

    Args:
        ctx: Populated ReportContext.

    Returns:
        Rendered HTML string.
    """
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )

    # Register custom filters
    env.filters["fmt_int"] = lambda v: f"{int(v):,}" if v is not None else "—"
    env.filters["fmt_float"] = lambda v, n=1: f"{v:.{n}f}" if v is not None else "—"
    env.filters["fmt_pct"] = lambda v: f"{v:+.1f}%" if v is not None else "—"
    env.filters["change_class"] = lambda v: (
        "positive" if v is not None and v > 0 else
        "negative" if v is not None and v < 0 else
        "neutral"
    )
    env.filters["fmt_duration"] = _fmt_duration

    template = env.get_template("report.html.j2")

    return template.render(
        config=ctx.config,
        ga4=ctx.ga4,
        gsc=ctx.gsc,
        ga4_sessions_change=ctx.ga4_sessions_change,
        ga4_users_change=ctx.ga4_users_change,
        ga4_conversions_change=ctx.ga4_conversions_change,
        gsc_clicks_change=ctx.gsc_clicks_change,
        gsc_impressions_change=ctx.gsc_impressions_change,
        generated_at=ctx.generated_at,
        report_period=ctx.report_period,
    )


def write_html(rendered: str, output_path: Path) -> None:
    """Write rendered HTML to a file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    logger.info("HTML report written → %s", output_path)


def _fmt_duration(seconds: float) -> str:
    """Format seconds as 'm:ss' string."""
    try:
        seconds = int(seconds)
        m, s = divmod(seconds, 60)
        return f"{m}:{s:02d}"
    except (TypeError, ValueError):
        return "—"
