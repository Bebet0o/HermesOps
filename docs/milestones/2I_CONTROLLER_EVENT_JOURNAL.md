# Milestone 2I — Durable Controller event journal

## Status

Implementation candidate. Validation and adversarial review are required before merge.

## Scope

- migration `015_controller_event_journal.sql`;
- immutable `controller_event_journal` separate from legacy `events` and `objective_events`;
- globally increasing SQLite sequence;
- stable event identifiers;
- monotonic aggregate revisions;
- redaction validation before persistence;
- bounded replay helper;
- transactional events for Controller objective and review commands.

## Deliberate exclusions

- WebSocket transport;
- SSE;
- retention or pruning;
- historical backfill;
- direct browser access to SQLite;
- Git, shell, recovery, restore or role mutation commands.

## Compatibility

The existing `events` and `objective_events` tables remain unchanged. Unknown well-formed event types are preserved. HTTP query APIs remain authoritative.
