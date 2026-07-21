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

## Adversarial hardening

The post-implementation review adds migration 016 and verifies:

- SQLite `INSERT OR REPLACE` cannot bypass journal immutability;
- secret-key normalization covers camelCase, kebab-case and dotted keys;
- common credential value formats are rejected before persistence;
- persisted timestamps use canonical RFC 3339 UTC form;
- concurrent writers preserve global sequence and aggregate revision order;
- `review.human_review_requested` is part of the public v1 event catalog.
