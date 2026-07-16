#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${HERMESOPS_ROOT:-/opt/docker/hermesops}"
REPO="${ROOT}/repo"

exec docker compose \
    --env-file "${REPO}/compose/images.lock.env" \
    -f "${REPO}/compose/agent.yaml" \
    "$@"
