#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${HERMESOPS_ROOT:-/opt/docker/hermesops}"
REPO="${ROOT}/repo"

required_directories=(
    "$REPO"
    "${ROOT}/state/hermes-home"
    "${ROOT}/state/controller"
    "${ROOT}/secrets"
    "${ROOT}/workspaces"
    "${ROOT}/project-data"
    "${ROOT}/backups"
    "${ROOT}/logs"
    "${ROOT}/runtime"
)

for directory in "${required_directories[@]}"; do
    [[ -d "$directory" ]] || {
        echo "ABSENT: $directory" >&2
        exit 1
    }
done

[[ -d "${REPO}/.git" ]] || {
    echo "Le dépôt Git est absent." >&2
    exit 1
}

secret_mode="$(stat -c '%a' "${ROOT}/secrets")"

[[ "$secret_mode" == "700" ]] || {
    echo "Permissions incorrectes sur secrets: ${secret_mode}" >&2
    exit 1
}

git -C "$REPO" rev-parse --verify HEAD >/dev/null

echo "HermesOps layout: PASS"
