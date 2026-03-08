#!/bin/bash
# Comobot - macOS Docker Launcher
# Double-click this file to start Comobot
cd "$(dirname "$0")/.."

PORT=18790

# Check Docker Desktop
if ! docker info &>/dev/null; then
    osascript -e 'display dialog "Docker Desktop is not running.\n\nPlease start Docker Desktop and try again." buttons {"OK"} default button "OK" with icon caution'
    open -a "Docker"
    echo "Waiting for Docker Desktop to start..."
    for i in $(seq 1 30); do
        sleep 2
        docker info &>/dev/null && break
        echo "  Waiting... ($i/30)"
    done
    docker info &>/dev/null || { echo "Docker failed to start"; exit 1; }
fi

echo "Starting Comobot..."
docker compose up -d

echo "Waiting for Comobot to be ready..."
for i in $(seq 1 15); do
    sleep 2
    if curl -sf "http://localhost:$PORT/api/health" &>/dev/null; then
        break
    fi
    echo "  Waiting... ($i/15)"
done

open "http://localhost:$PORT"
echo "Comobot is running at http://localhost:$PORT"
