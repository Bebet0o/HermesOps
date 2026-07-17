#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${HERMESOPS_ROOT:-/opt/docker/hermesops}"
REPO="${ROOT}/repo"
DB="${ROOT}/state/controller/hermesops.db"
UNIT="${HOME}/.config/systemd/user/hermesops-supervisor.service"

[[ -x "${REPO}/scripts/hermesops-supervisor.py" ]]
[[ -x "${REPO}/scripts/hermesops-recovery.py" ]]
[[ -f "${REPO}/migrations/008_supervisor_watchdog.sql" ]]
[[ -f "${REPO}/config/supervisor.toml" ]]
[[ -f "${REPO}/systemd/user/hermesops-supervisor.service" ]]
[[ -f "${REPO}/docs/SUPERVISOR.md" ]]
[[ -f "$UNIT" ]]

python3 -m py_compile \
    "${REPO}/scripts/hermesops-supervisor.py"

"${REPO}/scripts/hermesops-supervisor.py" self-test

grep -Fq 'def acquire_lock' \
    "${REPO}/scripts/hermesops-supervisor.py"
grep -Fq 'fcntl.LOCK_EX | fcntl.LOCK_NB' \
    "${REPO}/scripts/hermesops-supervisor.py"
grep -Fq 'def wait_for_core_health' \
    "${REPO}/scripts/hermesops-supervisor.py"
grep -Fq 'hermesops-sandbox-engine' \
    "${REPO}/scripts/hermesops-supervisor.py"
grep -Fq 'hermesops-agent' \
    "${REPO}/scripts/hermesops-supervisor.py"
grep -Fq '"startup"' \
    "${REPO}/scripts/hermesops-supervisor.py"
grep -Fq '"periodic"' \
    "${REPO}/scripts/hermesops-supervisor.py"
grep -Fq 'Restart=always' \
    "${REPO}/systemd/user/hermesops-supervisor.service"
grep -Fq 'NoNewPrivileges=true' \
    "${REPO}/systemd/user/hermesops-supervisor.service"

LATEST_MIGRATION_FILE="$(
    find "${REPO}/migrations" \
        -maxdepth 1 \
        -type f \
        -name '[0-9][0-9][0-9]_*.sql' \
        -printf '%f\n' |
    sort |
    tail -n 1
)"
[[ -n "$LATEST_MIGRATION_FILE" ]]
LATEST_MIGRATION_NUMBER="$((10#${LATEST_MIGRATION_FILE%%_*}))"
[[ "$(sqlite3 "$DB" 'PRAGMA user_version;')" == \
   "$LATEST_MIGRATION_NUMBER" ]]

for table in supervisor_instances supervisor_sweeps
do
    [[ "$(
        sqlite3 "$DB" \
            "SELECT COUNT(*)
             FROM sqlite_master
             WHERE type='table'
               AND name='${table}';"
    )" == "1" ]]
done

sqlite3 "$DB" 'PRAGMA foreign_key_check;' |
grep -q . && {
    echo "SQLite foreign_key_check failed." >&2
    exit 1
}
[[ "$(sqlite3 "$DB" 'PRAGMA quick_check;')" == "ok" ]]

[[ "$(loginctl show-user "$(id -un)" -p Linger --value)" == "yes" ]]
systemctl --user is-enabled --quiet hermesops-supervisor.service
systemctl --user is-active --quiet hermesops-supervisor.service

STATUS_JSON="$(
    "${REPO}/scripts/hermesops-supervisor.py" status
)"
python3 - "$STATUS_JSON" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["version"] == "supervisor-v1"
assert payload["lock_held"] is True
assert payload["health"]["healthy"] is True
assert payload["instance"]["status"] == "RUNNING"
assert payload["last_sweep"]["status"] in {
    "COMPLETED",
    "SKIPPED",
}
PY

[[ "$(
    sqlite3 "$DB" \
        "SELECT COUNT(*)
         FROM supervisor_sweeps
         WHERE status='COMPLETED';"
)" -ge 1 ]]

[[ "$(
    sqlite3 "$DB" \
        "SELECT COUNT(*)
         FROM supervisor_instances
         WHERE status='ABANDONED';"
)" -ge 1 ]]

[[ "$(sqlite3 "$DB" 'SELECT COUNT(*) FROM project_locks;')" == "0" ]]
[[ "$(sqlite3 "$DB" 'SELECT COUNT(*) FROM projects WHERE enabled=1;')" == "0" ]]
[[ "$(
    sqlite3 "$DB" \
        "SELECT COUNT(*)
         FROM approvals
         WHERE status='PENDING';"
)" == "0" ]]

echo "HermesOps automatic supervisor foundation: PASS"
