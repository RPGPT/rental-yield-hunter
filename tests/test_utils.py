import pytest

from scraper.utils import is_rented


class TestIsRented:
    @pytest.mark.parametrize(
        "keyword",
        [
            "arrendado",
            "inquilino",
            "arrendamento",
            "renda",
            "rented",
            "tenant",
            "alugado",
            "contrato de aluguer",
        ],
    )
    def test_detects_each_keyword(self, keyword):
        assert is_rented(f"Apartamento {keyword} em Porto") is True

    def test_negative(self):
        assert is_rented("Apartamento T2 renovado com vista mar") is False

    def test_case_insensitive(self):
        assert is_rented("Apartamento ARRENDADO") is True
        assert is_rented("Com INQUILINO estável") is True

    def test_rentabilidade_no_longer_triggers(self):
        assert is_rented("Boa rentabilidade garantida") is False

    def test_yield_no_longer_triggers(self):
        assert is_rented("High yield investment") is False

    def test_empty_string(self):
        assert is_rented("") is False
