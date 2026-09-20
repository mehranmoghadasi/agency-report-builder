"""
gsc.py — Google Search Console Search Analytics API client.

Fetches organic search metrics for a reporting period:
  - Overall clicks, impressions, CTR, average position
  - Top queries (keyword performance)
  - Top pages (URL-level performance)
  - Device split
  - Period-over-period comparison (optional)

Uses the google-api-python-client library with OAuth2/service account auth.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
ROW_LIMIT = 1000  # Max rows per GSC API call


# ── Data containers ───────────────────────────────────────────────────────────

@dataclass
class GSCKPIs:
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0     # %
    position: float = 0.0

    # Previous period
    clicks_prev: int = 0
    impressions_prev: int = 0


@dataclass
class QueryRow:
    query: str
    clicks: int
    impressions: int
    ctr: float
    position: float


@dataclass
class GSCPageRow:
    page: str
    clicks: int
    impressions: int
    ctr: float
    position: float


@dataclass
class GSCReportData:
    kpis: GSCKPIs = field(default_factory=GSCKPIs)
    top_queries: list[QueryRow] = field(default_factory=list)
    top_pages: list[GSCPageRow] = field(default_factory=list)
    site_url: str = ""
    date_start: str = ""
    date_end: str = ""


# ── Client factory ────────────────────────────────────────────────────────────

def build_gsc_client(credentials_path: str):
    """Build a GSC Search Analytics API service object."""
    creds = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=GSC_SCOPES,
    )
    return build("webmasters", "v3", credentials=creds, cache_discovery=False)


# ── Main fetch function ───────────────────────────────────────────────────────

def fetch_gsc_data(
    service,
    site_url: str,
    date_start: str,
    date_end: str,
    compare_to_previous: bool = True,
    top_n: int = 10,
) -> GSCReportData:
    """
    Fetch Search Console metrics for the reporting period.

    Args:
        service:             Authenticated webmasters v3 service object.
        site_url:            GSC site URL (e.g. "https://www.example.com/").
        date_start:          YYYY-MM-DD.
        date_end:            YYYY-MM-DD.
        compare_to_previous: Fetch the previous period totals.
        top_n:               Number of rows for query/page tables.

    Returns:
        GSCReportData
    """
    data = GSCReportData(site_url=site_url, date_start=date_start, date_end=date_end)

    data.kpis = _fetch_kpis(service, site_url, date_start, date_end, compare_to_previous)
    data.top_queries = _fetch_queries(service, site_url, date_start, date_end, top_n)
    data.top_pages = _fetch_pages(service, site_url, date_start, date_end, top_n)

    return data


# ── Private helpers ───────────────────────────────────────────────────────────

def _query(service, site_url: str, body: dict) -> list[dict]:
    """Execute a GSC Search Analytics query. Returns rows list."""
    try:
        resp = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
        return resp.get("rows", [])
    except Exception as exc:
        logger.error("GSC API error for %s: %s", site_url, exc)
        raise


def _fetch_kpis(
    service,
    site_url: str,
    date_start: str,
    date_end: str,
    compare_to_previous: bool,
) -> GSCKPIs:
    body = {
        "startDate": date_start,
        "endDate": date_end,
        "dimensions": [],  # Aggregate totals
        "rowLimit": 1,
    }
    rows = _query(service, site_url, body)
    kpis = GSCKPIs()

    if rows:
        r = rows[0]
        kpis.clicks = int(r.get("clicks", 0))
        kpis.impressions = int(r.get("impressions", 0))
        kpis.ctr = round(r.get("ctr", 0) * 100, 2)
        kpis.position = round(r.get("position", 0), 1)

    if compare_to_previous:
        from datetime import datetime, timedelta
        fmt = "%Y-%m-%d"
        s = datetime.strptime(date_start, fmt)
        e = datetime.strptime(date_end, fmt)
        delta = e - s + timedelta(days=1)
        prev_end = s - timedelta(days=1)
        prev_start = prev_end - delta + timedelta(days=1)

        prev_body = {
            "startDate": prev_start.strftime(fmt),
            "endDate": prev_end.strftime(fmt),
            "dimensions": [],
            "rowLimit": 1,
        }
        prev_rows = _query(service, site_url, prev_body)
        if prev_rows:
            pr = prev_rows[0]
            kpis.clicks_prev = int(pr.get("clicks", 0))
            kpis.impressions_prev = int(pr.get("impressions", 0))

    return kpis


def _fetch_queries(
    service,
    site_url: str,
    date_start: str,
    date_end: str,
    top_n: int,
) -> list[QueryRow]:
    body = {
        "startDate": date_start,
        "endDate": date_end,
        "dimensions": ["query"],
        "rowLimit": top_n,  # rows come back sorted by clicks desc; Search Analytics has no orderBy field
    }
    rows = _query(service, site_url, body)
    result = []
    for r in rows:
        result.append(QueryRow(
            query=r["keys"][0],
            clicks=int(r.get("clicks", 0)),
            impressions=int(r.get("impressions", 0)),
            ctr=round(r.get("ctr", 0) * 100, 2),
            position=round(r.get("position", 0), 1),
        ))
    return result


def _fetch_pages(
    service,
    site_url: str,
    date_start: str,
    date_end: str,
    top_n: int,
) -> list[GSCPageRow]:
    body = {
        "startDate": date_start,
        "endDate": date_end,
        "dimensions": ["page"],
        "rowLimit": top_n,  # rows come back sorted by clicks desc; Search Analytics has no orderBy field
    }
    rows = _query(service, site_url, body)
    result = []
    for r in rows:
        result.append(GSCPageRow(
            page=r["keys"][0],
            clicks=int(r.get("clicks", 0)),
            impressions=int(r.get("impressions", 0)),
            ctr=round(r.get("ctr", 0) * 100, 2),
            position=round(r.get("position", 0), 1),
        ))
    return result
