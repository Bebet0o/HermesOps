# ADR 0001: Controller Owns Control-Plane Writes

Status: **Accepted**
Date: 2026-07-18

## Context

HermesOps currently contains several scripts that can manipulate durable state.
The future Console, orchestrator, supervisor, notifier, reviewer, recovery
manager, and CLI must not evolve into independent writers with inconsistent
validation and audit behavior.

## Decision

The HermesOps Controller process family is the sole authority for
control-plane state transitions.

All writers use the same command service, persistence unit of work, policy
engine, idempotency rules, audit service, and event journal.

The Console, Hermes Agent, workers, and external notification channels never
write SQLite directly.

Read-only queries may use dedicated repository interfaces, but API responses
are read models rather than raw rows.

## Consequences

Positive:

- invariants are enforced in one place;
- commands are consistently audited;
- events and state commit atomically;
- idempotency is possible;
- recovery sees authoritative evidence;
- the database schema can evolve independently from the WebUI.

Costs:

- existing scripts must gradually become API clients or shared modules;
- internal services cannot use privileged write shortcuts;
- the Controller becomes a critical service and requires strong backups and
  tests.

## Rejected alternatives

### Console writes SQLite

Rejected because it exposes internal schema, bypasses policy, and makes browser
security equivalent to database security.

### Every daemon owns its tables

Rejected because cross-domain transitions would require fragile distributed
coordination.

### Hermes Agent owns project state

Rejected because Agent sessions are execution dependencies, not the durable
system of record.
