from normalization import normalize_location


def test_alias_maps_to_canonical():
    assert normalize_location("S. Mamede Infesta", "Matosinhos") == (
        "São Mamede de Infesta e Senhora da Hora",
        "Matosinhos",
    )


def test_city_corrected_when_parish_belongs_elsewhere():
    assert normalize_location("Santa Marinha e São Pedro da Afurada", "Porto")[1] == "Vila Nova de Gaia"


def test_unknown_and_none_untouched():
    assert normalize_location("Lugar X", "Vila Nova de Gaia") == ("Lugar X", "Vila Nova de Gaia")
    assert normalize_location(None, None) == (None, None)


def test_new_city_union_parishes():
    assert normalize_location("Frazão Arreigada", "Paços de Ferreira") == ("Frazão e Arreigada", "Paços de Ferreira")
    assert normalize_location("Guilhufe e Urrô", "Penafiel") == ("Guilhufe e Urrô", "Penafiel")


def test_generic_or_missing_neighborhood_becomes_city():
    assert normalize_location("Rio Tinto", "Porto") == ("Porto", "Porto")
    assert normalize_location("C4 - Ramos", "Vila Nova de Gaia") == ("Vila Nova de Gaia", "Vila Nova de Gaia")
    assert normalize_location(None, "Porto") == ("Porto", "Porto")
