# Milestone 2Q — Browser Session and Controller Client

Status: **implemented locally on the milestone branch**

## Base

- Required parent: `757b4a327a32eade29ded792793c9ab612bc0206`
- Branch: `milestone/2q-browser-session-controller-client`
- SQLite schema remains version `20`.

## Scope

Milestone 2Q connects the dedicated Console from 2P to the existing Controller
browser-authentication lifecycle without broadening the Controller authority.
It adds:

- a narrow same-origin HTTP gateway in the Console service;
- browser login, authoritative session refresh, capability read, and logout;
- CSRF and idempotency use for authentication mutations;
- strict in-memory-only credential handling;
- degraded-mode presentation when the Controller is unavailable;
- deterministic build, service, probe, and adversarial tests for the boundary.

## Security invariants

- Console and Controller targets remain validated loopback IP addresses.
- The browser never receives a direct Controller URL.
- POST requests require one exact Console origin.
- The gateway forwards only five allowlisted method/path pairs.
- Request and response bodies are bounded.
- Redirects, cross-origin headers, unsupported framing, duplicate sensitive
  headers, and unexpected routes fail closed.
- Session cookies remain HTTP-only, Secure, SameSite Strict, and server-owned.
- JavaScript uses no browser persistence, WebSocket, dynamic code execution, or
  offline queue.

## Acceptance

- deterministic source-to-distribution build passes;
- Console foundation and Controller-client suites pass;
- static validation passes;
- live Console probe observes unauthenticated session status `401` through the
  same-origin gateway;
- Controller and Console services are active with zero unexpected restarts;
- production SQLite remains schema 20 and byte-identical during application;
- one local commit is produced;
- no push or merge occurs before an independent adversarial audit.

## Out of scope

Dashboard data belongs to 2R. Project lifecycle belongs to 2S. Hermesfile
lifecycle belongs to 2T. Objective lifecycle belongs to 2U. Orchestration views
belong to 2V. Human review and recovery actions belong to 2W. WebSocket events
and reconciliation belong to 2X.
