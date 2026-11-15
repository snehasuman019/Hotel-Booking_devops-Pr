#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/Hotel-Booking_devops-Pr

echo "Validating docker-compose configuration..."
docker compose config -q

echo "Rebuilding and restarting API container..."
docker compose up -d --build --no-deps api

echo "Waiting for application health and readiness checks to pass..."
for i in $(seq 1 20); do
  HEALTH=$(curl -sSf http://127.0.0.1:8000/health 2>/dev/null || true)
  READY=$(curl -sSf http://127.0.0.1:8000/ready 2>/dev/null || true)
  if [ -n "$HEALTH" ] && [ -n "$READY" ]; then
    echo "Health probe response: $HEALTH"
    echo "Readiness probe response: $READY"
    echo "Deployment health check passed successfully."
    docker compose ps
    exit 0
  fi
  sleep 3
done

echo "Health check failed after 60 seconds."
docker compose ps
exit 1
