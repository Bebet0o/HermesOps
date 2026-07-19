# Milestone 2E adversarial review

This review hardens the published task, run, worker, and persisted event-log
read models without adding routes, writes, migrations, or raw artifact access.

## Corrected defects

### Worker registry integrity

A worker execution could previously claim a different role, source profile, or
workspace mode from the role registered for its orchestration task. The public
projection now requires exact agreement between the task, worker execution,
and role registry.

### Transaction project isolation

A task could reference a legacy transaction belonging to another project and
still expose that transaction's state and event stream. The linked transaction
project must now match the orchestration task project. Persisted events with an
explicit conflicting project identifier also fail closed.

### SQLite type safety

SQLite allows values with unexpected storage classes even in columns declared
as integers. Direct `int()` and `bool()` conversion could therefore turn
corrupt worker metadata into an HTTP 500 or silently reinterpret values such
as `2` as true. Numeric resource limits, counters, flags, attempt numbers, and
exit codes now use bounded fail-closed validation and return a controlled 503
projection error.

### Timestamp containment

Task, run, worker, and persisted-event timestamps were returned as raw strings.
A corrupt value could therefore expose a path-like or control-character value
through a field trusted by the Console. Public timestamps are now bounded,
timezone-aware ISO-8601 values. Invalid values fail closed without being
returned.

## Regression coverage

The review reproduces and fixes six failures:

- mismatched worker role;
- mismatched worker source profile;
- mismatched worker workspace mode;
- cross-project linked transaction;
- malformed numeric worker metadata producing HTTP 500;
- path-like persisted-event timestamp being exposed.

All pre-existing API, objective, execution, durable-service, live-probe,
secret-scan, static, and runtime validations remain mandatory.
