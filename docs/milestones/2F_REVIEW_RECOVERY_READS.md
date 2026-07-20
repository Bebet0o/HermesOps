# Milestone 2F — Review, evidence, integration, and recovery reads

## Scope

Milestone 2F completes the read-only Controller projection needed by the
future HermesOps Console to display independent review and recovery state.

Implemented routes:

- `GET /api/v1/reviews`
- `GET /api/v1/reviews/{review_id}`
- `GET /api/v1/reviews/{review_id}/evidence`
- `GET /api/v1/recoveries`
- `GET /api/v1/recoveries/{recovery_id}`

The implementation projects the current durable SQLite records from
`review_results`, `reviewer_executions`, `integration_executions`,
`recovery_executions`, `runs`, `projects`, and `roles`.

## Safety model

All database connections remain SQLite `mode=ro` with `query_only=ON`.

The API never reads or returns reviewer prompt files, output files, worktrees,
container identifiers, raw result JSON, raw recovery evidence, recovery
actions, failure payloads, controller-owner values, or internal transaction
keys.

Historical run identifiers are used only as bounded internal join keys. Public
responses contain deterministic opaque transaction references instead.

Review evidence is a bounded metadata projection derived from persisted,
validated records. It reports verification flags, safe field names, digests,
and integration state without opening any artifact path.

Recovery details expose the decision, observed state, outcome, evidence digest,
and bounded safe field names. Evidence and action payload values remain
redacted.

## Integrity rules

The projection fails closed when it encounters:

- malformed review, execution, integration, recovery, role, or project IDs;
- unregistered or mismatched reviewer/recovery roles and profiles;
- workspace or network policy mismatches;
- inconsistent review, execution, integration, run, or project links;
- invalid decisions, verdicts, states, commit IDs, timestamps, booleans, or
  numeric metadata;
- malformed, oversized, path-like, or secret-bearing persisted data;
- invalid recovery evidence digests or structured payloads.

List cursors are HMAC-SHA256 authenticated, bound to the current Controller
session and all active filters. Session rotation invalidates existing cursors.
Resource ETags cover the complete public detail projection.

## Deliberate exclusions

Milestone 2F does not implement:

- review commands or recovery decisions;
- raw review artifact downloads;
- raw worker or reviewer logs;
- arbitrary filesystem access;
- database migrations;
- Console UI;
- Hermesfile workflows;
- audit or backup reads.
