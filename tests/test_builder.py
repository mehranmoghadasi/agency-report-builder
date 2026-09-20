"""
Tests for the report builder and config modules.
"""

from pathlib import Path

import pytest

from report_builder.builder import build_report_context, render_html
from report_builder.config import DateRange, ReportConfig
from report_builder.ga4 import ChannelRow, DeviceRow, GA4KPIs, GA4ReportData, PageRow, pct_change
from report_builder.gsc import GSCKPIs, GSCReportData

# ── Config tests ──────────────────────────────────────────────────────────────

class TestReportConfig:
    def _make_config(self, **kwargs):
        defaults = dict(
            client_name="Test Client",
            ga4_property_id="properties/123456789",
            gsc_site_url="https://example.com/",
            date_range=DateRange(start="2026-04-01", end="2026-04-30"),
            credentials_path=Path("/tmp/creds.json"),
        )
        defaults.update(kwargs)
        return ReportConfig(**defaults)

    def test_valid_config_passes(self):
        cfg = self._make_config()
        assert cfg.client_name == "Test Client"
        assert cfg.brand_colour == "#1A56DB"

    def test_invalid_property_id_raises(self):
        with pytest.raises(Exception, match="properties/"):
            self._make_config(ga4_property_id="123456789")

    def test_invalid_brand_colour_raises(self):
        with pytest.raises(Exception, match="CSS hex"):
            self._make_config(brand_colour="blue")

    def test_valid_hex_colours(self):
        cfg = self._make_config(brand_colour="#FF5733")
        assert cfg.brand_colour == "#FF5733"


class TestDateRange:
    def test_valid_range(self):
        dr = DateRange(start="2026-04-01", end="2026-04-30")
        assert dr.start == "2026-04-01"

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            DateRange(start="April 1 2026", end="2026-04-30")

    def test_start_after_end_raises(self):
        with pytest.raises(ValueError):
            DateRange(start="2026-05-01", end="2026-04-01")


# ── GA4 helper tests ──────────────────────────────────────────────────────────

class TestPctChange:
    def test_positive_change(self):
        assert pct_change(110, 100) == 10.0

    def test_negative_change(self):
        assert pct_change(90, 100) == -10.0

    def test_zero_previous_returns_none(self):
        assert pct_change(50, 0) is None

    def test_no_change(self):
        assert pct_change(100, 100) == 0.0


# ── Builder tests ─────────────────────────────────────────────────────────────

def _make_ga4(sessions=1000, users=800, conversions=40, sessions_prev=900, users_prev=750, conversions_prev=35):
    kpis = GA4KPIs(
        sessions=sessions, users=users, new_users=200,
        conversions=conversions, conversion_rate=4.0,
        avg_session_duration=120, bounce_rate=42.5,
        sessions_prev=sessions_prev, users_prev=users_prev, conversions_prev=conversions_prev
    )
    channels = [ChannelRow("Organic Search", 500, 20, 4.0), ChannelRow("Paid Search", 300, 15, 5.0)]
    pages = [PageRow("/home", "Home", 800, 90), PageRow("/services", "Services", 400, 150)]
    devices = [DeviceRow("mobile", 600, 60.0), DeviceRow("desktop", 350, 35.0), DeviceRow("tablet", 50, 5.0)]
    return GA4ReportData(kpis=kpis, channels=channels, top_pages=pages, devices=devices,
                         property_id="properties/123456789", date_start="2026-04-01", date_end="2026-04-30")


def _make_gsc():
    kpis = GSCKPIs(clicks=500, impressions=12000, ctr=4.17, position=14.3, clicks_prev=450, impressions_prev=11000)
    from report_builder.gsc import GSCPageRow, QueryRow
    queries = [QueryRow("plumber edmonton", 80, 1200, 6.7, 4.2)]
    pages = [GSCPageRow("https://example.com/services", 120, 3000, 4.0, 6.5)]
    return GSCReportData(kpis=kpis, top_queries=queries, top_pages=pages,
                         site_url="https://example.com/", date_start="2026-04-01", date_end="2026-04-30")


def _make_config():
    return ReportConfig(
        client_name="Test Client",
        agency_name="Test Agency",
        ga4_property_id="properties/123456789",
        gsc_site_url="https://example.com/",
        date_range=DateRange(start="2026-04-01", end="2026-04-30"),
        credentials_path=Path("/tmp/creds.json"),
        output_dir=Path("/tmp/test-reports"),
    )


class TestBuildReportContext:
    def test_computes_pct_changes(self):
        ctx = build_report_context(_make_config(), _make_ga4(), _make_gsc())
        # sessions: 1000 → 900 prev → +11.1%
        assert ctx.ga4_sessions_change is not None
        assert ctx.ga4_sessions_change > 0

    def test_generated_at_set(self):
        ctx = build_report_context(_make_config(), _make_ga4(), _make_gsc())
        assert ctx.generated_at != ""

    def test_report_period_set(self):
        ctx = build_report_context(_make_config(), _make_ga4(), _make_gsc())
        assert "2026-04-01" in ctx.report_period


class TestRenderHtml:
    def test_html_contains_client_name(self):
        ctx = build_report_context(_make_config(), _make_ga4(), _make_gsc())
        html = render_html(ctx)
        assert "Test Client" in html

    def test_html_contains_sessions(self):
        ctx = build_report_context(_make_config(), _make_ga4(), _make_gsc())
        html = render_html(ctx)
        assert "1,000" in html  # sessions formatted

    def test_html_contains_gsc_clicks(self):
        ctx = build_report_context(_make_config(), _make_ga4(), _make_gsc())
        html = render_html(ctx)
        assert "500" in html  # clicks

    def test_html_contains_brand_colour(self):
        config = _make_config()
        config.brand_colour = "#FF5733"
        ctx = build_report_context(config, _make_ga4(), _make_gsc())
        html = render_html(ctx)
        assert "#FF5733" in html
