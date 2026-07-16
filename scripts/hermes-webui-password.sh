#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${HERMESOPS_ROOT:-/opt/docker/hermesops}"
SECRET="${ROOT}/secrets/webui.env"

[[ -r "$SECRET" ]] || {
    echo "Secret WebUI illisible : $SECRET" >&2
    exit 1
}

sed -n \
    's/^HERMES_WEBUI_PASSWORD=//p' \
    "$SECRET" |
head -n 1
