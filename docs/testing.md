# Testing & Quality Assurance Guide

This document specifies the testing methodology, automated test suites, concurrency validation, and CI/CD verification procedures implemented for the **Hotel Booking Platform**.

---

## 1. Test Suite Architecture

The test suite is structured around **Pytest** and **FastAPI TestClient**, executing both functional endpoint tests and concurrent multi-threaded conflict simulations.

| Test File | Scope | Execution Target |
| :--- | :--- | :--- |
| [`tests/test_api.py`](file:///e:/hotel-booking-devops/tests/test_api.py) | 16 automated tests covering all domain APIs, date validation, overlap rejection, and concurrency | GitHub Actions CI & Local Dev |
| [`tests/test_concurrency.py`](file:///e:/hotel-booking-devops/tests/test_concurrency.py) | Standalone multi-threaded live probe using synchronized barriers | Staging / Production EC2 Probe |
| [`tests/conftest.py`](file:///e:/hotel-booking-devops/tests/conftest.py) | Pytest session setup, room catalog seeding, and test reservation cleanup | Test Harness & Isolation |

---

## 2. Test Cases Specification

### 2.1 General & Observability Endpoints
* `test_home`: Verifies `GET /` returns HTTP 200 with service status `running`.
* `test_health`: Verifies `GET /health` returns HTTP 200 with `status: healthy` (Liveness probe).
* `test_ready`: Verifies `GET /ready` returns HTTP 200 with `status: ready` and `database: connected` (Readiness probe).
* `test_db_test`: Verifies `GET /db-test` executes a database query and returns HTTP 200.

### 2.2 Room Catalog Endpoints
* `test_get_rooms`: Verifies `GET /rooms` returns all active hotel rooms.
* `test_get_single_room`: Verifies `GET /rooms/1` returns valid room details for Room 101.
* `test_invalid_room`: Verifies `GET /rooms/99999` returns HTTP 404 with `"detail": "Room not found"`.

### 2.3 Reservation & Concurrency Protection Endpoints
* `test_create_valid_reservation`:
  - **Input:** Room 1, dates `2026-12-01` to `2026-12-05`.
  - **Expectation:** HTTP 201 Created, status `CONFIRMED`, unique reference `HTL-XXXXXXXXXX`.
* `test_overlapping_reservation_returns_409`:
  - **Input:** Consecutive booking for Room 1 with overlapping dates `2026-12-03` to `2026-12-07`.
  - **Expectation:** HTTP 409 Conflict with `"detail": "Room is already booked for these dates"`.
* `test_adjacent_non_overlapping_reservations_accepted`:
  - **Input:** Booking starting on the exact check-out day of an existing booking (`2026-12-05` to `2026-12-10`).
  - **Expectation:** HTTP 201 Created (adjacent dates are valid and do not conflict).
* `test_invalid_dates_checkout_before_checkin`:
  - **Input:** `check_in: 2026-12-10`, `check_out: 2026-12-05`.
  - **Expectation:** HTTP 400 Bad Request with `"detail": "Check-out must be after check-in"`.
* `test_invalid_dates_same_day`:
  - **Input:** Same check-in and check-out date (`2026-12-10`).
  - **Expectation:** HTTP 400 Bad Request.
* `test_create_reservation_for_nonexistent_room`:
  - **Input:** `room_id: 99999`.
  - **Expectation:** HTTP 404 with `"detail": "Room not found or inactive"`.
* `test_availability_filters_booked_rooms`:
  - **Setup:** Book Room 1 for `2026-12-01` to `2026-12-05`.
  - **Query:** `GET /availability?check_in=2026-12-02&check_out=2026-12-04`.
  - **Expectation:** Room 1 is excluded from the returned list; Rooms 2 and 3 are present.
* `test_concurrent_reservations_cannot_double_book`:
  - **Setup:** Synchronizes two simultaneous threads using `threading.Barrier` targeting Room 2 for the exact same dates.
  - **Expectation:** At most one request succeeds with HTTP 201; the second request is rejected with HTTP 409. Zero double-bookings.

---

## 3. How to Run Automated Tests

### 3.1 Local Environment
```bash
# Activate virtual environment
source venv/bin/activate  # Or on Windows: .\venv\Scripts\Activate.ps1

# Run the complete test suite with verbose output
python -m pytest -v

# Run tests with short traceback on failures
python -m pytest -v --tb=short
```

### 3.2 Automated CI Pipeline Execution
In GitHub Actions ([`.github/workflows/ci.yml`](file:///e:/hotel-booking-devops/.github/workflows/ci.yml)), the test suite runs inside an Ubuntu runner backed by an ephemeral PostgreSQL 16 service container:
```yaml
    services:
      postgres:
        image: postgres:16-alpine
        ports:
          - 5432:5432
...
    steps:
      - name: Run automated tests
        run: python -m pytest -v
```

---

## 4. Live Server Concurrency Verification

To test concurrency directly against the live AWS EC2 deployment:

```bash
# Execute concurrency test against live HTTPS endpoint
python tests/test_concurrency.py
```
Expected output:
```text
Starting simultaneous booking test against https://13.48.120.203/reservations...

Request 1
HTTP Status: 201
Response: {"id":...,"reference":"HTL-...","status":"CONFIRMED"}

Request 2
HTTP Status: 409
Response: {"detail":"Room is already booked for these dates"}

SUCCESS: Concurrency protection is working! Exactly one booking succeeded and one was rejected.
```
