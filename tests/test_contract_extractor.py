"""Tests for the rental contract detail extractor."""

from scraper.contract_extractor import (
    _extract_expiry,
    _extract_rent,
    _find_euro_amounts,
    _normalize_amount,
    _parse_unit_count,
    extract_rent_and_expiry,
)

# ── Amount normalisation ─────────────────────────────────────────────────────


class TestNormalizeAmount:
    def test_simple_integer(self):
        assert _normalize_amount("800") == 800.0

    def test_decimal_dot(self):
        assert _normalize_amount("870.00") == 870.0

    def test_european_thousands(self):
        assert _normalize_amount("1.200,00") == 1200.0

    def test_english_thousands(self):
        assert _normalize_amount("1,200") == 1200.0

    def test_english_thousands_with_cents(self):
        assert _normalize_amount("1,200.50") == 1200.5

    def test_european_thousands_no_cents(self):
        assert _normalize_amount("1.200") == 1200.0

    def test_comma_decimal(self):
        assert _normalize_amount("800,50") == 800.5

    def test_invalid(self):
        assert _normalize_amount("abc") is None

    def test_whitespace(self):
        assert _normalize_amount("  800  ") == 800.0


# ── Euro amount finder ───────────────────────────────────────────────────────


class TestFindEuroAmounts:
    def test_prefix_euro(self):
        results = _find_euro_amounts("Price is €870.00 per month")
        assert len(results) >= 1
        assert results[0][0] == 870.0

    def test_suffix_euro(self):
        results = _find_euro_amounts("Renda de 800€/mês")
        assert len(results) >= 1
        assert results[0][0] == 800.0

    def test_euro_word(self):
        results = _find_euro_amounts("950 euros mensais")
        assert len(results) >= 1
        assert results[0][0] == 950.0

    def test_multiple_amounts(self):
        results = _find_euro_amounts("Preço: 150.000€, renda: 800€/mês")
        assert len(results) == 2

    def test_no_amounts(self):
        assert _find_euro_amounts("No money here") == []

    def test_spaced_euro(self):
        results = _find_euro_amounts("renda de 800 €")
        assert len(results) >= 1
        assert results[0][0] == 800.0


# ── Unit count / multiplier ──────────────────────────────────────────────────


class TestParseUnitCount:
    def test_duas_casas_cada_uma(self):
        assert _parse_unit_count("duas casas t2 arrendadas por 750€ cada uma") == 2

    def test_no_multiplier(self):
        assert _parse_unit_count("apartamento arrendado por 800€") == 1

    def test_three_units_each(self):
        assert _parse_unit_count("3 apartamentos arrendados por 500€ each") == 3

    def test_count_without_cada(self):
        # "duas casas" without "cada uma" should NOT multiply
        assert _parse_unit_count("duas casas arrendadas por 1500€") == 1


# ── Rent extraction ──────────────────────────────────────────────────────────


class TestExtractRent:
    def test_portuguese_renda_atual(self):
        text = "renda atual: 800€/mês"
        amount, raw, conf = _extract_rent(text)
        assert amount == 800.0
        assert conf > 0

    def test_english_current_rent(self):
        text = "Current rent: €1,200 per month"
        amount, raw, conf = _extract_rent(text)
        assert amount == 1200.0
        assert conf > 0

    def test_arrendado_por(self):
        text = "Apartamento arrendado por 950 € mensais"
        amount, raw, conf = _extract_rent(text)
        assert amount == 950.0

    def test_rented_for(self):
        text = "Property rented for €870.00 per month"
        amount, raw, conf = _extract_rent(text)
        assert amount == 870.0

    def test_multiple_amounts_picks_rent(self):
        text = "Preço de venda: 150.000€. Renda atual: 800€/mês."
        amount, raw, conf = _extract_rent(text)
        assert amount == 800.0

    def test_multiplier_duas_casas(self):
        text = "duas casas t2 arrendadas por 750€ cada uma"
        amount, raw, conf = _extract_rent(text)
        assert amount == 1500.0

    def test_no_rent(self):
        text = "Beautiful apartment with sea view"
        amount, raw, conf = _extract_rent(text)
        assert amount is None
        assert conf == 0.0

    def test_out_of_range_ignored(self):
        text = "Preço: 300000€"
        amount, raw, conf = _extract_rent(text)
        assert amount is None


# ── Expiry extraction ────────────────────────────────────────────────────────


class TestExtractExpiry:
    def test_portuguese_month_year(self):
        text = "contrato de arrendamento válido até fevereiro de 2027"
        iso, raw, conf = _extract_expiry(text)
        assert iso == "2027-02-28"
        assert conf > 0

    def test_english_month_year(self):
        text = "rented until September 2026"
        iso, raw, conf = _extract_expiry(text)
        assert iso == "2026-09-30"

    def test_exact_date(self):
        text = "Lease valid until 31 December 2026"
        iso, raw, conf = _extract_expiry(text)
        assert iso == "2026-12-31"

    def test_portuguese_ate(self):
        text = "arrendamento até março de 2028"
        iso, raw, conf = _extract_expiry(text)
        assert iso == "2028-03-31"

    def test_no_expiry(self):
        text = "Apartamento T2 renovado"
        iso, raw, conf = _extract_expiry(text)
        assert iso is None
        assert conf == 0.0

    def test_past_date_ignored(self):
        text = "contrato até janeiro de 2020"
        iso, raw, conf = _extract_expiry(text)
        assert iso is None


# ── Full extraction ──────────────────────────────────────────────────────────


class TestExtractRentAndExpiry:
    def test_portuguese_full(self):
        text = (
            "Imóvel atualmente arrendado, ideal para investidores que procuram "
            "rendimento imediato, com uma renda atual: 800€/mês e contrato de "
            "arrendamento válido até fevereiro de 2027."
        )
        result = extract_rent_and_expiry(text)
        assert result["current_rent_amount"] == 800.0
        assert result["currency"] == "EUR"
        assert result["contract_expiry_date"] == "2027-02-28"
        assert result["confidence"] > 0

    def test_english_full(self):
        text = "Property currently rented until September 2026 for €870.00 per month."
        result = extract_rent_and_expiry(text)
        assert result["current_rent_amount"] == 870.0
        assert result["contract_expiry_date"] == "2026-09-30"

    def test_portuguese_short(self):
        text = "Apartamento arrendado por 950 € mensais com contrato até março de 2028."
        result = extract_rent_and_expiry(text)
        assert result["current_rent_amount"] == 950.0
        assert result["contract_expiry_date"] == "2028-03-31"

    def test_english_exact_date(self):
        text = "Lease valid until 31 December 2026. Current rent: €1,200 per month."
        result = extract_rent_and_expiry(text)
        assert result["current_rent_amount"] == 1200.0
        assert result["contract_expiry_date"] == "2026-12-31"

    def test_no_extractable_data(self):
        text = "Apartment with great views. Fully renovated."
        result = extract_rent_and_expiry(text)
        assert result["current_rent_amount"] is None
        assert result["contract_expiry_date"] is None
        assert result["confidence"] == 0.0

    def test_only_rent_no_expiry(self):
        text = "Arrendado por 700€ mensais."
        result = extract_rent_and_expiry(text)
        assert result["current_rent_amount"] == 700.0
        assert result["contract_expiry_date"] is None
        assert result["confidence"] > 0

    def test_only_expiry_no_rent(self):
        text = "Contrato válido até dezembro de 2027."
        result = extract_rent_and_expiry(text)
        assert result["current_rent_amount"] is None
        assert result["contract_expiry_date"] == "2027-12-31"
        assert result["confidence"] > 0

    def test_ambiguous_no_anchors(self):
        text = "O valor mencionado é 500€ mas não se sabe se é renda."
        result = extract_rent_and_expiry(text)
        # Without anchor proximity, may or may not extract — but shouldn't crash
        assert result["currency"] == "EUR"

    def test_duas_casas_multiplier(self):
        text = "duas casas t2 arrendadas por 750€ cada uma"
        result = extract_rent_and_expiry(text)
        assert result["current_rent_amount"] == 1500.0
