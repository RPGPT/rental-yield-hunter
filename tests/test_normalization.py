from normalization import normalize_location


def test_alias_maps_to_canonical():
    assert normalize_location("S. Mamede Infesta", "Matosinhos") == (
        "São Mamede de Infesta e Senhora da Hora",
        "Matosinhos",
    )


def test_city_corrected_when_parish_belongs_elsewhere():
    assert normalize_location("Santa Marinha e São Pedro da Afurada", "Porto")[1] == "Vila Nova de Gaia"


def test_unknown_and_none_untouched():
    assert normalize_location("Loureiro", "Vila Nova de Gaia") == ("Loureiro", "Vila Nova de Gaia")
    assert normalize_location(None, "Porto") == (None, "Porto")
