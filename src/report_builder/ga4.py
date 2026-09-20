"""
ga4.py — Google Analytics 4 Data API client.

Fetches key metrics and dimension breakdowns for a reporting period:
  - Overall KPIs: sessions, users, new users, key events (GA4's name for conversions since 2024), key-event rate
  - Channel breakdown: sessions, conversions per default channel group
  - Top pages: pageviews, average engagement time
  - Device split: sessions by device category
  - Period-over-period comparison (optional)

Uses the google-analytics-data library (GA4 Data API v1beta).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Metric,
    OrderBy,
    RunReportRequest,
)
from google.oauth2 import service_account

logger = logging.getLogger(__name__)


# ── Data containers ───────────────────────────────────────────────────────────

@dataclass
class GA4KPIs:
    sessions: int = 0
    users: int = 0
    new_users: int = 0
    conversions: int = 0
    conversion_rate: float = 0.0  # %
    avg_session_duration: float = 0.0  # seconds
    bounce_rate: float = 0.0  # %

    # Comparison (previous period)
    sessions_prev: int = 0
    users_prev: int = 0
    conversions_prev: int = 0


@dataclass
class ChannelRow:
    channel: str
    sessions: int
    conversions: int
    conversion_rate: float


@dataclass
class PageRow:
    page_path: str
    page_title: str
    pageviews: int
    avg_engagement_sec: float


@dataclass
class DeviceRow:
    device: str
    sessions: int
    sessions_pct: float


@dataclass
class GA4ReportData:
    kpis: GA4KPIs = field(default_factory=GA4KPIs)
    channels: list[ChannelRow] = field(default_factory=list)
    top_pages: list[PageRow] = field(default_factory=list)
    devices: list[DeviceRow] = field(default_factory=list)
    property_id: str = ""
    date_start: str = ""
    date_end: str = ""


# ── Client factory ────────────────────────────────────────────────────────────

def build_ga4_client(credentials_path: str) -> BetaAnalyticsDataClient:
    """
    Build a GA4 Data API client from a service account key file.

    Args:
        credentials_path: Path to a Google service account JSON key file.

    Returns:
        BetaAnalyticsDataClient
    """
    creds = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=["https://www.googleapis.com/auth/analytics.readonly"],
    )
    return BetaAnalyticsDataClient(credentials=creds)


# ── Main fetch function ───────────────────────────────────────────────────────

def fetch_ga4_data(
    client: BetaAnalyticsDataClient,
    property_id: str,
    date_start: str,
    date_end: str,
    compare_to_previous: bool = True,
    top_n: int = 10,
) -> GA4ReportData:
    """
    Fetch all metrics needed for the client report.

    Args:
        client:               Authenticated GA4 Data API client.
        property_id:          GA4 property ID, e.g. "properties/123456789".
        date_start:           Start date string (YYYY-MM-DD).
        date_end:             End date string (YYYY-MM-DD).
        compare_to_previous:  If True, also fetch the previous period KPIs.
        top_n:                Maximum rows for top-pages and channel tables.

    Returns:
        GA4ReportData populated with fetched data.
    """
    data = GA4ReportData(property_id=property_id, date_start=date_start, date_end=date_end)

    # 1. Overall KPIs
    data.kpis = _fetch_kpis(client, property_id, date_start, date_end, compare_to_previous)

    # 2. Channel breakdown
    data.channels = _fetch_channels(client, property_id, date_start, date_end, top_n)

    # 3. Top pages
    data.top_pages = _fetch_top_pages(client, property_id, date_start, date_end, top_n)

    # 4. Device split
    data.devices = _fetch_devices(client, property_id, date_start, date_end)

    return data


# ── Private helpers ───────────────────────────────────────────────────────────

def _run_report(client: BetaAnalyticsDataClient, request: RunReportRequest) -> Any:
    """Execute a report request with basic error logging."""
    try:
        return client.run_report(request)
    except Exception as exc:
        logger.error("GA4 API error: %s", exc)
        raise


def _fetch_kpis(
    client: BetaAnalyticsDataClient,
    property_id: str,
    date_start: str,
    date_end: str,
    compare_to_previous: bool,
) -> GA4KPIs:
    date_ranges = [DateRange(start_date=date_start, end_date=date_end)]
    if compare_to_previous:
        prev_start, prev_end = _previous_period(date_start, date_end)
        date_ranges.append(DateRange(start_date=prev_start, end_date=prev_end))

    req = RunReportRequest(
        property=property_id,
        date_ranges=date_ranges,
        metrics=[
            Metric(name="sessions"),
            Metric(name="totalUsers"),
            Metric(name="newUsers"),
            Metric(name="keyEvents"),
            Metric(name="sessionKeyEventRate"),
            Metric(name="averageSessionDuration"),
            Metric(name="bounceRate"),
        ],
    )
    resp = _run_report(client, req)

    return parse_kpi_rows(resp.rows, compare_to_previous)


def parse_kpi_rows(rows, compare_to_previous: bool) -> GA4KPIs:
    """Parse the KPI report. With two date ranges GA4 adds a ``dateRange`` dimension
    (``date_range_0`` = current, ``date_range_1`` = previous); rows are matched on it
    rather than on position, which the API does not guarantee."""
    kpis = GA4KPIs()
    current, previous = None, None
    for row in rows:
        tag = row.dimension_values[0].value if row.dimension_values else "date_range_0"
        if tag == "date_range_1":
            previous = row
        elif current is None:
            current = row

    if current is not None:
        vals = [float(v.value) for v in current.metric_values]
        kpis.sessions = int(vals[0])
        kpis.users = int(vals[1])
        kpis.new_users = int(vals[2])
        kpis.conversions = int(vals[3])
        kpis.conversion_rate = round(vals[4] * 100, 2)
        kpis.avg_session_duration = round(vals[5], 1)
        kpis.bounce_rate = round(vals[6] * 100, 1)

    if compare_to_previous and previous is not None:
        prev_vals = [float(v.value) for v in previous.metric_values]
        kpis.sessions_prev = int(prev_vals[0])
        kpis.users_prev = int(prev_vals[1])
        kpis.conversions_prev = int(prev_vals[3])

    return kpis


def _fetch_channels(
    client: BetaAnalyticsDataClient,
    property_id: str,
    date_start: str,
    date_end: str,
    top_n: int,
) -> list[ChannelRow]:
    req = RunReportRequest(
        property=property_id,
        date_ranges=[DateRange(start_date=date_start, end_date=date_end)],
        dimensions=[Dimension(name="sessionDefaultChannelGroup")],
        metrics=[
            Metric(name="sessions"),
            Metric(name="keyEvents"),
            Metric(name="sessionKeyEventRate"),
        ],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=top_n,
    )
    resp = _run_report(client, req)
    rows = []
    for row in resp.rows:
        channel = row.dimension_values[0].value
        sessions = int(float(row.metric_values[0].value))
        conversions = int(float(row.metric_values[1].value))
        cvr = round(float(row.metric_values[2].value) * 100, 2)
        rows.append(ChannelRow(channel=channel, sessions=sessions, conversions=conversions, conversion_rate=cvr))
    return rows


def _fetch_top_pages(
    client: BetaAnalyticsDataClient,
    property_id: str,
    date_start: str,
    date_end: str,
    top_n: int,
) -> list[PageRow]:
    req = RunReportRequest(
        property=property_id,
        date_ranges=[DateRange(start_date=date_start, end_date=date_end)],
        dimensions=[
            Dimension(name="pagePath"),
            Dimension(name="pageTitle"),
        ],
        metrics=[
            Metric(name="screenPageViews"),
            Metric(name="averageSessionDuration"),
        ],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"), desc=True)],
        limit=top_n,
    )
    resp = _run_report(client, req)
    rows = []
    for row in resp.rows:
        path = row.dimension_values[0].value
        title = row.dimension_values[1].value
        views = int(float(row.metric_values[0].value))
        avg_dur = round(float(row.metric_values[1].value), 1)
        rows.append(PageRow(page_path=path, page_title=title, pageviews=views, avg_engagement_sec=avg_dur))
    return rows


def _fetch_devices(
    client: BetaAnalyticsDataClient,
    property_id: str,
    date_start: str,
    date_end: str,
) -> list[DeviceRow]:
    req = RunReportRequest(
        property=property_id,
        date_ranges=[DateRange(start_date=date_start, end_date=date_end)],
        dimensions=[Dimension(name="deviceCategory")],
        metrics=[Metric(name="sessions")],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
    )
    resp = _run_report(client, req)
    total = sum(int(float(row.metric_values[0].value)) for row in resp.rows) or 1
    rows = []
    for row in resp.rows:
        device = row.dimension_values[0].value
        sessions = int(float(row.metric_values[0].value))
        pct = round(sessions / total * 100, 1)
        rows.append(DeviceRow(device=device, sessions=sessions, sessions_pct=pct))
    return rows


def _previous_period(start: str, end: str) -> tuple[str, str]:
    """Compute the previous period of equal length to start→end."""
    from datetime import datetime, timedelta
    fmt = "%Y-%m-%d"
    s = datetime.strptime(start, fmt)
    e = datetime.strptime(end, fmt)
    delta = e - s + timedelta(days=1)
    prev_end = s - timedelta(days=1)
    prev_start = prev_end - delta + timedelta(days=1)
    return prev_start.strftime(fmt), prev_end.strftime(fmt)


def pct_change(current: float | int, previous: float | int) -> float | None:
    """Return percentage change, or None if previous is 0."""
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)
