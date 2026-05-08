import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from db.models import Base


@pytest.fixture(scope="session")
def pg():
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def test_engine(pg):
    url = pg.get_connection_url()
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db(test_engine):
    session = sessionmaker(bind=test_engine)()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def clean_db(db):
    yield db
    db.execute(text("DELETE FROM user_favorites"))
    db.execute(text("DELETE FROM users"))
    db.execute(text("DELETE FROM raw_data"))
    db.execute(text("DELETE FROM listing_price_history"))
    db.execute(text("DELETE FROM listings"))
    db.commit()


def make_item(**overrides):
    item = {
        "id": 99999999,
        "title": "Apartamento T2 em Paranhos",
        "estate": "FLAT",
        "roomsNumber": "TWO",
        "floorNumber": 3,
        "totalPrice": {"value": 200000, "currency": "EUR"},
        "pricePerSquareMeter": {"value": 2353},
        "areaInSquareMeters": 85,
        "tags": ["PARKING_SPOT"],
        "investmentState": None,
        "location": {
            "address": {
                "street": {"name": "Rua de Costa Cabral"},
                "city": {"name": "Paranhos"},
                "province": {"name": "Porto"},
            }
        },
        "href": "[lang]/ad/apartamento-t2-paranhos-ID99999999",
        "shortDescription": "Belo apartamento T2 renovado.",
    }
    item.update(overrides)
    return item


def make_response(*items):
    return {
        "items": list(items),
        "pagination": {"totalItems": len(items), "totalPages": 1, "currentPage": 1},
    }
