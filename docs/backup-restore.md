# Database Backup, Retention & Restoration Runbook

This document details the database backup architecture, automated S3 storage lifecycle, and step-by-step restoration verification procedure for the **Hotel Booking Platform**.

---

## 1. Backup Strategy Overview

* **Database Engine:** PostgreSQL 16 Alpine running in Docker container `hotel-booking-db`.
* **Backup Destination:** Amazon S3 bucket `hotel-booking-backup-sneha` (Region: `eu-north-1`).
* **S3 Security:** Server-Side Encryption (SSE-S3 AES-256), S3 Bucket Versioning enabled, Public Access Blocked.
* **Authentication:** EC2 Instance IAM Role (Instance Profile) with least-privilege `s3:PutObject` and `s3:GetObject` permissions. Zero access keys stored on disk.
* **Frequency:** Automated daily cron execution at 02:00 UTC.

---

## 2. Automated Backup Implementation

The automated backup shell script is located at `/usr/local/bin/backup-db.sh` on the EC2 host:

```bash
#!/usr/bin/env bash
set -euo pipefail

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="/tmp/db_backups"
BACKUP_FILE="${BACKUP_DIR}/hotel_booking_${TIMESTAMP}.sql.gz"
S3_BUCKET="s3://hotel-booking-backup-sneha/backups"

mkdir -p "${BACKUP_DIR}"

echo "[$(date)] Starting PostgreSQL backup..."
docker exec hotel-booking-db pg_dump -U hotel_user -d hotel_booking | gzip > "${BACKUP_FILE}"

echo "[$(date)] Uploading ${BACKUP_FILE} to ${S3_BUCKET}..."
aws s3 cp "${BACKUP_FILE}" "${S3_BUCKET}/hotel_booking_${TIMESTAMP}.sql.gz"

echo "[$(date)] Cleaning up local temporary backup file..."
rm -f "${BACKUP_FILE}"

echo "[$(date)] Database backup completed successfully."
```

### Crontab Schedule
```cron
# Daily backup at 02:00 UTC
0 2 * * * /usr/local/bin/backup-db.sh >> /var/log/db_backup.log 2>&1
```

---

## 3. S3 Bucket Lifecycle & Retention Policy

The S3 bucket `hotel-booking-backup-sneha` enforces an automated lifecycle configuration:
1. **Current Versions:** Stored in S3 Standard storage class for immediate recovery access.
2. **Lifecycle Transition:** Older versions transition to `INTELLIGENT_TIERING` or `STANDARD_IA` after 30 days.
3. **Expiration:** Non-current backup versions are purged after 90 days, keeping storage costs optimized.

---

## 4. Disaster Recovery & Database Restoration Runbook

The following procedure guides a DevOps engineer through restoring a production backup.

### Step 1: List Available Backups in Amazon S3
```bash
aws s3 ls s3://hotel-booking-backup-sneha/backups/
```

### Step 2: Download the Target Backup File
```bash
mkdir -p /tmp/restore
aws s3 cp s3://hotel-booking-backup-sneha/backups/hotel_booking_<TIMESTAMP>.sql.gz /tmp/restore/backup.sql.gz
gunzip /tmp/restore/backup.sql.gz
```

### Step 3: Test Restoration into a Temporary Test Database (Non-Destructive)
To verify backup integrity without affecting active traffic:

```bash
# 1. Create a temporary database inside PostgreSQL container
docker exec -i hotel-booking-db psql -U hotel_user -d postgres -c "CREATE DATABASE hotel_booking_restore_test;"

# 2. Restore the SQL dump into the test database
docker exec -i hotel-booking-db psql -U hotel_user -d hotel_booking_restore_test < /tmp/restore/backup.sql

# 3. Verify table counts and data integrity
docker exec -i hotel-booking-db psql -U hotel_user -d hotel_booking_restore_test -c "SELECT count(*) FROM rooms;"
docker exec -i hotel-booking-db psql -U hotel_user -d hotel_booking_restore_test -c "SELECT count(*) FROM reservations;"

# 4. Clean up the temporary test database
docker exec -i hotel-booking-db psql -U hotel_user -d postgres -c "DROP DATABASE hotel_booking_restore_test;"
rm -f /tmp/restore/backup.sql
echo "Backup verification test passed!"
```

### Step 4: Full Production Database Disaster Recovery (Emergency Use Only)
If the primary database volume is corrupted or lost:

```bash
# 1. Temporarily stop incoming traffic by stopping the API container
docker compose stop api

# 2. Drop and recreate the production database
docker exec -i hotel-booking-db psql -U hotel_user -d postgres -c "DROP DATABASE hotel_booking WITH (FORCE);"
docker exec -i hotel-booking-db psql -U hotel_user -d postgres -c "CREATE DATABASE hotel_booking;"

# 3. Stream the SQL backup into the fresh database
docker exec -i hotel-booking-db psql -U hotel_user -d hotel_booking < /tmp/restore/backup.sql

# 4. Restart the API service
docker compose start api

# 5. Verify production endpoints
curl -s http://127.0.0.1:8000/ready
curl -s http://127.0.0.1:8000/rooms
```
