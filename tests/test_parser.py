from scraper.imovirtual.parser import (
    build_location,
    build_url,
    extract_id,
    parse,
    parse_listing,
    rooms_to_typology,
    typology_from_title,
)
from tests.conftest import make_item, make_response


class TestBuildUrl:
    def test_replaces_lang_and_ad(self):
        assert build_url("[lang]/ad/foo-ID123") == "https://www.imovirtual.com/pt/anuncio/foo-ID123"

    def test_strips_hpr_prefix(self):
        url = build_url("[lang]/hpr/ad/bar-ID456")
        assert "/hpr/" not in url
        assert url == "https://www.imovirtual.com/pt/anuncio/bar-ID456"

    def test_absolute_url_passthrough(self):
        assert build_url("https://example.com/page") == "https://example.com/page"

    def test_empty_returns_none(self):
        assert build_url("") is None


class TestBuildLocation:
    def test_full_location(self):
        loc = {
            "address": {"street": {"name": "Rua A"}},
            "reverseGeocoding": {
                "locations": [
                    {"locationLevel": "council", "name": "Porto"},
                    {"locationLevel": "parish", "name": "Paranhos"},
                ]
            },
        }
        location, neighborhood, city = build_location(loc)
        assert location == "Rua A, Paranhos, Porto"
        assert neighborhood == "Paranhos"
        assert city == "Porto"

    def test_parish_maps_to_neighborhood(self):
        loc = {
            "address": {"street": {}},
            "reverseGeocoding": {
                "locations": [
                    {"locationLevel": "council", "name": "Porto"},
                    {"locationLevel": "parish", "name": "Bonfim"},
                ]
            },
        }
        _, neighborhood, city = build_location(loc)
        assert neighborhood == "Bonfim"
        assert city == "Porto"

    def test_falls_back_to_address_when_no_revgeo(self):
        loc = {
            "address": {
                "street": {},
                "city": {"name": "Paranhos"},
                "province": {"name": "Porto"},
            },
            "reverseGeocoding": {"locations": []},
        }
        _, neighborhood, city = build_location(loc)
        assert neighborhood == "Paranhos"
        assert city == "Porto"

    def test_empty_location(self):
        location, neighborhood, city = build_location({})
        assert location == ""
        assert neighborhood is None
        assert city is None


class TestExtractId:
    def test_uses_item_id_field(self):
        assert extract_id({"id": 12345}, "https://example.com") == "12345"

    def test_falls_back_to_url_regex(self):
        assert extract_id({}, "https://www.imovirtual.com/pt/anuncio/foo-IDabc123") == "abc123"

    def test_returns_none_when_no_id(self):
        assert extract_id({}, "https://www.imovirtual.com/pt/something") is None


class TestParseListing:
    def test_full_item(self):
        result = parse_listing(make_item())

        assert result["id"] == "99999999"
        assert result["source"] == "imovirtual"
        assert result["price"] == 200000
        assert result["area"] == 85
        assert result["price_per_m2"] == 2353.0
        assert result["property_type"] == "apartment"
        assert result["typology"] == "T1"
        assert result["floor"] == "3"
        assert result["has_garage"] is True
        assert result["neighborhood"] == "Paranhos"
        assert result["city"] == "Porto"
        assert result["url"].startswith("https://www.imovirtual.com/pt/anuncio/")
        assert result["_raw_json"] == make_item()

    def test_property_type_mapping(self):
        for estate, expected in [("FLAT", "apartment"), ("HOUSE", "house"), ("TERRAIN", "land")]:
            assert parse_listing(make_item(estate=estate))["property_type"] == expected

    def test_typology_mapping(self):
        for rooms, expected in [("ONE", "T0"), ("TWO", "T1"), ("THREE", "T2"), ("FOUR", "T3"), ("FIVE", "T4")]:
            assert parse_listing(make_item(roomsNumber=rooms))["typology"] == expected

    def test_typology_unknown_returns_none(self):
        # "MORE" has no numeric equivalent; title has no T-pattern → None
        result = parse_listing(make_item(roomsNumber="MORE", title="Prédio em Cedofeita, Porto"))
        assert result["typology"] is None

    def test_rooms_to_typology_numeric_string(self):
        assert rooms_to_typology("8") == "T7"
        assert rooms_to_typology("1") == "T0"
        assert rooms_to_typology("3") == "T2"

    def test_rooms_to_typology_none(self):
        assert rooms_to_typology(None) is None
        assert rooms_to_typology("MORE") is None

    def test_typology_from_title(self):
        assert typology_from_title("Apartamento T2 com jardim") == "T2"
        assert typology_from_title("PRÉDIO PARA REABILITAÇÃO T4") == "T4"
        assert typology_from_title("Oportunidade T 4 no centro") == "T4"
        assert typology_from_title("Vendo T1 e T2 com jardim") == "T1"

    def test_typology_from_title_no_match(self):
        assert typology_from_title("Prédio Venda em Campanhã") is None

    def test_typology_fallback_used_when_rooms_number_missing(self):
        result = parse_listing(make_item(roomsNumber=None, title="Apartamento T3 Porto"))
        assert result["typology"] == "T3"

    def test_typology_fallback_used_with_space(self):
        result = parse_listing(make_item(roomsNumber=None, title="Moradia T 2 Matosinhos"))
        assert result["typology"] == "T2"

    def test_typology_null_when_no_rooms_and_no_title_match(self):
        result = parse_listing(make_item(roomsNumber=None, title="Prédio histórico no Porto"))
        assert result["typology"] is None

    def test_no_price_returns_none(self):
        assert parse_listing(make_item(totalPrice=None)) is None

    def test_price_above_max_returns_none(self):
        assert parse_listing(make_item(totalPrice={"value": 500000})) is None

    def test_price_below_min_returns_none(self):
        assert parse_listing(make_item(totalPrice={"value": 49999})) is None

    def test_price_at_min_is_included(self):
        assert parse_listing(make_item(totalPrice={"value": 50000})) is not None

    def test_no_href_returns_none(self):
        assert parse_listing(make_item(href="")) is None

    def test_is_rented_with_keywords(self):
        result = parse_listing(make_item(title="Apartamento arrendado", shortDescription="Com inquilino estável"))
        assert result["is_rented"] is True

    def test_is_rented_without_keywords(self):
        result = parse_listing(make_item(title="Apartamento T2", shortDescription="Vista mar"))
        assert result["is_rented"] is False

    def test_has_garage_from_tags(self):
        assert parse_listing(make_item(tags=["PARKING_SPOT"]))["has_garage"] is True
        assert parse_listing(make_item(tags=[]))["has_garage"] is False
        assert parse_listing(make_item(tags=None))["has_garage"] is False

    def test_has_garage_from_features(self):
        assert parse_listing(make_item(tags=[], features=["Garage"]))["has_garage"] is True
        assert parse_listing(make_item(tags=[], features=["Garden"]))["has_garage"] is False

    def test_filters_out_non_target_city(self):
        maia_item = make_item(
            location={
                "address": {"street": {}, "city": {"name": "Moreira"}, "province": {"name": "Maia"}},
                "reverseGeocoding": {"locations": [{"locationLevel": "council", "name": "Maia"}]},
            }
        )
        # When target_city is Porto, Maia listings are filtered out
        assert parse_listing(maia_item, target_city="Porto") is None

    def test_no_target_city_filter_accepts_any_city(self):
        maia_item = make_item(
            location={
                "address": {"street": {}, "city": {"name": "Moreira"}, "province": {"name": "Maia"}},
                "reverseGeocoding": {"locations": [{"locationLevel": "council", "name": "Maia"}]},
            }
        )
        # Without a target_city constraint all cities are accepted
        assert parse_listing(maia_item, target_city=None) is not None

    def test_missing_optional_fields(self):
        result = parse_listing(
            make_item(
                areaInSquareMeters=None,
                pricePerSquareMeter=None,
                floorNumber=None,
                roomsNumber=None,
                title="Prédio histórico no Porto",  # no T-pattern → typology stays None
            )
        )
        assert result["area"] is None
        assert result["price_per_m2"] is None
        assert result["floor"] is None
        assert result["typology"] is None

    def test_lifetime_rent_defaults_false(self):
        assert parse_listing(make_item())["lifetime_rent"] is False


class TestParse:
    def test_deduplication_by_id(self):
        item = make_item()
        assert len(parse([make_response(item, item)])) == 1

    def test_dedup_across_responses(self):
        item = make_item()
        assert len(parse([make_response(item), make_response(item)])) == 1

    def test_multiple_distinct_items(self):
        a = make_item(id=1, href="[lang]/ad/a-ID1")
        b = make_item(id=2, href="[lang]/ad/b-ID2")
        listings = parse([make_response(a, b)])
        assert len(listings) == 2
        assert {listing["id"] for listing in listings} == {"1", "2"}

    def test_filters_out_invalid_items(self):
        valid = make_item()
        no_price = make_item(id=2, totalPrice=None)
        assert len(parse([make_response(valid, no_price)])) == 1

    def test_parse_with_target_city_filters_others(self):
        porto_item = make_item(id=1, href="[lang]/ad/a-ID1")
        maia_item = make_item(
            id=2,
            href="[lang]/ad/b-ID2",
            location={
                "address": {"street": {}, "city": {"name": "Moreira"}, "province": {"name": "Maia"}},
                "reverseGeocoding": {"locations": [{"locationLevel": "council", "name": "Maia"}]},
            },
        )
        listings = parse([make_response(porto_item, maia_item)], target_city="Porto")
        assert len(listings) == 1
        assert listings[0]["city"] == "Porto"

    def test_parse_without_target_city_accepts_all(self):
        porto_item = make_item(id=1, href="[lang]/ad/a-ID1")
        maia_item = make_item(
            id=2,
            href="[lang]/ad/b-ID2",
            location={
                "address": {"street": {}, "city": {"name": "Moreira"}, "province": {"name": "Maia"}},
                "reverseGeocoding": {"locations": [{"locationLevel": "council", "name": "Maia"}]},
            },
        )
        listings = parse([make_response(porto_item, maia_item)], target_city=None)
        assert len(listings) == 2
        assert {listing["city"] for listing in listings} == {"Porto", "Maia"}


class TestCustomPriceRange:
    def test_parse_listing_respects_custom_min(self):
        assert parse_listing(make_item(totalPrice={"value": 299}), min_price=300, max_price=4000) is None
        assert parse_listing(make_item(totalPrice={"value": 300}), min_price=300, max_price=4000) is not None

    def test_parse_listing_respects_custom_max(self):
        assert parse_listing(make_item(totalPrice={"value": 4001}), min_price=300, max_price=4000) is None
        assert parse_listing(make_item(totalPrice={"value": 4000}), min_price=300, max_price=4000) is not None

    def test_parse_filters_with_custom_range(self):
        in_range = make_item(id=1, href="[lang]/ad/a-ID1", totalPrice={"value": 1500})
        too_cheap = make_item(id=2, href="[lang]/ad/b-ID2", totalPrice={"value": 100})
        too_expensive = make_item(id=3, href="[lang]/ad/c-ID3", totalPrice={"value": 9999})
        result = parse([make_response(in_range, too_cheap, too_expensive)], min_price=300, max_price=4000)
        assert len(result) == 1
        assert result[0]["id"] == "1"

    def test_parse_listing_defaults_to_config_prices(self):
        from config import MAX_PRICE, MIN_PRICE

        assert parse_listing(make_item(totalPrice={"value": MIN_PRICE})) is not None
        assert parse_listing(make_item(totalPrice={"value": MIN_PRICE - 1})) is None
        assert parse_listing(make_item(totalPrice={"value": MAX_PRICE + 1})) is None


class TestRentPricePerM2:
    def test_calculated_from_price_and_area(self):
        result = parse_listing(
            make_item(totalPrice={"value": 1200}, areaInSquareMeters=80), min_price=300, max_price=4000
        )
        assert result["rent_price_per_m2"] == 15.0

    def test_falls_back_to_api_ppm2_when_no_area(self):
        result = parse_listing(
            make_item(
                totalPrice={"value": 1200},
                areaInSquareMeters=None,
                pricePerSquareMeter={"value": 14},
            ),
            min_price=300,
            max_price=4000,
        )
        assert result["rent_price_per_m2"] == 14.0

    def test_none_when_no_area_and_no_api_ppm2(self):
        result = parse_listing(
            make_item(
                totalPrice={"value": 1200},
                areaInSquareMeters=None,
                pricePerSquareMeter=None,
            ),
            min_price=300,
            max_price=4000,
        )
        assert result["rent_price_per_m2"] is None

    def test_precise_calculation(self):
        result = parse_listing(
            make_item(totalPrice={"value": 520}, areaInSquareMeters=30), min_price=300, max_price=4000
        )
        assert result["rent_price_per_m2"] == round(520 / 30, 2)
