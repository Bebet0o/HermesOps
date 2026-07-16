#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${HERMESOPS_ROOT:-/opt/docker/hermesops}"
REPO="${ROOT}/repo"
DB="${ROOT}/state/controller/hermesops.db"

"${REPO}/scripts/hermesops-roles.py" validate
"${REPO}/scripts/hermesops-db.py" migrate
"${REPO}/scripts/hermesops-roles.py" sync
"${REPO}/scripts/hermesops-roles.py" verify-profiles
"${REPO}/scripts/hermesops-db.py" integrity

ROLE_COUNT="$(
    sqlite3 "$DB" \
        'SELECT COUNT(*) FROM roles WHERE enabled = 1;'
)"

[[ "$ROLE_COUNT" == "6" ]] || {
    echo "Nombre de rôles inattendu : $ROLE_COUNT" >&2
    exit 1
}

PUSH_COUNT="$(
    sqlite3 "$DB" \
        'SELECT COUNT(*) FROM roles WHERE may_push != 0;'
)"

[[ "$PUSH_COUNT" == "0" ]]

echo "HermesOps role fleet: PASS"
