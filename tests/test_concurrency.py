import os
import json
import ssl
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

BASE_URL = os.getenv("APP_URL", "http://127.0.0.1:8000").rstrip("/")
URL = f"{BASE_URL}/reservations"
SSL_CTX = ssl._create_unverified_context() if URL.startswith("https") else None

# Both requests will start together
barrier = Barrier(2)

booking_data = {
    "room_id": 1,
    "guest_name": "Concurrency Guest",
    "check_in": "2026-12-20",
    "check_out": "2026-12-23"
}


def make_booking(request_number):
    data = json.dumps(booking_data).encode("utf-8")

    request = urllib.request.Request(
        URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    # Wait until both threads are ready
    barrier.wait()

    try:
        with urllib.request.urlopen(request, timeout=20, context=SSL_CTX) as response:
            return {
                "request": request_number,
                "status": response.status,
                "body": response.read().decode("utf-8")
            }

    except urllib.error.HTTPError as error:
        return {
            "request": request_number,
            "status": error.code,
            "body": error.read().decode("utf-8")
        }
    except Exception as error:
        return {
            "request": request_number,
            "status": 500,
            "body": str(error)
        }


if __name__ == "__main__":
    print(f"Starting simultaneous booking test against {URL}...\n")

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(make_booking, 1),
            executor.submit(make_booking, 2)
        ]

        results = [future.result() for future in futures]

    for result in results:
        print(f"Request {result['request']}")
        print(f"HTTP Status: {result['status']}")
        print(f"Response: {result['body']}\n")

    statuses = sorted(result["status"] for result in results)

    if statuses == [201, 409]:
        print("SUCCESS: Concurrency protection is working! Exactly one booking succeeded and one was rejected.")
    else:
        print(f"RESULT: Status codes returned: {statuses}")
