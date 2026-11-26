"""Unit & DB integration tests for the Casa Sapo scraper (real captured HTML + edge cases)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yieldhunter import config
from yieldhunter.config import SUPPORTED_CITIES
from yieldhunter.db.models import Listing, RawData
from yieldhunter.db.repository import upsert_listings
from yieldhunter.sources.base import Scraper
from yieldhunter.sources.casasapo import CasaSapoBuyScraper, CasaSapoRentalScraper
from yieldhunter.sources.casasapo.client import build_search_url, fetch_with_context
from yieldhunter.sources.casasapo.constants import CITY_SLUGS
from yieldhunter.sources.casasapo.parser import extract_cards, parse, parse_card, parse_price

FIXTURE_HTML = (Path(__file__).parent / "fixtures" / "http" / "casasapo_alfena.html").read_text(encoding="utf-8")


class TestCasaSapoConfiguration:
    def test_scraper_subclasses_and_city_coverage(self):
        assert issubclass(CasaSapoBuyScraper, Scraper)
        assert issubclass(CasaSapoRentalScraper, Scraper)
        assert set(SUPPORTED_CITIES) == set(CITY_SLUGS.keys())
        assert CasaSapoBuyScraper.MIN_PRICE == config.MIN_PRICE
        assert CasaSapoBuyScraper.MAX_PRICE == config.MAX_PRICE
        assert CasaSapoRentalScraper.MIN_PRICE == config.MIN_RENTAL_PRICE
        assert CasaSapoRentalScraper.MAX_PRICE == config.MAX_RENTAL_PRICE

    def test_build_search_url_buy_and_rent_and_pagination(self):
        assert (
            build_search_url("Porto", "buy", page=1)
            == "https://casa.sapo.pt/comprar-apartamentos/mais-baratos/porto/?sa=13"
        )
        assert (
            build_search_url("Ermesinde", "rent", page=3)
            == "https://casa.sapo.pt/arrendar-apartamentos/mais-baratos/valongo/ermesinde/?sa=13&pn=3"
        )
        with pytest.raises(ValueError, match="Unsupported Casa Sapo city"):
            build_search_url("Lisboa", "buy")


class TestCasaSapoRealHtmlParsing:
    def test_parses_all_13_real_alfena_cards(self, clean_db):
        cards = extract_cards(FIXTURE_HTML)
        assert len(cards) == 13

        listings = parse([{"html": FIXTURE_HTML}], target_city="Alfena", min_price=50_000, max_price=405_000)
        assert len(listings) == 13

        first = listings[0]
        assert first["id"] == "casasapo-e4c703fb-d90e-11f1-9a8d-060000000057"
        assert first["source"] == "casasapo"
        assert first["url"].startswith("https://casa.sapo.pt/comprar-apartamento-")
        assert first["price"] == 199_000
        assert first["area"] == 71
        assert first["city"] == "Alfena"
        assert first["neighborhood"] == "Alfena"
        assert first["typology"] == "T1"
        assert first["has_garage"] is True
        assert len(first["description"]) > 500
        assert first["_raw_json"]["fullDescription"] == first["description"]

        # Verify clean DB upsert + raw_data storage
        upsert_listings(clean_db, listings)
        assert clean_db.query(Listing).filter_by(source="casasapo", city="Alfena").count() == 13
        raw = clean_db.query(RawData).filter_by(listing_id=first["id"]).one()
        assert "fullDescription" in raw.raw_json

    def test_parse_price_formats(self):
        assert parse_price(["199.000 €"]) == 199_000
        assert parse_price("1.250 €/mês") == 1_250
        assert parse_price("Sob consulta") is None
        assert parse_price(None) is None

    def test_rented_and_lifetime_flags_detected_on_buy_but_not_rent(self):
        card = {
            "uid": "abc-123",
            "href": "/comprar-apartamento-t2-porto-abc-123.html",
            "type_text": "Apartamento T2",
            "location_text": "Paranhos, Porto, Distrito do Porto",
            "features_text": "80m² · 2º andar · Com Garagem",
            "price_text": "215.000 €",
            "description": "Imóvel arrendado com contrato vitalício por 450€/mês.",
            "ld": {},
        }
        buy = parse_card(card, target_city="Porto", min_price=50_000, max_price=405_000, listing_type="buy")
        assert buy["is_rented"] is True
        assert buy["lifetime_rent"] is True
        assert buy["floor"] == "2"
        assert buy["has_garage"] is True

        card_rent = {**card, "price_text": "950 €/mês"}
        rent = parse_card(card_rent, target_city="Porto", min_price=300, max_price=4_000, listing_type="rent")
        assert rent["is_rented"] is False
        assert rent["lifetime_rent"] is False
        assert rent["rent_price_per_m2"] == round(950 / 80, 2)


class TestCasaSapoClient:
    @patch("yieldhunter.sources.casasapo.client.curl_requests")
    @patch("yieldhunter.sources.casasapo.client.time")
    def test_retries_on_429_and_completes(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        r429 = MagicMock(status_code=429, text="<title>Site Offline</title>")
        r200 = MagicMock(status_code=200, text=FIXTURE_HTML)
        session.get.side_effect = [r429, r200]

        responses, complete = fetch_with_context("Alfena", "buy", max_price=405_000)
        assert complete is True
        assert len(responses) == 1
        assert len(responses[0]["cards"]) == 13

    @patch("yieldhunter.sources.casasapo.client.curl_requests")
    @patch("yieldhunter.sources.casasapo.client.time")
    def test_marks_incomplete_on_persistent_429(self, mock_time, mock_curl):
        session = MagicMock()
        mock_curl.Session.return_value = session
        session.get.return_value = MagicMock(status_code=429, text="<title>Site Offline</title>")

        responses, complete = fetch_with_context("Alfena", "buy", max_price=405_000)
        assert responses == []
        assert complete is False
