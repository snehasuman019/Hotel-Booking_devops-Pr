# Hotel Booking Platform — Internship Assessment Defense & Interview Guide

This guide prepares you to confidently present, explain, and defend every architectural and engineering decision in your Hotel Booking DevOps project.

---

## 1. Core Technical Concepts & Questions

### Q1: Why FastAPI over Django, Flask, or Express?
* **High Performance**: Built on top of Starlette and Pydantic, running asynchronously with Uvicorn. Capable of handling high-concurrency reservation queries with minimal latency.
* **Automatic OpenAPI/Swagger Documentation**: Native `/docs` and `/openapi.json` generated directly from Pydantic schemas, eliminating API documentation drift.
* **Native Async & Type Safety**: Strongly-typed data validation ensures malformed dates or missing guest names are rejected with `400 Bad Request` before reaching database locks.

---

### Q2: Why Docker and Docker Compose?
* **Environment Parity**: Ensures that what passes automated tests in GitHub Actions behaves identically on local developer machines and on AWS EC2 Ubuntu.
* **Network & Process Isolation**: PostgreSQL (`5432`) and FastAPI (`8000`) are bound strictly to localhost loopback (`127.0.0.1`), ensuring zero direct exposure to the public internet.
* **Named Volume Persistence**: The PostgreSQL data directory is mapped to `postgres_data`, ensuring container restarts, code updates, or host reboots never destroy reservation records.
* **Service Dependency Orchestration**: `depends_on` with `condition: service_healthy` guarantees FastAPI does not attempt to bind connections until PostgreSQL responds to `pg_isready`.

---

### Q3: How Does the Continuous Integration (CI) Pipeline Work?
* **Trigger**: Automatic execution on every `git push` or `pull_request` targeting `main`.
* **Ephemeral Service Containers**: GitHub Actions spins up an isolated PostgreSQL 16 container service with healthy polling.
* **Automated Test Matrix**:
  1. Installs Python 3.13 and dependencies via `pip`.
  2. Executes unit and integration test suites using `pytest -v`.
  3. Verifies endpoints (`/`, `/health`, `/rooms`, `/availability`) and concurrency collision protection.
* **Artifact/Image Validation**: Runs `docker build -t hotel-booking-api:test .` to ensure the container image builds without syntax or packaging errors before any code can be merged.

---

### Q4: How is Continuous Deployment (CD) Intended to Work via OIDC & SSM?
* **Workflow Run Trigger**: Automatically triggered upon successful completion of the CI pipeline on `main`.
* **Keyless Authentication (OIDC)**: 
  - The GitHub Actions runner requests a short-lived OpenID Connect JWT token signed by GitHub's authority (`token.actions.githubusercontent.com`).
  - AWS STS evaluates the token against `GitHubHotelBookingDeployRole`'s trust policy, checking repository name (`snehasuman019/Hotel-Booking_devops-Pr`) and branch (`refs/heads/main`).
  - If valid, STS issues temporary AWS credentials with a 1-hour expiration.
* **Command Execution via AWS Systems Manager**:
  - The runner calls `aws ssm send-command` using document `AWS-RunShellScript` targeting instance `i-03d455ea3e1887798`.
  - The EC2 SSM Agent polls Systems Manager over outbound TLS (Port 443) and receives the deployment script.
  - The script switches to user `ubuntu`, pulls `main`, validates configuration (`docker compose config -q`), rebuilds the API container (`docker compose up -d --build --no-deps api`), and polls `http://127.0.0.1:8000/health`.
  - **Zero Inbound SSH Ports**: EC2 requires NO open port 22 in its security group, eliminating brute-force attack vectors.

---

### Q5: How Does Nginx Function as a Reverse Proxy with HTTPS?
* **Traffic Ingress**: External HTTP requests on port 80 and HTTPS requests on port 443 hit Nginx.
* **Automated HTTP-to-HTTPS Redirection**: Requests on port 80 receive a `301 Moved Permanently` redirecting to `https://$host$request_uri`.
* **SSL/TLS Termination**: Nginx terminates the TLS encryption using Let's Encrypt certificates issued for IP `13.48.120.203`.
* **Header Preservation**: Proxies clean HTTP traffic internally to FastAPI on `127.0.0.1:8000`, setting `X-Real-IP`, `X-Forwarded-For`, and `X-Forwarded-Proto` so the application knows the client's true IP and protocol.
* **Automated Renewal**: Systemd timer `certbot.timer` runs twice daily. When the certificate approaches renewal (within 30 days), Certbot renews it and executes an Nginx deploy hook (`systemctl reload nginx`) with zero downtime.

---

### Q6: How are Database Backups Stored and Restored?
* **Disaster Recovery Policy**:
  - Scheduled daily via cron at `0 2 * * *` (02:00 UTC / 07:30 AM IST).
  - Shell script `/home/ubuntu/backup-hotel-db.sh` executes `docker exec hotel-booking-db pg_dump`, compresses the output with `gzip`, and streams it to private S3 bucket `hotel-booking-backup-sneha`.
* **Storage Security**: S3 Bucket Versioning protects against accidental deletion; SSE-S3 AES-256 enforces encryption at rest; S3 Lifecycle Rules automatically transition or expire old backups.
* **Restoration Verification**: Validated by streaming an S3 backup into a temporary verification database (`hotel_booking_restore_test`) and checking `SELECT count(*) FROM rooms;`, confirming all room records restore with 100% data fidelity.

---

### Q7: How Does Pessimistic Locking Prevent Double Booking?
* **ACID Transactions**: When two simultaneous requests attempt to book Room 101 for overlapping dates:
  ```python
  room = db.query(Room).filter(Room.id == reservation.room_id).with_for_update().first()
  ```
* **Lock Queue**: The first request acquires an exclusive row-level lock on the room record. The second request is forced by PostgreSQL to wait until Transaction 1 commits or rolls back.
* **Overlap Evaluation**: Once Transaction 1 commits its booking, Transaction 2 acquires the lock, detects the newly committed confirmed booking overlapping its requested date range, rolls back, and returns `HTTP 409 Conflict`.

---

### Q8: What Happens When a Deployment Fails?
* **Health Check Loop**: The deployment script polls the local API health endpoint up to 20 times with 3-second sleep intervals (60 seconds total grace period).
* **Rollback Initiation**: If the health check fails to return `HTTP 200`, the deployment halts, preserving the previous Git commit reference, rebuilding the last known stable API image, and keeping the database volume untouched.

---

## 2. Final Demonstration Checklist for Reviewers

- [ ] Open [https://13.48.120.203/health](https://13.48.120.203/health) in a browser to show `{"status":"healthy"}` over HTTPS.
- [ ] Open [https://13.48.120.203/docs](https://13.48.120.203/docs) to demonstrate the interactive Swagger UI.
- [ ] Execute `GET /rooms` to show active rooms (Room 101: Single, 102: Double, 103: Deluxe).
- [ ] Execute `GET /availability?check_in=2026-12-01&check_out=2026-12-05` to show room availability querying.
- [ ] Show `GET /availability?check_in=2026-12-05&check_out=2026-12-01` to demonstrate `400 Bad Request` date ordering validation.
- [ ] Show GitHub Actions CI pipeline (#15) passing green on `main`.
- [ ] Show the Docker Compose configuration with loopback isolation (`127.0.0.1`) and persistent named volume `postgres_data`.
- [ ] Show the S3 backup script and cron schedule on EC2.
- [ ] Explain the concurrency protection formula and row locking mechanism.
