# Milestone 2R — Operational Dashboard

Status: **implementation candidate RC1**

## Base

- Required parent: `4ef68e058db3b8d31f0f9b7dd0be7f58401b1a23`
- Branch: `milestone/2r-operational-dashboard`
- SQLite schema remains version `20`.

## Scope

Milestone 2R turns the authenticated 2Q shell into a bounded read-only
operational dashboard. It adds six explicit Controller collection reads,
partial-data handling, attention and active-work summaries, deterministic build
updates, live probes, and adversarial source/proxy coverage.

## Security invariants

- no SQLite, Docker, workspace, Agent, or host-path access from the Console;
- no general proxy and no query strings through the 2R gateway;
- no Controller URL in JavaScript;
- no browser persistence, WebSocket, dynamic code execution, or HTML injection;
- only redacted Controller projections are displayed;
- collection and body sizes remain bounded;
- missing collections remain visibly partial and are never extrapolated;
- no Controller or database migration is introduced.

## Acceptance

- deterministic source-to-distribution build passes;
- Console foundation, Controller-client, and operational-dashboard suites pass;
- all six dashboard routes forward correctly and out-of-scope routes fail
  before upstream;
- unauthenticated live dashboard reads return `401` through the same-origin
  Console gateway;
- static validation passes;
- SQLite remains schema 20 and byte-identical;
- one local commit is produced;
- no push or merge occurs before an independent adversarial audit.

## Out of scope

2S project lifecycle, 2T Hermesfile lifecycle, 2U objective lifecycle, 2V
detailed orchestration and execution views, 2W human review/recovery actions,
and 2X realtime events and reconciliation.
