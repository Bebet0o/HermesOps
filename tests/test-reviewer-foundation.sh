#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/opt/docker/hermesops"
REPO="${ROOT}/repo"
DB="${ROOT}/state/controller/hermesops.db"

[[ -x "${REPO}/scripts/hermesops-reviewer.py" ]]
[[ -x "${REPO}/scripts/hermesops-worker.py" ]]
[[ -x "${REPO}/scripts/hermes-worker-entry.py" ]]
[[ -f "${REPO}/migrations/005_reviewer_executions.sql" ]]
[[ -f "${REPO}/docs/REVIEWERS.md" ]]

python3 -m py_compile \
    "${REPO}/scripts/hermesops-reviewer.py"

grep -Fq 'def precreate_reviewer_sandbox' \
    "${REPO}/scripts/hermesops-reviewer.py"

grep -Fq 'f"{clone}:/workspace:ro"' \
    "${REPO}/scripts/hermesops-reviewer.py"

grep -Fq 'if workspace_mount.get("RW"):' \
    "${REPO}/scripts/hermesops-reviewer.py"

grep -Fq '"--network=none"' \
    "${REPO}/scripts/hermesops-reviewer.py"

grep -Fq 'repository_unchanged' \
    "${REPO}/scripts/hermesops-reviewer.py"

grep -Fq 'def validate_controller_schema' \
    "${REPO}/scripts/hermesops-reviewer.py"

grep -Fq 'UPDATE runs SET heartbeat_at = ? WHERE run_id = ?' \
    "${REPO}/scripts/hermesops-reviewer.py"

grep -Fq 'UPDATE project_locks' \
    "${REPO}/scripts/hermesops-reviewer.py"

if grep -Fq 'updated_at' \
    "${REPO}/scripts/hermesops-reviewer.py"
then
    echo "Reviewer contains unsupported runs.updated_at reference." >&2
    exit 1
fi

for table in runs project_locks tasks review_results reviewer_executions
do
    [[ "$(
        sqlite3 "$DB" \
            "SELECT COUNT(*)
             FROM sqlite_master
             WHERE type='table'
               AND name='${table}';"
    )" == "1" ]] || {
        echo "Required Controller table absent: ${table}" >&2
        exit 1
    }
done

grep -Fq 'HERMESOPS_REVIEW_JSON_BEGIN' \
    "${REPO}/scripts/hermesops-reviewer.py"

[[ "$(
    sqlite3 "$DB" \
        "SELECT COUNT(*)
         FROM sqlite_master
         WHERE type='table'
           AND name='reviewer_executions';"
)" == "1" ]]

[[ "$(
    sqlite3 "$DB" \
        "SELECT role_kind || '|' ||
                workspace_mode || '|' ||
                may_push
         FROM roles
         WHERE role_id='reviewer';"
)" == "reviewer|read_only|0" ]]

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

LATEST_MIGRATION_NUMBER="$((
    10#${LATEST_MIGRATION_FILE%%_*}
))"

[[ "$(
    sqlite3 "$DB" 'PRAGMA user_version;'
)" == "$LATEST_MIGRATION_NUMBER" ]]

sqlite3 "$DB" 'PRAGMA foreign_key_check;' |
grep -q . && {
    echo "SQLite foreign_key_check failed." >&2
    exit 1
}

[[ "$(sqlite3 "$DB" 'PRAGMA quick_check;')" == "ok" ]]

INVALID_DECISION="$(
    sqlite3 "$DB" <<'SQL' 2>/dev/null || true
PRAGMA foreign_keys = ON;
SAVEPOINT reviewer_validation;
INSERT INTO reviewer_executions (
    execution_id,
    review_id,
    task_id,
    run_id,
    role_id,
    source_profile,
    runtime_profile,
    outer_container_name,
    prompt_path,
    output_path,
    cpu_limit,
    memory_mb,
    decision,
    created_at
)
VALUES (
    'invalid',
    'invalid',
    'invalid',
    'invalid',
    'reviewer',
    'ops-reviewer',
    'invalid',
    'invalid',
    'invalid',
    'invalid',
    1,
    512,
    'INVALID',
    'invalid'
);
ROLLBACK TO reviewer_validation;
RELEASE reviewer_validation;
SQL
)"

[[ -z "$INVALID_DECISION" ]]

BAD_EXECUTIONS="$(
    sqlite3 "$DB" \
        "SELECT COUNT(*)
         FROM reviewer_executions
         WHERE workspace_mode <> 'read_only'
            OR network_enabled <> 0
            OR (finished_at IS NOT NULL
                AND (
                    mount_verified <> 1
                    OR isolation_verified <> 1
                    OR repository_unchanged <> 1
                ));"
)"

[[ "$BAD_EXECUTIONS" == "0" ]]

echo "HermesOps independent reviewer foundation: PASS"
