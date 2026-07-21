# Milestone 2L — Reviewer assignment workflow

Milestone 2L separates reviewer assignment from reviewer execution.

## Durable lifecycle

Each controlled reviewer transport attempt owns one immutable assignment:

```text
ASSIGNED -> CLAIMED -> COMPLETED
        \-> FAILED
        \-> CANCELLED
```

The orchestrator creates the assignment before invoking the reviewer. The
reviewer claims it in the same SQLite transaction that reserves the task and
`reviewer_executions` row. Completion or failure closes the assignment in the
same transaction as the reviewer result. Recovery closes any remaining active
assignment with the bounded failure code `RECOVERY_ABANDONED`.

## Safety properties

- one active assignment per run;
- immutable assignment identity and terminal history;
- reviewer role must be enabled, read-only, non-committing, non-pushing and
  network-disabled;
- no raw prompts, output, paths or failure reasons are stored in assignments;
- each retry creates a new assignment number;
- historical reviewer executions are not rewritten;
- legacy events and the durable Controller event journal are emitted in the
  same transaction as each lifecycle transition.

This milestone does not add reviewer reruns or operator assignment mutation to
the public Controller API.
