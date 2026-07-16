#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${HERMESOPS_ROOT:-/opt/docker/hermesops}"
SECRET_FILE="${ROOT}/secrets/agent.env"

API_KEY="$(
    sed -n 's/^API_SERVER_KEY=//p' "$SECRET_FILE" |
    head -n 1
)"

[[ -n "$API_KEY" ]] || {
    echo "API_SERVER_KEY absente." >&2
    exit 1
}

RUNNING="$(
    docker inspect hermesops-agent \
        --format '{{.State.Running}}'
)"

HEALTH="$(
    docker inspect hermesops-agent \
        --format '{{.State.Health.Status}}'
)"

[[ "$RUNNING" == "true" ]]
[[ "$HEALTH" == "healthy" ]]

curl \
    --silent \
    --show-error \
    --fail \
    http://127.0.0.1:8642/health |
    jq -e '.status == "ok"' >/dev/null

curl \
    --silent \
    --show-error \
    --fail \
    --header "Authorization: Bearer ${API_KEY}" \
    http://127.0.0.1:8642/v1/models |
    jq -e '.object == "list"' >/dev/null

BINDING="$(docker port hermesops-agent 8642/tcp)"
[[ "$BINDING" == "127.0.0.1:8642" ]]

echo "Hermes Agent foundation: PASS"
