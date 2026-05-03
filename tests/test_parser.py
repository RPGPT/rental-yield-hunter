from scraper.imovirtual.parser import parse_listing, parse, build_url, extract_id
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


class TestExtractId:
    def test_uses_item_id_field(self):
        assert extract_id({"id": 12345}, "https://example.com") == "12345"

    def test_falls_back_to_url_regex(self):
        assert extract_id({}, "https://www.imovirtual.com/pt/anuncio/foo-IDabc123") == "abc123"

    def test_returns_none_when_no_id(self):
        assert extract_id({}, "https://www.imovirtual.com/pt/something") is None


class TestParseListing:
    def test_full_item(self):
        item = make_item()
        result = parse_listing(item)

        assert result["id"] == "99999999"
        assert result["source"] == "imovirtual"
        assert result["price"] == 200000
        assert result["area"] == 85
        assert result["price_per_m2"] == 2353.0
        assert result["property_type"] == "apartment"
        assert result["typology"] == "T2"
        assert result["floor"] == "3"
        assert result["has_garage"] is True
        assert result["city"] == "Paranhos"
        assert result["url"].startswith("https://www.imovirtual.com/pt/anuncio/")
        assert result["_raw_json"] == item

    def test_property_type_mapping(self):
        for estate, expected in [("FLAT", "apartment"), ("HOUSE", "house"), ("TERRAIN", "land")]:
            result = parse_listing(make_item(estate=estate))
            assert result["property_type"] == expected

    def test_typology_mapping(self):
        for rooms, expected in [("ONE", "T1"), ("THREE", "T3"), ("FIVE_OR_MORE", "T5+")]:
            result = parse_listing(make_item(roomsNumber=rooms))
            assert result["typology"] == expected

    def test_condition_mapping(self):
        result = parse_listing(make_item(investmentState="READY_TO_USE"))
        assert result["condition"] == "new"

        result = parse_listing(make_item(investmentState="TO_RENOVATION"))
        assert result["condition"] == "to_renovate"

    def test_no_price_returns_none(self):
        assert parse_listing(make_item(totalPrice=None)) is None

    def test_price_above_max_returns_none(self):
        assert parse_listing(make_item(totalPrice={"value": 500000})) is None

    def test_no_href_returns_none(self):
        assert parse_listing(make_item(href="")) is None

    def test_is_rented_with_keywords(self):
        result = parse_listing(make_item(
            title="Apartamento arrendado",
            shortDescription="Com inquilino estável",
        ))
        assert result["is_rented"] is True

    def test_is_rented_without_keywords(self):
        result = parse_listing(make_item(
            title="Apartamento T2",
            shortDescription="Vista mar",
        ))
        assert result["is_rented"] is False

    def test_has_garage_from_tags(self):
        assert parse_listing(make_item(tags=["PARKING_SPOT"]))["has_garage"] is True
        assert parse_listing(make_item(tags=[]))["has_garage"] is False
        assert parse_listing(make_item(tags=None))["has_garage"] is False

    def test_has_garage_from_features(self):
        assert parse_listing(make_item(tags=[], features=["Garage"]))["has_garage"] is True
        assert parse_listing(make_item(tags=[], features=["Garden"]))["has_garage"] is False

    def test_missing_optional_fields(self):
        result = parse_listing(make_item(
            areaInSquareMeters=None,
            pricePerSquareMeter=None,
            floorNumber=None,
            roomsNumber=None,
            investmentState=None,
        ))
        assert result["area"] is None
        assert result["price_per_m2"] is None
        assert result["floor"] is None
        assert result["typology"] is None
        assert result["condition"] is None


    def test_lifetime_rent_defaults_false(self):
        result = parse_listing(make_item())
        assert result["lifetime_rent"] is False


class TestParse:
    def test_deduplication_by_id(self):
        item = make_item()
        listings = parse([make_response(item, item)])
        assert len(listings) == 1

    def test_dedup_across_responses(self):
        item = make_item()
        listings = parse([make_response(item), make_response(item)])
        assert len(listings) == 1

    def test_multiple_distinct_items(self):
        a = make_item(id=1, href="[lang]/ad/a-ID1")
        b = make_item(id=2, href="[lang]/ad/b-ID2")
        listings = parse([make_response(a, b)])
        assert len(listings) == 2
        assert {l["id"] for l in listings} == {"1", "2"}

    def test_filters_out_invalid_items(self):
        valid = make_item()
        no_price = make_item(id=2, totalPrice=None)
        listings = parse([make_response(valid, no_price)])
        assert len(listings) == 1

