MAX_PRICE = 450_000
REQUEST_DELAY = 2
SOURCE = "imovirtual"

TENANT_KEYWORDS = [
    "arrendado", "inquilino", "rentabilidade",
    "arrendamento", "renda", "rented", "yield", "tenant",
]

ESTATE_MAP = {
    "FLAT": "apartment",
    "HOUSE": "house",
    "TERRAIN": "land",
    "GARAGE": "garage",
    "WAREHOUSE": "warehouse",
}

ROOMS_MAP = {
    "ONE": "T1",
    "TWO": "T2",
    "THREE": "T3",
    "FOUR": "T4",
    "FIVE_OR_MORE": "T5+",
}

CONDITION_MAP = {
    "IN_BUILDING": "under_construction",
    "READY_TO_USE": "new",
    "TO_RENOVATION": "to_renovate",
    "TO_COMPLETION": "to_finish",
}
