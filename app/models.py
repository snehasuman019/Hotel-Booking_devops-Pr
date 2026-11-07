
from sqlalchemy import (
    Column, Integer, String, Boolean,
    Numeric, Date, DateTime, ForeignKey, func
)

from app.database import Base


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    room_number = Column(String(10), unique=True, nullable=False)
    room_type = Column(String(50), nullable=False)
    price_per_night = Column(Numeric(10, 2), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String(20), unique=True, nullable=False)

    room_id = Column(
        Integer,
        ForeignKey("rooms.id"),
        nullable=False
    )

    guest_name = Column(String(100), nullable=False)
    check_in = Column(Date, nullable=False)
    check_out = Column(Date, nullable=False)

    status = Column(String(20), default="CONFIRMED", nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
