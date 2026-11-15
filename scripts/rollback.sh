#!/usr/bin/env bash
set -euo pipefail

# Hotel Booking Safe Rollback Script
# Reverts the API service to a previous stable version without touching database volume

APP_DIR="/home/ubuntu/Hotel-Booking_devops-Pr"
cd "$APP_DIR"

TARGET_COMMIT="${1:-HEAD~1}"

echo "======================================================"
echo "Hotel Booking Safe Rollback Initiated"
echo "Target: ${TARGET_COMMIT}"
echo "Current HEAD: $(git rev-parse --short HEAD)"
echo "======================================================"

# 1. Checkout target commit
echo "Checking out ${TARGET_COMMIT}..."
git checkout "${TARGET_COMMIT}"
echo "Now at commit: $(git rev-parse --short HEAD)"

# 2. Validate docker-compose configuration
echo "Validating docker-compose configuration..."
docker compose config -q

# 3. Rebuild and restart API container without touching the database volume
echo "Rebuilding API container (preserving postgres_data volume)..."
docker compose up -d --build --no-deps api

# 4. Verify deployment health
echo "Verifying application health..."
for i in $(seq 1 20); do
  HEALTH=$(curl -sSf http://127.0.0.1:8000/health 2>/dev/null || true)
  READY=$(curl -sSf http://127.0.0.1:8000/ready 2>/dev/null || true)
  if [ -n "$HEALTH" ] && [ -n "$READY" ]; then
    echo "Rollback health & readiness checks passed successfully!"
    echo "Health: $HEALTH"
    echo "Readiness: $READY"
    docker compose ps
    echo "======================================================"
    echo "Rollback completed successfully to $(git rev-parse --short HEAD)"
    echo "======================================================"
    exit 0
  fi
  sleep 3
done

echo "ERROR: Rollback health check timed out."
docker compose logs --tail=50 api
exit 1
