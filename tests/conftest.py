import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, engine, SessionLocal
from app.models import Room, Reservation
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Ensure database schema exists and seed test rooms for the test session."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Seed test rooms if not present
        existing_count = db.query(Room).count()
        if existing_count == 0:
            rooms = [
                Room(id=1, room_number="101", room_type="Single", price_per_night=1500.00, is_active=True),
                Room(id=2, room_number="102", room_type="Double", price_per_night=2500.00, is_active=True),
                Room(id=3, room_number="103", room_type="Deluxe", price_per_night=4000.00, is_active=True),
            ]
            db.add_all(rooms)
            db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def clean_reservations():
    """Clean up reservations before and after each test for test isolation."""
    db = SessionLocal()
    try:
        db.query(Reservation).delete()
        db.commit()
    finally:
        db.close()
    yield
    db = SessionLocal()
    try:
        db.query(Reservation).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture
def client():
    """FastAPI test client fixture."""
    with TestClient(app) as test_client:
        yield test_client
