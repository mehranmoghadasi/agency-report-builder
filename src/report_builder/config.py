"""
config.py — Report configuration loader and validator.

Reads a TOML or JSON client config file (or environment variables)
and returns a typed ReportConfig object via Pydantic.

Config file format (JSON):
{
  "client_name": "Acme Hardware",
  "client_logo_url": "https://acme.com/logo.png",
  "agency_name": "Bright Digital Agency",
  "brand_colour": "#1A56DB",
  "ga4_property_id": "properties/123456789",
  "gsc_site_url": "https://acme-hardware.com/",
  "date_range": {"start": "2026-04-01", "end": "2026-04-30"},
  "output_dir": "./reports",
  "formats": ["html", "pdf"],
  "credentials_path": "./credentials.json"
}
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


class DateRange(BaseModel):
    start: str  # YYYY-MM-DD
    end: str    # YYYY-MM-DD

    @field_validator("start", "end")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        from datetime import datetime
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError as err:
            raise ValueError(f"Date must be YYYY-MM-DD, got: {v!r}") from err
        return v

    @model_validator(mode="after")
    def start_before_end(self) -> DateRange:
        if self.start >= self.end:
            raise ValueError(f"start ({self.start}) must be before end ({self.end})")
        return self


class ReportConfig(BaseModel):
    client_name: str
    client_logo_url: str = ""
    agency_name: str = "Digital Marketing Agency"
    brand_colour: str = "#1A56DB"  # CSS hex colour for report accents

    ga4_property_id: str        # e.g. "properties/123456789"
    gsc_site_url: str           # e.g. "https://www.example.com/"

    date_range: DateRange
    compare_to_previous: bool = True  # include MoM or WoW comparison

    output_dir: Path = Path("./reports")
    formats: list[Literal["html", "pdf"]] = ["html"]

    credentials_path: Path = Path("./credentials.json")

    # Optional: limit rows in top-pages / top-queries tables
    top_n: int = 10

    @field_validator("brand_colour")
    @classmethod
    def valid_hex(cls, v: str) -> str:
        import re
        if not re.match(r"^#[0-9A-Fa-f]{3,6}$", v):
            raise ValueError(f"brand_colour must be a CSS hex colour (e.g. #1A56DB), got: {v!r}")
        return v

    @field_validator("ga4_property_id")
    @classmethod
    def valid_property_id(cls, v: str) -> str:
        if not v.startswith("properties/"):
            raise ValueError(
                f'ga4_property_id must start with "properties/", e.g. "properties/123456789". Got: {v!r}'
            )
        return v


def load_config(config_path: str | Path | None = None) -> ReportConfig:
    """
    Load and validate a ReportConfig from a JSON file or environment variables.

    Priority:
      1. Explicit config_path argument
      2. REPORT_CONFIG env var pointing to a JSON file
      3. Default ./report-config.json in the current directory

    Raises:
        FileNotFoundError: if no config file is found
        ValueError / ValidationError: if config is invalid
    """
    if config_path is None:
        env_path = os.environ.get("REPORT_CONFIG")
        config_path = Path(env_path) if env_path else Path("report-config.json")

    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            "Create a report-config.json or pass --config to the CLI.\n"
            "See docs/USAGE.md for a complete example."
        )

    with config_path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    config = ReportConfig.model_validate(raw)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    return config
