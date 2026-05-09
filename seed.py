from db.client import Session
from db.models import Listing


def main():
    db = Session()
    db.add(Listing(
        id="test-1",
        source="imovirtual",
        url="https://example.com/test-1",
        title="T2 Porto With Tenant",
        price=200000,
        area=80,
        location="Paranhos, Porto",
        neighborhood="Paranhos",
        city="Porto",
        property_type="apartment",
        typology="T2",
        is_rented=True,
    ))
    db.add(Listing(
        id="test-2",
        source="imovirtual",
        url="https://example.com/test-2",
        title="T3 Porto Vacant",
        price=300000,
        area=120,
        location="Campanhã, Porto",
        neighborhood="Campanhã",
        city="Porto",
        property_type="apartment",
        typology="T3",
        is_rented=False,
    ))
    db.commit()
    db.close()


if __name__ == "__main__":
    main()
