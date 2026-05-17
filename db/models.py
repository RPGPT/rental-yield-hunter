from sqlalchemy import TIMESTAMP, Boolean, CheckConstraint, Column, Float, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()


class Listing(Base):
    __tablename__ = "listings"

    id = Column(Text, primary_key=True)
    source = Column(Text, nullable=False)
    url = Column(Text, nullable=False)

    title = Column(Text)
    description = Column(Text)

    price = Column(Integer)
    area = Column(Integer)
    price_per_m2 = Column(Float)

    location = Column(Text)
    neighborhood = Column(Text)
    city = Column(Text)

    property_type = Column(Text)
    typology = Column(Text)
    floor = Column(Text)

    has_garage = Column(Boolean)

    is_rented = Column(Boolean, default=False)
    lifetime_rent = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False, server_default="false")
    active = Column(Boolean, default=True, server_default="true")
    inactive_since = Column(TIMESTAMP, nullable=True)

    first_seen = Column(TIMESTAMP, server_default=func.now())
    last_seen = Column(TIMESTAMP, server_default=func.now())
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now())

    price_history = relationship("ListingPriceHistory", back_populates="listing")
    raw = relationship("RawData", back_populates="listing", uselist=False)


class ListingPriceHistory(Base):
    __tablename__ = "listing_price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    listing_id = Column(Text, ForeignKey("listings.id"), nullable=False)
    price = Column(Integer)
    captured_at = Column(TIMESTAMP, server_default=func.now())

    listing = relationship("Listing", back_populates="price_history")


class RawData(Base):
    __tablename__ = "raw_data"

    listing_id = Column(Text, ForeignKey("listings.id"), primary_key=True)
    raw_json = Column(JSONB)
    captured_at = Column(TIMESTAMP, server_default=func.now())

    listing = relationship("Listing", back_populates="raw")


class RentalListing(Base):
    __tablename__ = "rental_listings"

    id = Column(Text, primary_key=True)
    source = Column(Text, nullable=False)
    url = Column(Text, nullable=False)

    title = Column(Text)
    description = Column(Text)

    price = Column(Integer)
    area = Column(Integer)
    price_per_m2 = Column(Float)
    rent_price_per_m2 = Column(Float)

    location = Column(Text)
    neighborhood = Column(Text)
    city = Column(Text)

    property_type = Column(Text)
    typology = Column(Text)
    floor = Column(Text)

    has_garage = Column(Boolean)

    is_deleted = Column(Boolean, default=False, server_default="false")
    active = Column(Boolean, default=True, server_default="true")
    inactive_since = Column(TIMESTAMP, nullable=True)

    first_seen = Column(TIMESTAMP, server_default=func.now())
    last_seen = Column(TIMESTAMP, server_default=func.now())
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now())

    price_history = relationship("RentalListingPriceHistory", back_populates="listing")
    raw = relationship("RentalRawData", back_populates="listing", uselist=False)


class RentalListingPriceHistory(Base):
    __tablename__ = "rental_listing_price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    listing_id = Column(Text, ForeignKey("rental_listings.id"), nullable=False)
    price = Column(Integer)
    captured_at = Column(TIMESTAMP, server_default=func.now())

    listing = relationship("RentalListing", back_populates="price_history")


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (CheckConstraint("role IN ('user', 'admin')", name="user_roles_role_check"),)

    # user_id matches neon_auth.users.id — no FK enforced across schemas
    user_id = Column(Text, primary_key=True, comment="neon_auth.users.id")
    role = Column(Text, nullable=False, server_default="user")


class RentalRawData(Base):
    __tablename__ = "rental_raw_data"

    listing_id = Column(Text, ForeignKey("rental_listings.id"), primary_key=True)
    raw_json = Column(JSONB)
    captured_at = Column(TIMESTAMP, server_default=func.now())

    listing = relationship("RentalListing", back_populates="raw")
