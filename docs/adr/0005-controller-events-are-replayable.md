# ADR 0005: Controller Events Are Replayable

Status: **Accepted**
Date: 2026-07-18

## Context

HermesOps Console must show long-running work, progress, reviews, recovery,
sandbox builds, and infrastructure health in real time.

A transient WebSocket-only stream would lose state during reconnects and force
the UI to guess what happened.

## Decision

The Controller persists redacted domain events with:

- globally increasing sequence;
- stable event ID;
- schema version;
- aggregate identity and revision;
- correlation and causation IDs;
- event data.

The WebSocket stream provides at-least-once delivery and replay after a
sequence number.

Clients deduplicate by event ID, order by sequence, and refresh snapshots when
replay is unavailable.

The query API remains authoritative.

## Consequences

Positive:

- browser reconnect is deterministic;
- operators can inspect event history;
- progress and state changes share one contract;
- missed events do not require invented state;
- correlation improves incident diagnosis.

Costs:

- event storage and retention must be managed;
- schema compatibility rules are required;
- clients must implement replay and reconciliation;
- secret redaction must occur before event persistence.

## Rejected alternatives

### WebSocket messages without persistence

Rejected because network interruptions would create silent gaps.

### Poll every resource continuously

Rejected because it is inefficient and provides poor temporal evidence.

### Treat events as the only state store

Rejected for the first beta because current domain state and migrations remain
simpler in explicit relational tables.
