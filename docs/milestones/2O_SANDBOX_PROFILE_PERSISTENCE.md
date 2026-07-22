# Milestone 2O — Sandbox profile persistence foundation

Milestone 2O begins the durable lifecycle of Hermesfile v1 sandbox profiles.

## Implemented in this first slice

- SQLite schema version 20;
- durable sandbox profile identities;
- immutable source revisions;
- validated source and deterministic canonical JSON retention;
- source and canonical SHA-256 fingerprints;
- bounded safe diagnostics;
- atomic operator CLI import;
- authenticated profile list and detail reads;
- signed, session-bound list cursors;
- resource revisions and ETags;
- live capability discovery and a read probe.

Only sources that pass Hermesfile v1 validation are persisted. A separate
high-confidence credential scan runs before persistence. Rejected source values
are never included in public diagnostics.

## State boundary

New profiles begin in `draft`.

This slice does not transition profiles to `ready`, `active`, `inactive`, or
`archived`. Those states remain reserved for later build, validation-container,
activation and lifecycle milestones.

## Mutation boundary

The public Controller exposes only:

```text
GET /api/v1/sandboxes
GET /api/v1/sandboxes/{sandbox_id}
```

Operator import remains a local administration command:

```bash
scripts/hermesops-sandbox-profile.py import Hermesfile
```

HTTP create/update remains disabled until a dedicated command persistence
contract provides CSRF, idempotency, optimistic concurrency, audit and event
journal integration.

## Explicitly not implemented

- HTTP profile writes;
- persistence of invalid sources;
- image builds or package resolution;
- build logs;
- validation-container execution;
- activation or rollback;
- secret binding;
- profile deletion;
- project or role selection.

`hermesfile_builds=false` remains authoritative.
