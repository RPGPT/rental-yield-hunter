import pytest

from yieldhunter.analysis.rented import is_rented


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

    @pytest.mark.parametrize(
        "text",
        [
            "Localização central, ideal para arrendamento de curta ou longa duração.",
            "Excelente para arrendamento ou habitação própria.",
            "Imóvel para habitação própria ou arrendamento.",
            "Forte potencial de arrendamento no centro do Porto.",
            "Soluções em Compra/ Venda/ Arrendamento de imóveis/ Trespasse.",
            "Serviços de mediação e arrendamento de imóveis.",
            "Imóvel não está arrendado, pronto a habitar.",
            "Apartamento sem inquilino.",
        ],
    )
    def test_false_positive_phrases_ignored(self, text):
        assert is_rented(text) is False

    def test_true_rented_still_detected_alongside_boilerplate(self):
        text = "Apartamento atualmente arrendado por 850€/mês. Agência especializada em Compra/ Venda/ Arrendamento."
        assert is_rented(text) is True
