"""
Tests for the API-response parsing in ga4.py and gsc.py, using fakes shaped
exactly like the client libraries' responses. No network, no credentials.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from report_builder.ga4 import parse_kpi_rows
from report_builder.gsc import _fetch_kpis, _fetch_pages, _fetch_queries


def _val(v):
    return SimpleNamespace(value=str(v))


def _row(metrics, dims=()):
    return SimpleNamespace(metric_values=[_val(m) for m in metrics], dimension_values=[_val(d) for d in dims])


# ── GA4 ───────────────────────────────────────────────────────────────────────

CURRENT = [1000, 800, 200, 40, 0.04, 120.4, 0.425]
PREVIOUS = [900, 750, 180, 35, 0.039, 118.0, 0.44]


class TestGA4KpiParsing:
    def test_single_range(self):
        k = parse_kpi_rows([_row(CURRENT)], compare_to_previous=False)
        assert (k.sessions, k.users, k.new_users, k.conversions) == (1000, 800, 200, 40)
        assert k.conversion_rate == 4.0
        assert k.bounce_rate == 42.5
        assert k.sessions_prev == 0

    def test_two_ranges_matched_by_tag_not_position(self):
        # previous period listed FIRST — positional parsing would swap them
        rows = [_row(PREVIOUS, ["date_range_1"]), _row(CURRENT, ["date_range_0"])]
        k = parse_kpi_rows(rows, compare_to_previous=True)
        assert k.sessions == 1000 and k.sessions_prev == 900
        assert k.conversions == 40 and k.conversions_prev == 35

    def test_empty_response(self):
        k = parse_kpi_rows([], compare_to_previous=True)
        assert k.sessions == 0 and k.sessions_prev == 0


# ── GSC ───────────────────────────────────────────────────────────────────────

def _service(rows_by_dimension):
    """Fake webmasters service: returns rows depending on the requested dimensions."""
    svc = MagicMock()
    captured = []

    def query(siteUrl, body):
        captured.append(body)
        key = tuple(body.get("dimensions", []))
        return SimpleNamespace(execute=lambda: {"rows": rows_by_dimension.get(key, [])})

    svc.searchanalytics.return_value.query.side_effect = query
    svc.captured = captured
    return svc


class TestGSCParsing:
    def test_kpis_and_previous_period_dates(self):
        svc = _service({(): [{"clicks": 500, "impressions": 12000, "ctr": 0.0417, "position": 14.3}]})
        k = _fetch_kpis(svc, "https://example.com/", "2026-04-01", "2026-04-30", compare_to_previous=True)
        assert (k.clicks, k.impressions, k.ctr, k.position) == (500, 12000, 4.17, 14.3)
        prev = svc.captured[1]
        assert (prev["startDate"], prev["endDate"]) == ("2026-03-02", "2026-03-31")  # same length, immediately before

    def test_queries_and_pages_use_only_valid_request_fields(self):
        q_row = {"keys": ["plumber edmonton"], "clicks": 80, "impressions": 1200, "ctr": 0.067, "position": 4.2}
        p_row = {"keys": ["https://example.com/svc"], "clicks": 120, "impressions": 3000, "ctr": 0.04, "position": 6.5}
        svc = _service({("query",): [q_row], ("page",): [p_row]})
        q = _fetch_queries(svc, "https://example.com/", "2026-04-01", "2026-04-30", top_n=10)
        p = _fetch_pages(svc, "https://example.com/", "2026-04-01", "2026-04-30", top_n=10)
        assert q[0].query == "plumber edmonton" and q[0].ctr == 6.7
        assert p[0].page.endswith("/svc") and p[0].position == 6.5
        for body in svc.captured:
            assert set(body) <= {"startDate", "endDate", "dimensions", "rowLimit"}, body
