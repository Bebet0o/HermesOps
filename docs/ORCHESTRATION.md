# HermesOps orchestration DAG

Milestone 4A adds a durable multi-task scheduler above the transactional
worker/reviewer/integrator pipeline.

## Plan contract

A plan contains an objective, a bounded parallelism value, and an acyclic set
of tasks. Production tasks use `PIPELINE` and specify one enabled project, one
committing worker role, precise instructions, acceptance criteria and a
completion marker. Same-project write tasks must be dependency-ordered because
project writer concurrency is one.

## Execution lifecycle

For each `PIPELINE` task the orchestrator:

1. reserves a Git transaction and verified snapshot;
2. launches the selected isolated worker;
3. submits the exact result commit;
4. launches the independent read-only reviewer;
5. calls the controlled integration gate;
6. persists the worker, review, integration and run identifiers;
7. marks the task complete only after reviewed local integration.

Dependencies become `READY` only after every parent is `COMPLETED`. A failed
parent blocks descendants. Tasks from different projects or controller-only
test actions can run concurrently, bounded by both plan and global limits.

## Persistence and restart

The systemd user service owns one exclusive lock. Plans, tasks, dependencies,
attempts and daemon instances are durable in SQLite. On restart, interrupted
non-pipeline attempts become `ABANDONED` and are retried within their attempt
budget. Active transactional pipelines are never duplicated; the existing
Recovery Manager remains authoritative for their safe reconciliation.

## AI planner

`hermesops-planner.py` runs the `ops-orchestrator` profile without a project
workspace. It accepts a high-level objective and a fixed set of enabled
projects, then emits a strictly validated JSON DAG. AI plans start as `DRAFT`
unless explicitly activated.

## Operations

```bash
systemctl --user status hermesops-orchestrator.service
/opt/docker/hermesops/repo/scripts/hermesops-orchestrator.py daemon-status
/opt/docker/hermesops/repo/scripts/hermesops-orchestrator.py list
/opt/docker/hermesops/repo/scripts/hermesops-orchestrator.py status --plan PLAN_ID
```


## User-systemd portability

The Orchestrator runs in the per-user systemd manager. Its unit uses only the
hardening directives already validated by the Supervisor: `NoNewPrivileges`,
`PrivateTmp`, `RestrictSUIDSGID`, and `LockPersonality`. Mount-namespace and
kernel-protection directives that fail with `218/CAPABILITIES` in this runtime
are deliberately excluded.

A unit is considered ready only when systemd reports a running MainPID and
`daemon-status` confirms the exclusive lock, healthy Supervisor, and matching
SQLite instance in `RUNNING`.

## Reviewer transport resilience

Reviewer transport failures and reviewer decisions are separate states. A
missing marker is not retryable by itself. HermesOps reads the failed reviewer
execution log and retries only recognized provider/stream failures, including
the observed Codex `no SSE events` condition. Retries are bounded, audited and
reuse the same immutable transaction result; the worker is not rerun.

After every reviewer invocation, controller-owned runtime containers, profiles
and clones are removed using exact audited identifiers. A real `REJECT` or
`BLOCK_HUMAN` decision is never retried.


## Active sandbox protection

Worker and reviewer execution rows are reserved before their nested Docker
sandboxes are created. The sandbox ID is finalized later, which previously
left a race with the permanent orphan cleaner. Recovery now preserves any
sandbox whose `hermes-task-id` belongs to a SQLite task in `RUNNING` under an
active run. The normal sandbox ID remains the primary reference after it is
persisted.
