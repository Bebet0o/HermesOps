#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${HERMESOPS_ROOT:-/opt/docker/hermesops}"
REPO="${ROOT}/repo"
export HERMES_UID="${HERMES_UID:-$(id -u)}"
export HERMES_GID="${HERMES_GID:-$(id -g)}"

exec docker compose \
    --project-directory "${REPO}/compose" \
    --env-file "${REPO}/compose/images.lock.env" \
    -f "${REPO}/compose/agent.yaml" \
    "$@"
