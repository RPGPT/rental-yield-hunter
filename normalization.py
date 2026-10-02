"""Canonical neighborhood (freguesia) / city names.

Listings arrive with many spellings for the same parish. ``normalize_location``
maps them onto a single canonical neighborhood, and fixes the city when the
parish belongs to another municipality.
"""

from typing import Optional

PORTO_CENTRO = "Cedofeita, Santo Ildefonso, Sé, Miragaia, São Nicolau e Vitória"
PORTO_FOZ = "Aldoar, Foz do Douro e Nevogilde"
PORTO_LORDELO = "Lordelo do Ouro e Massarelos"
GAIA_SANTA_MARINHA = "Santa Marinha e São Pedro da Afurada"
GAIA_MAFAMUDE = "Mafamude e Vilar do Paraíso"
GAIA_SAO_FELIX = "São Félix da Marinha"
MAT_CENTRO = "Matosinhos e Leça da Palmeira"
MAT_SAO_MAMEDE = "São Mamede de Infesta e Senhora da Hora"
MAT_CUSTOIAS = "Custóias, Leça do Balio e Guifões"
MAT_PERAFITA = "Perafita, Lavra e Santa Cruz do Bispo"

# alias -> canonical neighborhood
_NEIGHBORHOOD_ALIASES: dict[str, str] = {
    # Paços de Ferreira / Penafiel
    "Frazão Arreigada": "Frazão e Arreigada",
    "Arreigada": "Frazão e Arreigada",
    "Frazão": "Frazão e Arreigada",
    "Sanfins Lamoso Codessos": "Sanfins, Lamoso e Codessos",
    "Sanfins": "Sanfins, Lamoso e Codessos",
    "Lamoso": "Sanfins, Lamoso e Codessos",
    "Codessos": "Sanfins, Lamoso e Codessos",
    "Guilhufe": "Guilhufe e Urrô",
    "Urrô": "Guilhufe e Urrô",
    "Lagares": "Lagares e Figueira",
    "Luzim": "Luzim e Vila Cova",
    "Vila Cova": "Luzim e Vila Cova",
    # Porto
    "Cedofeita, Ildefonso, Sé, Miragaia, Nicolau, Vitória": PORTO_CENTRO,
    "Cedofeita, Santo Ildefonso, Sé, Miragaia, São Nico": PORTO_CENTRO,
    "Cedofeita": PORTO_CENTRO,
    "Santo Ildefonso": PORTO_CENTRO,
    "Sé": PORTO_CENTRO,
    "Sé do Porto": PORTO_CENTRO,
    "Miragaia": PORTO_CENTRO,
    "Flores": PORTO_CENTRO,
    "Batalha": PORTO_CENTRO,
    "Clérigos": PORTO_CENTRO,
    "Aliados": PORTO_CENTRO,
    "Centro do Porto, Aliados, Santa Cartarina, Bolhão": PORTO_CENTRO,
    "Paranhos - Porto": "Paranhos",
    "Polo Universitário": "Paranhos",
    "Amial": "Paranhos",
    "Bonfim - Porto": "Bonfim",
    "Campo 24 Agosto": "Bonfim",
    "São Roque da Lameira": "Campanhã",
    "Massarelos": PORTO_LORDELO,
    "Foz Velha": PORTO_FOZ,
    "Pinhais da Foz": PORTO_FOZ,
    # Porto sub-areas / landmarks
    "Bolhão": PORTO_CENTRO,
    "Metro Bolhão": PORTO_CENTRO,
    "Santa Catarina": PORTO_CENTRO,
    "Baixa Centro": PORTO_CENTRO,
    "Porto Centro": PORTO_CENTRO,
    "Trindade": PORTO_CENTRO,
    "Serpa Pinto": PORTO_CENTRO,
    "Carolina Michaëlis": PORTO_CENTRO,
    "Bom Sucesso": PORTO_CENTRO,
    "Antas": "Paranhos",
    "Carvalhido": "Paranhos",
    "Marquês": "Bonfim",
    "Metro do Marquês": "Bonfim",
    "Costa Cabral": "Bonfim",
    "Boavista": "Ramalde",
    "Pinheiro Manso": "Ramalde",
    "Prelada": "Ramalde",
    "Arca d´ Água": "Ramalde",
    "Arca d´Água": "Ramalde",
    "Corujeira - Matadouro": "Campanhã",
    "Corujeira-Matadouro": "Campanhã",
    "Campo Alegre": PORTO_LORDELO,
    "Serralves": PORTO_FOZ,
    "Fluvial": PORTO_FOZ,
    # Gaia landmarks
    "Gaia Shopping": GAIA_MAFAMUDE,
    "A2 - Enxomil": GAIA_MAFAMUDE,
    "Arrábida Shopping": GAIA_SANTA_MARINHA,
    "Jardins d´Arrábida": GAIA_SANTA_MARINHA,
    "El Corte Inglês": GAIA_SANTA_MARINHA,
    "Avenida República": GAIA_SANTA_MARINHA,
    "Valadares e Francelos - Vila Nova de Gaia": "Gulpilhares e Valadares",
    "Gueifães, Maia": "Cidade da Maia",
    # Vila Nova de Gaia
    "Santa Marinha e Afurada": GAIA_SANTA_MARINHA,
    "Coimbrões": GAIA_SANTA_MARINHA,
    "Cais de Gaia": GAIA_SANTA_MARINHA,
    "Mafamude": GAIA_MAFAMUDE,
    "Devesas": GAIA_MAFAMUDE,
    "Sto. Ovídio": GAIA_MAFAMUDE,
    "S. Félix da Marinha": GAIA_SAO_FELIX,
    "São Félix da Marinha - Vila Nova de Gaia": GAIA_SAO_FELIX,
    "São Félix da Marinha I - Granja": GAIA_SAO_FELIX,
    "São Félix da Marinha I - Brito": GAIA_SAO_FELIX,
    "São Félix da Marinha II - Reta Solverde": GAIA_SAO_FELIX,
    "São Félix da Marinha III - Granja": GAIA_SAO_FELIX,
    "Canidelo - Vila Nova de Gaia": "Canidelo",
    "Madalena - Vila Nova de Gaia": "Madalena",
    # Matosinhos
    "Leça da Palmeira": MAT_CENTRO,
    "Leça da Palmeira - Matosinhos": MAT_CENTRO,
    "Senhora da Hora": MAT_SAO_MAMEDE,
    "Metro Senhora da Hora": MAT_SAO_MAMEDE,
    "S. Mamede Infesta": MAT_SAO_MAMEDE,
    "São Mamede de Infesta": MAT_SAO_MAMEDE,
    "ISCAP": MAT_SAO_MAMEDE,
    "Custóias": MAT_CUSTOIAS,
    "Guifões": MAT_CUSTOIAS,
    "Leça do Balio": MAT_CUSTOIAS,
    "Perafita": MAT_PERAFITA,
    "Santa Cruz do Bispo": MAT_PERAFITA,
    # Maia
    "Cidade da Maia": "Cidade da Maia",
}

# (neighborhood) -> municipality it really belongs to
_NEIGHBORHOOD_CITY: dict[str, str] = {
    PORTO_CENTRO: "Porto",
    "Paranhos": "Porto",
    "Bonfim": "Porto",
    "Campanhã": "Porto",
    "Ramalde": "Porto",
    PORTO_LORDELO: "Porto",
    PORTO_FOZ: "Porto",
    GAIA_SANTA_MARINHA: "Vila Nova de Gaia",
    MAT_SAO_MAMEDE: "Matosinhos",
}

_LOOKUP = {k.casefold(): v for k, v in _NEIGHBORHOOD_ALIASES.items()}


def normalize_location(neighborhood: Optional[str], city: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Return canonical (neighborhood, city)."""
    if neighborhood:
        neighborhood = neighborhood.strip()
        neighborhood = _LOOKUP.get(neighborhood.casefold(), neighborhood)
        city = _NEIGHBORHOOD_CITY.get(neighborhood, city)
    return neighborhood, city
