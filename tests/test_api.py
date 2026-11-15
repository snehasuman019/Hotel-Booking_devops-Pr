import pytest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier


def test_home(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "Hotel Booking" in data["message"]


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_ready(client):
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"


def test_db_test(client):
    response = client.get("/db-test")
    assert response.status_code == 200
    assert response.json()["status"] == "connected"


def test_get_rooms(client):
    response = client.get("/rooms")
    assert response.status_code == 200
    rooms = response.json()
    assert isinstance(rooms, list)
    assert len(rooms) >= 3
    room_numbers = [r["room_number"] for r in rooms]
    assert "101" in room_numbers


def test_get_single_room(client):
    response = client.get("/rooms/1")
    assert response.status_code == 200
    room = response.json()
    assert room["id"] == 1
    assert room["room_number"] == "101"
    assert room["is_active"] is True


def test_invalid_room(client):
    response = client.get("/rooms/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Room not found"


def test_create_valid_reservation(client):
    payload = {
        "room_id": 1,
        "guest_name": "Alice Walker",
        "check_in": "2026-12-01",
        "check_out": "2026-12-05"
    }
    response = client.post("/reservations", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["room_id"] == 1
    assert data["guest_name"] == "Alice Walker"
    assert data["check_in"] == "2026-12-01"
    assert data["check_out"] == "2026-12-05"
    assert data["status"] == "CONFIRMED"
    assert data["reference"].startswith("HTL-")


def test_overlapping_reservation_returns_409(client):
    # Initial booking: Dec 01 to Dec 05
    initial_booking = {
        "room_id": 1,
        "guest_name": "Primary Guest",
        "check_in": "2026-12-01",
        "check_out": "2026-12-05"
    }
    res1 = client.post("/reservations", json=initial_booking)
    assert res1.status_code == 201

    # Overlapping booking: Dec 03 to Dec 07 (conflicts with existing Dec 01-05)
    conflicting_booking = {
        "room_id": 1,
        "guest_name": "Overlapping Guest",
        "check_in": "2026-12-03",
        "check_out": "2026-12-07"
    }
    res2 = client.post("/reservations", json=conflicting_booking)
    assert res2.status_code == 409
    assert res2.json()["detail"] == "Room is already booked for these dates"


def test_adjacent_non_overlapping_reservations_accepted(client):
    # Booking A: Dec 01 to Dec 05
    booking_a = {
        "room_id": 1,
        "guest_name": "Guest Alpha",
        "check_in": "2026-12-01",
        "check_out": "2026-12-05"
    }
    res_a = client.post("/reservations", json=booking_a)
    assert res_a.status_code == 201

    # Booking B starts exactly on check-out day of Booking A: Dec 05 to Dec 10
    booking_b = {
        "room_id": 1,
        "guest_name": "Guest Beta",
        "check_in": "2026-12-05",
        "check_out": "2026-12-10"
    }
    res_b = client.post("/reservations", json=booking_b)
    assert res_b.status_code == 201


def test_invalid_dates_checkout_before_checkin(client):
    payload = {
        "room_id": 1,
        "guest_name": "Invalid Date Guest",
        "check_in": "2026-12-10",
        "check_out": "2026-12-05"
    }
    response = client.post("/reservations", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "Check-out must be after check-in"


def test_invalid_dates_same_day(client):
    payload = {
        "room_id": 1,
        "guest_name": "Same Day Guest",
        "check_in": "2026-12-10",
        "check_out": "2026-12-10"
    }
    response = client.post("/reservations", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "Check-out must be after check-in"


def test_create_reservation_for_nonexistent_room(client):
    payload = {
        "room_id": 99999,
        "guest_name": "Ghost Room Guest",
        "check_in": "2026-12-01",
        "check_out": "2026-12-05"
    }
    response = client.post("/reservations", json=payload)
    assert response.status_code == 404
    assert response.json()["detail"] == "Room not found or inactive"


def test_availability_filters_booked_rooms(client):
    # Book room 1 for Dec 01 to Dec 05
    client.post("/reservations", json={
        "room_id": 1,
        "guest_name": "Booked Guest",
        "check_in": "2026-12-01",
        "check_out": "2026-12-05"
    })

    # Query availability during overlapping period: Dec 02 to Dec 04
    res_overlapping = client.get("/availability?check_in=2026-12-02&check_out=2026-12-04")
    assert res_overlapping.status_code == 200
    available_rooms = res_overlapping.json()
    available_ids = [r["id"] for r in available_rooms]
    assert 1 not in available_ids
    assert 2 in available_ids
    assert 3 in available_ids

    # Query availability outside booked period: Dec 10 to Dec 15
    res_free = client.get("/availability?check_in=2026-12-10&check_out=2026-12-15")
    assert res_free.status_code == 200
    free_ids = [r["id"] for r in res_free.json()]
    assert 1 in free_ids


def test_invalid_availability_dates(client):
    response = client.get(
        "/availability",
        params={
            "check_in": "2026-11-15",
            "check_out": "2026-11-10"
        }
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Check-out date must be after check-in date"


def test_concurrent_reservations_cannot_double_book(client):
    """Verify concurrent requests for the exact same room and dates never result in double booking."""
    barrier = Barrier(2)
    booking_data = {
        "room_id": 2,
        "check_in": "2026-12-20",
        "check_out": "2026-12-25"
    }

    def attempt_booking(guest_name):
        barrier.wait()
        payload = dict(booking_data, guest_name=guest_name)
        return client.post("/reservations", json=payload)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(attempt_booking, "Concurrent Guest 1")
        f2 = executor.submit(attempt_booking, "Concurrent Guest 2")
        r1 = f1.result()
        r2 = f2.result()

    statuses = [r1.status_code, r2.status_code]
    # At most ONE booking can ever succeed with 201; both cannot succeed
    successful_bookings = statuses.count(201)
    assert successful_bookings <= 1, f"Double booking detected! Statuses: {statuses}"
