# Operations & Troubleshooting Runbook

This runbook provides complete operational procedures for inspecting, managing, troubleshooting, and recovering the **Hotel Booking Platform** services on AWS EC2.

---

## 1. Service Management Commands

All service commands must be executed on the EC2 host from `/home/ubuntu/Hotel-Booking_devops-Pr`.

### 1.1 Checking Service Status
```bash
# Check Docker container status, uptime, and health state
docker compose ps

# Detailed container health inspection
docker inspect --format='{{json .State.Health}}' hotel-booking-api | jq
docker inspect --format='{{json .State.Health}}' hotel-booking-db | jq

# Check host system resources
free -h
df -h /
uptime
```

### 1.2 Starting and Stopping Services Safely
```bash
# Start all services in the background
docker compose up -d

# Stop all services gracefully (WITHOUT destroying data volumes)
docker compose down

# Restart the API service only (zero database interruption)
docker compose restart api

# Rebuild and restart API service after configuration changes
docker compose up -d --build --no-deps api

# CAUTION: NEVER execute 'docker compose down -v' in production!
# Flag '-v' deletes the persistent named volume postgres_data!
```

---

## 2. Log Inspection Runbook

### 2.1 Application Logs (FastAPI)
```bash
# View last 100 lines of API logs
docker compose logs --tail=100 api

# Follow API logs in real-time
docker compose logs -f api

# Filter for booking confirmation and conflict logs
docker compose logs api | grep -E "Reservation confirmed|Reservation conflict"
```

### 2.2 PostgreSQL Database Logs
```bash
# View last 100 lines of database logs
docker compose logs --tail=100 db

# Follow DB logs in real-time
docker compose logs -f db

# Check for connection errors or locks
docker compose logs db | grep -iE "error|fatal|lock"
```

### 2.3 Nginx Web Server Logs
```bash
# Nginx access log (live requests)
sudo tail -f /var/log/nginx/access.log

# Nginx error log
sudo tail -f /var/log/nginx/error.log

# Verify Nginx configuration syntax
sudo nginx -t

# Reload Nginx without downtime
sudo systemctl reload nginx
```

---

## 3. Health & Readiness Verification

```bash
# 1. External HTTPS Liveness Probe
curl -i https://13.48.120.203/health

# 2. External HTTPS Deep Readiness Probe (Verifies DB connection)
curl -i https://13.48.120.203/ready

# 3. Local Host Probes (via SSH/SSM on EC2)
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/ready
curl -s http://127.0.0.1:8000/db-test

# 4. PostgreSQL Direct Socket Probe
docker compose exec db pg_isready -U hotel_user -d hotel_booking
```

---

## 4. Troubleshooting Common Failures

### Scenario 1: `502 Bad Gateway` from Nginx
* **Symptom:** Browser or API clients receive `HTTP 502 Bad Gateway`.
* **Root Cause:** The `hotel-booking-api` container is stopped, restarting, or not listening on `127.0.0.1:8000`.
* **Diagnosis:**
  ```bash
  docker compose ps
  docker compose logs --tail=50 api
  ```
* **Resolution:**
  ```bash
  # Check if container is crashing due to configuration:
  docker compose up -d --build --no-deps api
  curl -s http://127.0.0.1:8000/health
  ```

---

### Scenario 2: `503 Service Unavailable` on `/ready` or `/db-test`
* **Symptom:** API returns HTTP 503 with `"detail": "Database readiness check failed"`.
* **Root Cause:** PostgreSQL container is unhealthy, out of connections, or down.
* **Diagnosis:**
  ```bash
  docker compose ps db
  docker compose logs --tail=50 db
  ```
* **Resolution:**
  ```bash
  # Check database container health:
  docker compose restart db
  # Wait 10 seconds for pg_isready, then test:
  curl -s http://127.0.0.1:8000/ready
  ```

---

### Scenario 3: Continuous Deployment (CD) Fails at SSM
* **Symptom:** GitHub Actions CD pipeline fails with `Remote Execution Failed on EC2` or timeout.
* **Diagnosis:**
  ```bash
  # Check SSM Agent status on EC2:
  sudo systemctl status snap.amazon-ssm-agent.amazon-ssm-agent.service
  
  # Inspect SSM Agent logs:
  sudo tail -n 100 /var/log/amazon/ssm/amazon-ssm-agent.log
  ```
* **Resolution:**
  ```bash
  # Restart SSM Agent if disconnected:
  sudo systemctl restart snap.amazon-ssm-agent.amazon-ssm-agent.service
  ```

---

### Scenario 4: Disk Space Exhaustion on EC2
* **Symptom:** Containers stop unexpectedly, `No space left on device` in logs.
* **Diagnosis:**
  ```bash
  df -h /
  docker system df
  ```
* **Resolution:**
  ```bash
  # Clean up dangling images and build caches safely:
  docker image prune -f
  docker builder prune -f
  # Note: Do NOT run 'docker volume prune -f' without verifying!
  ```

---

## 5. Rollback Procedure

When a newly deployed application version introduces a bug or regression, execute the automated safe rollback script:

```bash
# 1. Revert to the immediately preceding git commit
sudo -u ubuntu -H bash /home/ubuntu/Hotel-Booking_devops-Pr/scripts/rollback.sh

# 2. Or revert to a specific known good commit SHA:
sudo -u ubuntu -H bash /home/ubuntu/Hotel-Booking_devops-Pr/scripts/rollback.sh <COMMIT_SHA>

# 3. Verify application health
curl -s https://13.48.120.203/ready
```
This script rebuilds the `api` container against the previous commit, preserving all database data in `postgres_data`.
