"""
cli.py — Command-line interface for agency-report-builder.

Commands:
  build     Generate a client report from GA4 + GSC data.
  preview   Build HTML only (no PDF), open in browser.
  validate  Validate a report-config.json file without fetching data.

Usage:
  report-builder build --config ./configs/acme.json
  report-builder build --config ./configs/acme.json --format html --format pdf
  report-builder validate --config ./configs/acme.json
  report-builder preview --config ./configs/acme.json
"""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()


@click.group()
@click.version_option("1.0.0", prog_name="report-builder")
def cli():
    """Generate branded HTML/PDF marketing reports from GA4 and Google Search Console."""
    pass


@cli.command()
@click.option("--config", "-c", "config_path", type=click.Path(exists=True), required=True,
              help="Path to report-config.json")
@click.option("--format", "-f", "formats", multiple=True,
              type=click.Choice(["html", "pdf"], case_sensitive=False),
              default=None, help="Output format(s). Overrides config file setting.")
@click.option("--dry-run", is_flag=True, help="Validate config only; do not fetch data or write files.")
def build(config_path: str, formats: tuple[str], dry_run: bool) -> None:
    """Fetch GA4 + GSC data and generate a client performance report."""
    from .config import load_config
    from .ga4 import build_ga4_client, fetch_ga4_data
    from .gsc import build_gsc_client, fetch_gsc_data
    from .builder import build_report_context, render_html, write_html
    from .pdf import render_pdf

    console.print(Panel.fit("[bold cyan]Agency Report Builder[/bold cyan]", border_style="cyan"))

    # Load config
    try:
        config = load_config(config_path)
        if formats:
            config.formats = list(formats)
    except Exception as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        sys.exit(1)

    console.print(f"  Client:    [bold]{config.client_name}[/bold]")
    console.print(f"  Period:    {config.date_range.start} → {config.date_range.end}")
    console.print(f"  Formats:   {', '.join(config.formats)}")
    console.print(f"  Output:    {config.output_dir}")
    console.print("")

    if dry_run:
        console.print("[yellow]--dry-run: config is valid. Exiting without fetching data.[/yellow]")
        return

    # Build API clients
    try:
        ga4_client = build_ga4_client(str(config.credentials_path))
        gsc_service = build_gsc_client(str(config.credentials_path))
    except Exception as exc:
        console.print(f"[red]Authentication error:[/red] {exc}")
        sys.exit(1)

    # Fetch data
    with console.status("[cyan]Fetching GA4 data...[/cyan]"):
        try:
            ga4_data = fetch_ga4_data(
                ga4_client,
                config.ga4_property_id,
                config.date_range.start,
                config.date_range.end,
                compare_to_previous=config.compare_to_previous,
                top_n=config.top_n,
            )
        except Exception as exc:
            console.print(f"[red]GA4 fetch error:[/red] {exc}")
            sys.exit(1)

    with console.status("[cyan]Fetching GSC data...[/cyan]"):
        try:
            gsc_data = fetch_gsc_data(
                gsc_service,
                config.gsc_site_url,
                config.date_range.start,
                config.date_range.end,
                compare_to_previous=config.compare_to_previous,
                top_n=config.top_n,
            )
        except Exception as exc:
            console.print(f"[red]GSC fetch error:[/red] {exc}")
            sys.exit(1)

    # Print KPI summary to terminal
    _print_kpi_table(ga4_data, gsc_data)

    # Build report context
    ctx = build_report_context(config, ga4_data, gsc_data)
    html_string = render_html(ctx)

    # Determine filename base
    slug = config.client_name.lower().replace(" ", "-")
    period = config.date_range.end[:7]  # YYYY-MM
    base_name = f"{slug}-report-{period}"

    output_paths = []

    # Write HTML
    if "html" in config.formats:
        html_path = config.output_dir / f"{base_name}.html"
        write_html(html_string, html_path)
        output_paths.append(html_path)

    # Write PDF
    if "pdf" in config.formats:
        pdf_path = config.output_dir / f"{base_name}.pdf"
        try:
            render_pdf(html_string, pdf_path)
            output_paths.append(pdf_path)
        except Exception as exc:
            console.print(f"[yellow]PDF generation skipped:[/yellow] {exc}")

    console.print("")
    console.print("[bold green]✔  Report generated:[/bold green]")
    for p in output_paths:
        console.print(f"   → [link={p.as_uri()}]{p}[/link]")
    console.print("")


@cli.command()
@click.option("--config", "-c", "config_path", type=click.Path(exists=True), required=True,
              help="Path to report-config.json")
def validate(config_path: str) -> None:
    """Validate a report config file without fetching any data."""
    from .config import load_config

    try:
        config = load_config(config_path)
        console.print("[green]✔  Config is valid.[/green]")
        console.print(f"   Client:      {config.client_name}")
        console.print(f"   GA4 prop:    {config.ga4_property_id}")
        console.print(f"   GSC site:    {config.gsc_site_url}")
        console.print(f"   Period:      {config.date_range.start} → {config.date_range.end}")
        console.print(f"   Credentials: {config.credentials_path}")
    except Exception as exc:
        console.print(f"[red]✖  Config invalid:[/red] {exc}")
        sys.exit(1)


@cli.command()
@click.option("--config", "-c", "config_path", type=click.Path(exists=True), required=True,
              help="Path to report-config.json")
def preview(config_path: str) -> None:
    """Generate HTML report and open it in the default browser."""
    from .config import load_config
    from .ga4 import build_ga4_client, fetch_ga4_data
    from .gsc import build_gsc_client, fetch_gsc_data
    from .builder import build_report_context, render_html, write_html

    config = load_config(config_path)
    config.formats = ["html"]

    ga4_client = build_ga4_client(str(config.credentials_path))
    gsc_service = build_gsc_client(str(config.credentials_path))

    ga4_data = fetch_ga4_data(ga4_client, config.ga4_property_id,
                               config.date_range.start, config.date_range.end)
    gsc_data = fetch_gsc_data(gsc_service, config.gsc_site_url,
                               config.date_range.start, config.date_range.end)

    ctx = build_report_context(config, ga4_data, gsc_data)
    html = render_html(ctx)

    slug = config.client_name.lower().replace(" ", "-")
    period = config.date_range.end[:7]
    html_path = config.output_dir / f"{slug}-preview-{period}.html"
    write_html(html, html_path)

    webbrowser.open(html_path.as_uri())
    console.print(f"[cyan]Preview opened:[/cyan] {html_path}")


def _print_kpi_table(ga4, gsc) -> None:
    """Print a Rich table of key metrics to the terminal."""
    table = Table(title="Report KPIs", box=box.ROUNDED, border_style="cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_column("vs Previous", justify="right")

    from .ga4 import pct_change

    def _arrow(v):
        if v is None:
            return "—"
        return f"[green]+{v}%[/green]" if v >= 0 else f"[red]{v}%[/red]"

    table.add_row("Sessions (GA4)", f"{ga4.kpis.sessions:,}",
                  _arrow(pct_change(ga4.kpis.sessions, ga4.kpis.sessions_prev)))
    table.add_row("Users (GA4)", f"{ga4.kpis.users:,}",
                  _arrow(pct_change(ga4.kpis.users, ga4.kpis.users_prev)))
    table.add_row("Conversions (GA4)", f"{ga4.kpis.conversions:,}",
                  _arrow(pct_change(ga4.kpis.conversions, ga4.kpis.conversions_prev)))
    table.add_row("Conv. Rate (GA4)", f"{ga4.kpis.conversion_rate}%", "—")
    table.add_row("Clicks (GSC)", f"{gsc.kpis.clicks:,}",
                  _arrow(pct_change(gsc.kpis.clicks, gsc.kpis.clicks_prev)))
    table.add_row("Impressions (GSC)", f"{gsc.kpis.impressions:,}",
                  _arrow(pct_change(gsc.kpis.impressions, gsc.kpis.impressions_prev)))
    table.add_row("Avg Position (GSC)", f"{gsc.kpis.position}", "—")

    console.print(table)
