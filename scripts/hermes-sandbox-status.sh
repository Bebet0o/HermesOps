#!/usr/bin/env bash
set -Eeuo pipefail

AGENT="hermesops-agent"
ENGINE="hermesops-sandbox-engine"

echo "=== Services hôte ==="
docker ps \
    --filter "name=^/${AGENT}$" \
    --filter "name=^/${ENGINE}$" \
    --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'

echo
echo "=== Docker distant vu par Hermes Agent ==="
docker exec "$AGENT" sh -lc '
    printf "DOCKER_HOST=%s\n" "$DOCKER_HOST"
    docker info --format "Name={{.Name}} Driver={{.Driver}} Containers={{.Containers}} Images={{.Images}}"
'

echo
echo "=== Sandboxes imbriquées ==="
docker exec "$ENGINE" docker ps -a \
    --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Labels}}'

echo
echo "=== Sandboxes accidentelles sur le daemon hôte ==="
docker ps -a \
    --filter 'label=hermes-agent=1' \
    --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
