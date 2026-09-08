"""Tests for scraper parsing helpers (no network access)."""
from __future__ import annotations

import pandas as pd

from app.scrapers.fbref import FBrefScraper
from app.scrapers.transfermarkt import TransfermarktScraper


def test_transfermarkt_value_parsing():
    assert TransfermarktScraper._parse_value_text("€90.00m") == 90_000_000
    assert TransfermarktScraper._parse_value_text("€900k") == 900_000
    assert TransfermarktScraper._parse_value_text("€1.2m") == 1_200_000
    assert TransfermarktScraper._parse_value_text("€50m") == 50_000_000
    assert TransfermarktScraper._parse_value_text("€1.5bn") == 1_500_000_000
    assert TransfermarktScraper._parse_value_text("") is None
    assert TransfermarktScraper._parse_value_text("no value") is None


def test_fbref_split_name():
    assert FBrefScraper._split_name("Martin Ødegaard") == ("Martin", "Ødegaard")
    assert FBrefScraper._split_name("Pedri") == ("Pedri", "")
    assert FBrefScraper._split_name("Virgil van Dijk") == ("Virgil", "van Dijk")


def test_fbref_slug_and_experience():
    assert FBrefScraper._slug("Martin Ødegaard") == "martin-odegaard"
    assert FBrefScraper._estimate_experience(26) == 8
    assert FBrefScraper._estimate_experience(0) == 0


def test_fbref_absorb_table_prefers_per90():
    scraper = FBrefScraper(cache=None)  # type: ignore[arg-type]
    # Columns: "Gls" (total) and "Gls.1" (per-90), plus "Ast.1".
    table = pd.DataFrame(
        [
            {"Gls": 10.0, "Gls.1": 0.30, "Ast.1": 0.40},
            {"Gls": 12.0, "Gls.1": 0.35, "Ast.1": 0.45},
        ]
    )
    features: dict[str, float] = {}
    scraper._absorb_table(features, table)
    # Latest row's per-90 values win.
    assert features["goals_p90"] == 0.35
    assert features["assists_p90"] == 0.45


def test_fbref_absorb_table_falls_back_to_total():
    scraper = FBrefScraper(cache=None)  # type: ignore[arg-type]
    table = pd.DataFrame([{"Gls": 11.0}])
    features: dict[str, float] = {}
    scraper._absorb_table(features, table)
    assert features["goals_p90"] == 11.0
