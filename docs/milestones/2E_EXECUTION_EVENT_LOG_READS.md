# Milestone 2E — task, run, worker, and persisted event-log reads

Milestone 2E extends the local Controller API with the next read-only slice
required by the future HermesOps Console.

## Implemented routes

- `GET /api/v1/objectives/{objective_id}/tasks`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks/{task_id}/runs`
- `GET /api/v1/runs/{run_id}`
- `GET /api/v1/runs/{run_id}/logs`

These routes implement the existing OpenAPI contracts without adding a new
contract version.

## Read models

### Tasks

Public tasks are projected from `orchestration_tasks`, linked to an objective
through `objective_queue.plan_id`. The projection exposes bounded operational
metadata such as state, role, priority, dependency counts, attempt counts, and
timestamps.

Instructions, acceptance payloads, stored results, and failure text are never
returned. Their presence is represented only by redacted availability flags.

### Runs and workers

A public Run represents one row from `orchestration_attempts`. It can include a
safe, bounded worker summary from `worker_executions` and a linked transaction
state from `runs`.

The projection never returns:

- repository or workspace paths;
- prompt or output paths;
- outer or nested container identifiers;
- raw worker, review, integration, or attempt payloads;
- raw failure reasons;
- output-file contents.

Worker resource limits and verification booleans are exposed because they are
useful for the Console and do not reveal host paths or credentials.

### Logs

Run logs are a bounded projection of rows already persisted in `events` for the
linked transaction run. Each entry contains a sequence, timestamp, severity,
event type, and a message derived only from the controlled event type.

`payload_json` is never returned. The API reports only whether a payload was
present, redacted, and syntactically valid. Raw worker output files are not
opened and remain explicitly unsupported by the capability document.

The response metadata includes `snapshot_sequence`, and continuation uses
`after_sequence` with a maximum page size of 500.

## Security and consistency

- SQLite is opened with `mode=ro` and `PRAGMA query_only = ON`.
- Task and run pagination cursors are HMAC-SHA256 authenticated with the
  validated local Controller session.
- Session rotation invalidates previously issued execution cursors.
- Task and run ETags hash the complete public projection.
- Legacy identifiers, states, profile names, event types, and severities fail
  closed when they cannot be projected safely.
- Database schema failures map to controlled `503 database_unavailable`
  responses.
- No migration and no mutation are introduced.

## Capabilities

The Controller advertises:

- `task_reads: true`
- `run_reads: true`
- `worker_execution_reads: true`
- `persisted_event_log_reads: true`
- `raw_worker_log_reads: false`
- `run_artifact_reads: false`

The negative capability flags are deliberate: arbitrary files and artifacts
will not be exposed until a later contract defines containment, redaction,
limits, and authorization.


## RC1 live role-alias compatibility correction

The first server transaction passed every isolated API, objective, execution,
service, static, and secret test, but the real task-list probe returned 503.

A read-only diagnostic confirmed:

- schema version 11 and migrations 1 through 11 were present;
- every required execution table and column existed;
- task, plan, objective, project, profile, and workspace fields were valid;
- historical orchestration tasks used registered role aliases such as
  `worker_docs`;
- these aliases were linked to safe public profiles such as
  `ops-worker-docs`.

The initial projection accepted hyphenated role identifiers but rejected the
underscore form already used by the durable orchestration data.

RC1 accepts lowercase role aliases containing hyphens or underscores, but only
when the exact identifier successfully joins to the `roles` registry. This
preserves fail-closed behavior for invented aliases, path-like values, control
characters, and corrupt foreign references.

No database row, migration, route, or write behavior is changed.


## RC2 opaque transaction-key compatibility correction

RC1 fixed historical registered role aliases and moved the real Controller
probe from the task list to the run list. A second read-only diagnostic then
showed that every public run, task, objective, worker, role, and profile
identifier was valid. The remaining failure came exclusively from
`orchestration_attempts.run_id`: production stores an older internal
transaction key whose format is not the public `run-<hex>` form assumed by the
initial projection.

RC2 treats this value according to its actual role:

- it is an internal database join key, not the public Run identifier;
- the raw value is never returned;
- a bounded, control-character-free internal key is required;
- the key must resolve exactly to the linked row in `runs`;
- a linked worker execution must reference the same transaction key;
- the public `transaction_run_id` is a deterministic opaque
  `transaction-<hex>` reference derived with SHA-256;
- event-log lookup continues to use the raw key internally through parameterized
  SQLite queries.

This preserves live historical compatibility without widening a public
identifier grammar or exposing the durable internal key. No migration or write
behavior is introduced.
