from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class RoomResponse(BaseModel):
    id: int
    room_number: str
    room_type: str
    price_per_night: Decimal
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ReservationCreate(BaseModel):
    room_id: int
    guest_name: str = Field(min_length=2, max_length=100)
    check_in: date
    check_out: date


class ReservationResponse(BaseModel):
    id: int
    reference: str
    room_id: int
    guest_name: str
    check_in: date
    check_out: date
    status: str

    model_config = ConfigDict(from_attributes=True)