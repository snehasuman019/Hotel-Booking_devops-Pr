
from datetime import date
from uuid import uuid4

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db
from app.models import Room, Reservation
from app.schemas import (
    RoomResponse,
    ReservationCreate,
    ReservationResponse
)

app = FastAPI(
    title="Hotel Booking Platform",
    description="Hotel Room Availability and Reservation API",
    version="1.0.0"
)

# Create database tables
Base.metadata.create_all(bind=engine)


# 1. Home endpoint
@app.get("/")
def home():
    return {
        "message": "Welcome to Hotel Booking Platform",
        "status": "running"
    }


# 2. Health check
@app.get("/health")
def health_check():
    return {"status": "healthy"}


# 3. Database connection test
@app.get("/db-test")
def database_test():
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text("SELECT current_database()")
            )
            return {
                "status": "connected",
                "database": result.scalar()
            }
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed"
        )


# 4. Get all active rooms
@app.get("/rooms", response_model=list[RoomResponse])
def get_rooms(db: Session = Depends(get_db)):
    return (
        db.query(Room)
        .filter(Room.is_active.is_(True))
        .order_by(Room.id)
        .all()
    )


# 5. Get a particular room
@app.get("/rooms/{room_id}", response_model=RoomResponse)
def get_room(
    room_id: int,
    db: Session = Depends(get_db)
):
    room = db.query(Room).filter(Room.id == room_id).first()

    if not room:
        raise HTTPException(
            status_code=404,
            detail="Room not found"
        )

    return room


# 6. Create reservation with concurrency protection
@app.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=201
)
def create_reservation(
    reservation: ReservationCreate,
    db: Session = Depends(get_db)
):
    # Validate booking dates
    if reservation.check_out <= reservation.check_in:
        raise HTTPException(
            status_code=400,
            detail="Check-out must be after check-in"
        )

    try:
        # Lock the room row until the transaction completes
        room = (
            db.query(Room)
            .filter(
                Room.id == reservation.room_id,
                Room.is_active.is_(True)
            )
            .with_for_update()
            .first()
        )

        if not room:
            raise HTTPException(
                status_code=404,
                detail="Room not found or inactive"
            )

        # Check for overlapping confirmed reservations
        existing_booking = (
            db.query(Reservation)
            .filter(
                Reservation.room_id == reservation.room_id,
                Reservation.status == "CONFIRMED",
                Reservation.check_in < reservation.check_out,
                Reservation.check_out > reservation.check_in
            )
            .first()
        )

        if existing_booking:
            raise HTTPException(
                status_code=409,
                detail="Room is already booked for these dates"
            )

        # Generate unique reservation reference
        new_reservation = Reservation(
            reference="HTL-" + uuid4().hex[:10].upper(),
            room_id=reservation.room_id,
            guest_name=reservation.guest_name,
            check_in=reservation.check_in,
            check_out=reservation.check_out,
            status="CONFIRMED"
        )

        # Save reservation in PostgreSQL
        db.add(new_reservation)
        db.commit()
        db.refresh(new_reservation)

        return new_reservation

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise


# 7. Check room availability
@app.get(
    "/availability",
    response_model=list[RoomResponse]
)
def check_availability(
    check_in: date,
    check_out: date,
    db: Session = Depends(get_db)
):
    # Validate dates
    if check_out <= check_in:
        raise HTTPException(
            status_code=400,
            detail="Check-out date must be after check-in date"
        )

    # Find overlapping confirmed reservations
    overlapping_reservations = (
        db.query(Reservation.id)
        .filter(
            Reservation.room_id == Room.id,
            Reservation.status == "CONFIRMED",
            Reservation.check_in < check_out,
            Reservation.check_out > check_in
        )
        .exists()
    )

    # Return active rooms without overlapping reservations
    available_rooms = (
        db.query(Room)
        .filter(Room.is_active.is_(True))
        .filter(~overlapping_reservations)
        .order_by(Room.id)
        .all()
    )

    return available_rooms
