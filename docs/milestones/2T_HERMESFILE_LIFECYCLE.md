# Milestone 2T — Hermesfile Lifecycle

Status: **implementation candidate**

## Delivered boundary

Milestone 2T makes the Hermesfile v1 source editable and versioned through the
Controller and Console while preserving the existing sandbox-profile ownership
model introduced by 2N and 2O.

- migration 022 adds dedicated Hermesfile operations, actor-bound idempotency,
  and immutable command audit; source and canonical bytes remain in the existing
  `sandbox_profile_revisions` table;
- authenticated reads expose the current source, immutable revision history,
  one historical revision, and a bounded canonical path comparison;
- validation and template endpoints support guided creation without persisting
  invalid input;
- create and update perform strict Hermesfile validation and secret eligibility
  checks before opening the write transaction;
- update requires `If-Match` and creates exactly one new immutable source
  revision while advancing the sandbox profile resource revision by one;
- canonical JSON and the runtime configuration are deterministic read-only
  projections of the persisted Hermesfile source;
- operations, audit, idempotency, and Controller events retain hashes and bounded
  metadata only, never raw source or canonical content;
- the Console adds a same-origin editor, diagnostics, canonical/runtime preview,
  revision history, and path-only comparison without browser persistence.

## Source-of-truth rule

A Hermesfile remains a `SandboxProfile` source. Project identity, repository
configuration, scheduling policy, and objective state do not move into the
Hermesfile. SQLite stores the immutable source revision and derived canonical
projection required by the existing persistence contract; it does not create a
second independently editable YAML, TOML, or runtime source.

## Deliberate exclusions

- image construction or image pull;
- image activation or rollback;
- secret binding or secret values;
- revision deletion;
- profile archive/delete commands;
- objective lifecycle, owned by 2U;
- generic Controller proxying or browser persistence.

## Validation contract

The milestone requires migration fresh/rerun/trigger tests, direct and HTTP
Controller lifecycle tests, secret-redaction and concurrency tests, Console
source/proxy tests, deterministic Console build, full static validation, an
isolated transactional rehearsal, production migration with rollback, one local
commit, and an independent adversarial audit before any push.
