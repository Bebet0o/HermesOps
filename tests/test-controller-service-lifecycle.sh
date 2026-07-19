#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C
export PYTHONDONTWRITEBYTECODE=1

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="${HERMESOPS_ROOT:-/opt/docker/hermesops}"
UNIT="hermesops-controller-api.service"
PROBE="${REPO}/scripts/hermesops-controller-probe.py"

dump_failure() {
    local rc="${1:-$?}"
    trap - ERR
    echo
    echo "=== Controller service failure diagnostics ===" >&2
    systemctl --user status "$UNIT" --no-pager --full >&2 || true
    journalctl --user -u "$UNIT" -n 200 --no-pager -o short-precise >&2 || true
    systemctl --user show "$UNIT" \
        -p LoadState -p ActiveState -p SubState -p Result \
        -p ExecMainCode -p ExecMainStatus --no-pager >&2 || true
    exit "$rc"
}

trap 'dump_failure $?' ERR

systemctl --user daemon-reload
systemctl --user enable "$UNIT" >/dev/null
systemctl --user restart "$UNIT"

python3 "$PROBE" \
    --base-url http://127.0.0.1:8765 \
    --session-file "${ROOT}/secrets/controller-session" \
    --wait-seconds 30

PID_BEFORE="$(systemctl --user show -p MainPID --value "$UNIT")"
[[ "$PID_BEFORE" =~ ^[1-9][0-9]*$ ]]

systemctl --user restart "$UNIT"
python3 "$PROBE" \
    --base-url http://127.0.0.1:8765 \
    --session-file "${ROOT}/secrets/controller-session" \
    --wait-seconds 30

PID_AFTER="$(systemctl --user show -p MainPID --value "$UNIT")"
[[ "$PID_AFTER" =~ ^[1-9][0-9]*$ ]]
[[ "$PID_AFTER" != "$PID_BEFORE" ]]

systemctl --user stop "$UNIT"
! systemctl --user is-active --quiet "$UNIT"

systemctl --user start "$UNIT"
systemctl --user is-enabled --quiet "$UNIT"
systemctl --user is-active --quiet "$UNIT"

python3 "$PROBE" \
    --base-url http://127.0.0.1:8765 \
    --session-file "${ROOT}/secrets/controller-session" \
    --wait-seconds 30

trap - ERR
echo "HERMESOPS_CONTROLLER_SERVICE_LIFECYCLE_PASS"
