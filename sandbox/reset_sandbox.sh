#!/usr/bin/env bash
# Fully resets the sandbox: drops the container + volume, brings it back up
# clean, reseeds data. Use this between demo rehearsals so numbers are
# consistent and no leftover fix (e.g. an index the Fixer created) sticks
# around from the last run.
set -euo pipefail

cd "$(dirname "$0")"

echo "Stopping and removing sandbox container + volume..."
docker compose down -v

echo "Starting fresh sandbox container..."
docker compose up -d

echo "Waiting for Postgres to accept connections..."
sleep 3

echo "Seeding data..."
python seed.py "$@"

echo "Sandbox reset complete. Ready for demo."
