#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${HERMESOPS_ROOT:-/opt/docker/hermesops}"
REPO="${ROOT}/repo"
DB="${ROOT}/state/controller/hermesops.db"

for file in \
    "${REPO}/scripts/hermesops-objectives.py" \
    "${REPO}/scripts/hermesops-orchestrator.py" \
    "${REPO}/migrations/010_objective_queue.sql" \
    "${REPO}/config/orchestrator.toml" \
    "${REPO}/docs/OBJECTIVES.md" \
    "${REPO}/tests/test-objective-queue-foundation.sh"
do
    [[ -f "$file" ]]
done

python3 -m py_compile \
    "${REPO}/scripts/hermesops-objectives.py" \
    "${REPO}/scripts/hermesops-orchestrator.py"

"${REPO}/scripts/hermesops-objectives.py" self-test
"${REPO}/scripts/hermesops-orchestrator.py" self-test

grep -Fq 'def synchronize_objective_states' \
    "${REPO}/scripts/hermesops-orchestrator.py"
grep -Fq 'def reserve_ai_objective' \
    "${REPO}/scripts/hermesops-orchestrator.py"
grep -Fq 'def reconcile_interrupted_planner_executions' \
    "${REPO}/scripts/hermesops-orchestrator.py"
grep -Fq 'Preserve global priority' \
    "${REPO}/scripts/hermesops-orchestrator.py"
grep -Fq "objective.status = 'RUNNING'" \
    "${REPO}/scripts/hermesops-orchestrator.py"
grep -Fq 'global_parallel_objectives = 2' \
    "${REPO}/config/orchestrator.toml"
grep -Fq 'planning_retry_backoff_seconds = 30' \
    "${REPO}/config/orchestrator.toml"

# HERMESOPS_OBJECTIVE_QUEUE_MINIMUM_MIGRATION_V1
OBJECTIVE_QUEUE_SCHEMA_VERSION="$(
    sqlite3 "$DB" 'PRAGMA user_version;'
)"
[[ "$OBJECTIVE_QUEUE_SCHEMA_VERSION" =~ ^[0-9]+$ ]]
[[ "$OBJECTIVE_QUEUE_SCHEMA_VERSION" -ge 10 ]]
[[ "$(sqlite3 "$DB" 'PRAGMA quick_check;')" == "ok" ]]
! sqlite3 "$DB" 'PRAGMA foreign_key_check;' | grep -q .

for table in objective_queue objective_attempts objective_events
do
    [[ "$(
        sqlite3 "$DB" \
            "SELECT COUNT(*) FROM sqlite_master
             WHERE type='table' AND name='${table}';"
    )" == "1" ]]
done

systemctl --user is-enabled --quiet hermesops-orchestrator.service
systemctl --user is-active --quiet hermesops-orchestrator.service

DAEMON_STATUS="$("${REPO}/scripts/hermesops-orchestrator.py" daemon-status)"
python3 - "$DAEMON_STATUS" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["version"] == "orchestrator-v2"
assert payload["lock_held"] is True
assert payload["supervisor_healthy"] is True
assert payload["instance"]["status"] == "RUNNING"
assert isinstance(payload["objective_counts"], dict)
PY

python3 - "$DB" <<'PY'
import json
import sqlite3
import sys
from datetime import datetime

connection = sqlite3.connect(sys.argv[1])
connection.row_factory = sqlite3.Row

objectives = {
    row["objective"]: row
    for row in connection.execute("SELECT * FROM objective_queue")
}

high_name = "High-priority project-B objective used to prove global queue ordering."
low_a_name = "Low-priority project-A objective used to prove cross-project concurrency."
low_b_name = "Low-priority project-B objective that must wait behind the high-priority project-B objective."
pause_name = "Prove that a queued objective can be paused and resumed without dispatch."
cancel_name = "Prove cancellation before dispatch."

for name in (high_name, low_a_name, low_b_name, pause_name, cancel_name):
    assert name in objectives, name

for name in (high_name, low_a_name, low_b_name, pause_name):
    assert objectives[name]["status"] == "COMPLETED", (name, objectives[name]["status"])
assert objectives[cancel_name]["status"] == "CANCELLED"

parse = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))

def task_for(name: str):
    return connection.execute(
        """
        SELECT task.*
        FROM orchestration_tasks AS task
        JOIN objective_queue AS objective
          ON objective.plan_id = task.plan_id
        WHERE objective.objective = ?
        """,
        (name,),
    ).fetchone()

high = task_for(high_name)
low_a = task_for(low_a_name)
low_b = task_for(low_b_name)
assert high and low_a and low_b
assert parse(objectives[high_name]["created_at"]) > parse(objectives[low_b_name]["created_at"])
assert parse(high["started_at"]) < parse(low_b["started_at"])
assert max(parse(high["started_at"]), parse(low_a["started_at"])) < min(
    parse(high["finished_at"]), parse(low_a["finished_at"])
)
assert parse(high["finished_at"]) <= parse(low_b["started_at"])

pause_id = objectives[pause_name]["objective_id"]
pause_events = {
    row[0]
    for row in connection.execute(
        "SELECT event_type FROM objective_events WHERE objective_id = ?",
        (pause_id,),
    )
}
assert "OBJECTIVE_PAUSED" in pause_events
assert "OBJECTIVE_RESUMED" in pause_events

cancel_plan = objectives[cancel_name]["plan_id"]
assert connection.execute(
    """
    SELECT COUNT(*)
    FROM orchestration_attempts AS attempt
    JOIN orchestration_tasks AS task
      ON task.orchestration_task_id = attempt.orchestration_task_id
    WHERE task.plan_id = ?
    """,
    (cancel_plan,),
).fetchone()[0] == 0

ai = connection.execute(
    """
    SELECT *
    FROM objective_queue
    WHERE source = 'AI'
      AND objective LIKE 'Create exactly one independently reviewable PIPELINE task%'
    ORDER BY created_at DESC
    LIMIT 1
    """
).fetchone()
assert ai is not None
assert ai["status"] == "COMPLETED", ai["status"]
attempt_statuses = [
    row[0]
    for row in connection.execute(
        """
        SELECT status
        FROM objective_attempts
        WHERE objective_id = ?
        ORDER BY attempt_number
        """,
        (ai["objective_id"],),
    )
]
assert "ABANDONED" in attempt_statuses, attempt_statuses
assert "COMPLETED" in attempt_statuses, attempt_statuses

pipeline = connection.execute(
    """
    SELECT result_json
    FROM orchestration_tasks
    WHERE plan_id = ? AND kind = 'PIPELINE' AND status = 'COMPLETED'
    ORDER BY created_at
    LIMIT 1
    """,
    (ai["plan_id"],),
).fetchone()
assert pipeline is not None
result = json.loads(pipeline["result_json"])
assert result["worker"]["exit_code"] == 0
assert result["worker"]["marker_found"] is True
assert result["integration"]["integrated"] is True
assert result["reviewer"]["decision"] == "APPROVE"

active = connection.execute(
    """
    SELECT COUNT(*)
    FROM objective_queue
    WHERE status IN (
        'QUEUED', 'PLANNING', 'RUNNING',
        'PAUSE_REQUESTED', 'CANCEL_REQUESTED'
    )
    """
).fetchone()[0]
assert active == 0, active
PY

[[ "$(sqlite3 "$DB" 'SELECT COUNT(*) FROM project_locks;')" == "0" ]]
[[ "$(sqlite3 "$DB" 'SELECT COUNT(*) FROM projects WHERE enabled=1;')" == "0" ]]

# HERMESOPS_4C_EXPECTED_PRECOMMIT_DIRTY_SET_V1
REPOSITORY_STATUS="$(
    git -C "$REPO" status --porcelain=v1 --untracked-files=all
)"

python3 - "$REPOSITORY_STATUS" <<'PY'
import sys

lines = [line for line in sys.argv[1].splitlines() if line]
if not lines:
    raise SystemExit(0)

allowed = {
    "VERSION",
    "config/notifier.toml",
    "docs/NOTIFICATIONS.md",
    "docs/STATE.md",
    "migrations/011_notification_outbox.sql",
    "scripts/configure-hermesops-telegram.sh",
    "scripts/hermesops-control.py",
    "scripts/hermesops-notifier.py",
    "scripts/hermesopsctl",
    "systemd/user/hermesops-notifier.service",
    "tests/test-notification-foundation.sh",
    "tests/test-objective-queue-foundation.sh",
}

observed = set()
for line in lines:
    if len(line) < 4:
        raise AssertionError(f"Malformed porcelain entry: {line!r}")
    status = line[:2]
    path = line[3:]
    if path not in allowed:
        raise AssertionError(f"Unexpected repository change: {line}")
    if status not in {"??", " M"}:
        raise AssertionError(
            f"Unexpected change type for {path}: {status!r}"
        )
    if path in observed:
        raise AssertionError(f"Duplicate repository change: {path}")
    observed.add(path)

required = allowed - {"VERSION"}
missing = required - observed
if missing:
    raise AssertionError(
        "Expected 4C pre-commit changes missing: "
        + ", ".join(sorted(missing))
    )
PY

echo "HermesOps persistent autonomous objective queue foundation: PASS"
