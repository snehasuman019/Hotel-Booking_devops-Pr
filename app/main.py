import logging
import time
from datetime import date
from uuid import uuid4

from fastapi import FastAPI, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db
from app.models import Room, Reservation
from app.schemas import (
    RoomResponse,
    ReservationCreate,
    ReservationResponse
)

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("hotel_booking")

app = FastAPI(
    title="Hotel Booking Platform",
    description="Hotel Room Availability and Reservation API",
    version="1.0.0"
)

# HTTP Request/Response logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start_time) * 1000, 2)
    logger.info(
        f"HTTP {request.method} {request.url.path} - Status: {response.status_code} ({duration_ms}ms)"
    )
    return response

# Create database tables
Base.metadata.create_all(bind=engine)


# 1. Home endpoint
@app.get("/")
def home():
    return {
        "message": "Welcome to Hotel Booking Platform",
        "status": "running"
    }


# 2. Health check (Liveness probe)
@app.get("/health")
def health_check():
    return {"status": "healthy"}


# 3. Readiness check (Verifies application & database readiness)
@app.get("/ready")
def readiness_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "database": "connected"
        }
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail="Database readiness check failed"
        )


# 4. Database connection test
@app.get("/db-test")
def database_test():
    try:
        with engine.connect() as connection:
            try:
                db_name = connection.execute(text("SELECT current_database()")).scalar()
            except Exception:
                db_name = "connected"
            return {
                "status": "connected",
                "database": db_name
            }
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        raise HTTPException(
            status_code=503,
            detail="Database connection failed"
        )


# 5. Get all active rooms
@app.get("/rooms", response_model=list[RoomResponse])
def get_rooms(db: Session = Depends(get_db)):
    return (
        db.query(Room)
        .filter(Room.is_active.is_(True))
        .order_by(Room.id)
        .all()
    )


# 6. Get a particular room
@app.get("/rooms/{room_id}", response_model=RoomResponse)
def get_room(
    room_id: int,
    db: Session = Depends(get_db)
):
    room = db.query(Room).filter(Room.id == room_id).first()

    if not room:
        logger.warning(f"Room query failed: Room {room_id} not found")
        raise HTTPException(
            status_code=404,
            detail="Room not found"
        )

    return room


# 7. Create reservation with concurrency protection
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
        logger.warning(
            f"Reservation rejection: check_out ({reservation.check_out}) <= check_in ({reservation.check_in})"
        )
        raise HTTPException(
            status_code=400,
            detail="Check-out must be after check-in"
        )

    try:
        # Lock the room row until the transaction completes (row-level locking)
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
            logger.warning(f"Reservation failed: Room {reservation.room_id} not found or inactive")
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
            logger.warning(
                f"Reservation conflict: Room {reservation.room_id} already booked for window "
                f"[{reservation.check_in} -> {reservation.check_out}]. Conflicting ID: {existing_booking.id}"
            )
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

        logger.info(
            f"Reservation confirmed: Ref={new_reservation.reference}, Room={new_reservation.room_id}, "
            f"Dates=[{new_reservation.check_in} -> {new_reservation.check_out}]"
        )

        return new_reservation

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error during reservation creation: {e}", exc_info=True)
        raise


# 8. Check room availability
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
        logger.warning(f"Availability check invalid dates: {check_in} -> {check_out}")
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
