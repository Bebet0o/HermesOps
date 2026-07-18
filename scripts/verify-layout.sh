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

for file in \
    "${REPO}/VERSION" \
    "${REPO}/compose/agent.yaml" \
    "${REPO}/config/controller.toml"
do
    [[ -f "$file" ]] || {
        echo "ABSENT: $file" >&2
        exit 1
    }
done

secret_mode="$(stat -c '%a' "${ROOT}/secrets")"

[[ "$secret_mode" == "700" ]] || {
    echo "Permissions incorrectes sur secrets: ${secret_mode}" >&2
    exit 1
}

if [[ -d "${REPO}/.git" ]]; then
    git -C "$REPO" rev-parse --verify HEAD >/dev/null
    echo "HermesOps layout: PASS (git checkout)"
else
    version="$(tr -d '\r\n' <"${REPO}/VERSION")"
    [[ -n "$version" ]] || {
        echo "VERSION vide dans la source installée." >&2
        exit 1
    }
    echo "HermesOps layout: PASS (source archive ${version})"
fi
