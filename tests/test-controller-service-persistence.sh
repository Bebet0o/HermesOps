#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C
export PYTHONDONTWRITEBYTECODE=1

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="${HERMESOPS_ROOT:-/opt/docker/hermesops}"
UNIT="hermesops-controller-api.service"
UNIT_PATH="${HOME}/.config/systemd/user/${UNIT}"
WANTS_PATH="${HOME}/.config/systemd/user/default.target.wants/${UNIT}"

systemctl --user is-enabled --quiet "$UNIT"
systemctl --user is-active --quiet "$UNIT"

[[ -f "$UNIT_PATH" ]]
[[ -L "$WANTS_PATH" ]]
[[ "$(readlink -f "$WANTS_PATH")" == "$(readlink -f "$UNIT_PATH")" ]]

LINGER="$(loginctl show-user "$(id -un)" -p Linger --value)"
[[ "$LINGER" == "yes" ]]

python3 "${REPO}/scripts/hermesops-controller-probe.py" \
    --base-url http://127.0.0.1:8765 \
    --session-file "${ROOT}/secrets/controller-session" \
    --wait-seconds 10

echo "HERMESOPS_CONTROLLER_SERVICE_PERSISTENCE_PASS"
