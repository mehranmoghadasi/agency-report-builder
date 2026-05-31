# Architecture — agency-report-builder

## Module Breakdown

```
src/report_builder/
├── cli.py        Click command group — routes `build`, `validate`, `preview`
├── config.py     Pydantic v2 ReportConfig — loads + validates JSON config file
├── ga4.py        GA4 Data API client — fetches KPIs, channels, pages, devices
├── gsc.py        GSC Search Analytics client — fetches totals, queries, pages
├── builder.py    Assembles API data into ReportContext; drives Jinja2 rendering
├── pdf.py        WeasyPrint wrapper — converts rendered HTML string to PDF bytes
└── templates/
    └── report.html.j2  Jinja2 HTML template with CSS variables for branding
```

## Data Flow

```
CLI build command
  │
  ├─ config.py: ReportConfig.model_validate(json)
  │   └─ Pydantic validates date formats, hex colour, property ID prefix, etc.
  │
  ├─ ga4.py: fetch_ga4_data(client, property_id, start, end)
  │   ├─ _fetch_kpis()      — RunReportRequest, 2 date ranges for PoP
  │   ├─ _fetch_channels()  — dimension: sessionDefaultChannelGroup
  │   ├─ _fetch_top_pages() — dimension: pagePath + pageTitle
  │   └─ _fetch_devices()   — dimension: deviceCategory
  │
  ├─ gsc.py: fetch_gsc_data(service, site_url, start, end)
  │   ├─ _fetch_kpis()     — aggregate totals, optional prev period
  │   ├─ _fetch_queries()  — dimension: query, ordered by clicks desc
  │   └─ _fetch_pages()    — dimension: page, ordered by clicks desc
  │
  ├─ builder.py: build_report_context(config, ga4_data, gsc_data)
  │   └─ Computes pct_change() for each KPI pair; assembles ReportContext
  │
  ├─ builder.py: render_html(ctx)
  │   └─ Jinja2 Environment → report.html.j2 → rendered HTML string
  │
  └─ pdf.py: render_pdf(html_string, output_path)  [if 'pdf' in formats]
      └─ WeasyPrint HTML(string=…).write_pdf() → bytes → file
```

## Design Decisions

- **Pydantic v2 for config** — strict validation with clear error messages prevents silent misconfigurations (wrong property ID format, invalid hex colour, reversed date range).
- **Separate GA4 and GSC modules** — each API has a different client library and auth flow. Keeping them separate makes it easy to extend or replace one without touching the other.
- **Jinja2 + WeasyPrint over reportlab** — the HTML-first approach means the same template produces both the browser preview and the PDF, with no duplication of layout logic. CSS is the design system.
- **CSS variables for branding** — a single `brand_colour` config value propagates through the entire report via `:root { --brand: ... }`. Agencies can re-brand instantly without touching the template.
- **Context object pattern** — `ReportContext` is a flat dataclass holding all template variables. Jinja2 receives it as keyword arguments, keeping the template free of complex Python logic.
- **No async** — GA4 and GSC calls are sequential and fast enough for a CLI context. Async would add complexity without meaningful speed gain for 3–5 API calls.
