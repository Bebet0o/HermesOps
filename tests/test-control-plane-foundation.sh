#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${HERMESOPS_ROOT:-/opt/docker/hermesops}"
REPO="${ROOT}/repo"
DB="${ROOT}/state/controller/hermesops.db"

"${REPO}/scripts/hermesops-registry.py" validate
"${REPO}/scripts/hermesops-db.py" migrate
"${REPO}/scripts/hermesops-registry.py" sync
"${REPO}/scripts/hermesops-db.py" integrity

[[ -f "$DB" ]]

[[ "$(stat -c '%a' "$DB")" == "640" ]]

[[ "$(
    sqlite3 "$DB" \
        'PRAGMA journal_mode;'
)" == "wal" ]]

[[ "$(
    sqlite3 "$DB" \
        'PRAGMA user_version;'
)" == "1" ]]

required_tables=(
    projects
    runs
    tasks
    project_locks
    events
    approvals
    review_results
    memory_records
)

for table in "${required_tables[@]}"; do
    count="$(
        sqlite3 "$DB" \
            "SELECT COUNT(*)
             FROM sqlite_master
             WHERE type='table'
               AND name='${table}';"
    )"

    [[ "$count" == "1" ]] || {
        echo "Table absente : $table" >&2
        exit 1
    }
done

echo "HermesOps control-plane foundation: PASS"
