
import json
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

URL = "http://127.0.0.1:8000/reservations"

# Both requests will start together
barrier = Barrier(2)

booking_data = {
    "room_id": 5,
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
        with urllib.request.urlopen(request, timeout=20) as response:
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


if __name__ == "__main__":
    print("Starting simultaneous booking test...\n")

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
        print("SUCCESS: Concurrency protection is working!")
    else:
        print("UNEXPECTED RESULT: Review the API and database logs.")
