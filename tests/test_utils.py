import pytest

from scraper.utils import is_rented


class TestIsRented:
    @pytest.mark.parametrize("keyword", [
        "arrendado", "inquilino", "rentabilidade",
        "arrendamento", "renda", "rented", "yield", "tenant",
    ])
    def test_detects_each_keyword(self, keyword):
        assert is_rented(f"Apartamento {keyword} em Porto") is True

    def test_negative(self):
        assert is_rented("Apartamento T2 renovado com vista mar") is False

    def test_case_insensitive(self):
        assert is_rented("Apartamento ARRENDADO") is True
        assert is_rented("Com INQUILINO estável") is True

    def test_keyword_in_description(self):
        assert is_rented("Boa rentabilidade garantida") is True

    def test_empty_string(self):
        assert is_rented("") is False

