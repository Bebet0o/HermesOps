# Milestone 2U — Objective Lifecycle

Status: **implementation candidate RC1**

## Base

- required parent: `0332d49b5c7b32c82b1a6a0d1d52fe547142c4f8`;
- required tree: `022e548000047407e787a66c5959144696031622`;
- branch: `milestone/2u-objective-lifecycle`;
- SQLite schema remains version `22`.

## Scope

Milestone 2U connects the existing secure objective command and read surfaces to
the dedicated Console. It adds a bounded objective list, creation form, detail
view, state-dependent pause/resume/cancel actions, and a bounded read of the
Controller operation returned by each mutation.

The Console reuses the existing Controller contracts:

- `GET|POST /api/v1/objectives`;
- `GET /api/v1/objectives/{objective_id}`;
- `POST /api/v1/objectives/{objective_id}/commands/{pause|resume|cancel}`;
- `GET /api/v1/operations/{operation_id}`;
- `POST /api/v1/auth/csrf`.

## Security invariants

- no direct SQLite, workspace, Docker, Agent, or host-path access;
- no generic proxy, query strings, encoded path, or nested task exposure;
- mutations require same-origin cookies, CSRF and generated idempotency keys;
- objective and operation identifiers are syntax-checked before fetch;
- only pause, resume and cancel are exposed;
- cancellation requires explicit browser confirmation;
- controls are hidden when the authoritative raw state makes the transition
  unavailable;
- operation following is bounded to three reads and never persisted in the
  browser;
- untrusted strings are rendered with `textContent` only;
- no browser storage, dynamic HTML, WebSocket, or background reconciliation.

## Explicitly out of scope

- explicit start/plan/replan/archive/delete objective commands;
- task graph, run logs, artifacts, evidence or review detail;
- WebSocket reconciliation or continuous polling;
- project, Hermesfile or sandbox scope expansion;
- any database migration.

## Acceptance

- Console source/distribution build is reproducible;
- exact proxy boundary tests pass for allowed and denied objective routes;
- creation, detail, command and operation forwarding tests pass;
- existing objective Controller tests and inherited Console suites pass;
- static validation passes with migration sequence still at 22;
- production database and services remain unchanged during calibration;
- no branch, commit, push or merge before the transactional package gate.
