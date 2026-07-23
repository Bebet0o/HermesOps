# Milestone 2P — Console Web Foundation

Status: **implementation milestone**

Base commit: `677e685f6d5d64adea5030442f44eaca337fa5f9`

## Objective

Create the independent HermesOps Console technical foundation without adding
business workflows or coupling the browser to SQLite, Docker, Hermes Agent, or
internal scripts.

## Delivered scope

- semantic and responsive Console shell;
- routes for dashboard, projects, objectives, executions, reviews, events, and
  administration;
- deterministic Python-only static build;
- committed source and byte-reproducible distribution manifest;
- dedicated loopback-only user service on port 8788;
- strict static allowlist and bounded HTTP implementation;
- security headers and no-network CSP;
- build, unit, concurrency, adversarial HTTP, systemd, install, and runtime
  probe coverage;
- public architecture and installation documentation.

## Invariants

- SQLite remains at schema version 20 and is not opened by the Console.
- The Controller API remains authoritative and unchanged.
- The legacy Hermes WebUI remains available on port 8787.
- The Console does not make HTTP, WebSocket, or browser-storage calls.
- No frontend package manager or downloaded dependency is introduced.
- No secret, bootstrap session, provider credential, host path, or raw runtime
  payload is embedded in the distribution.
- No business mutation is exposed.

## Acceptance

The milestone passes when:

1. the static distribution rebuilds byte-for-byte at least 16 times;
2. every product route returns the same allowlisted shell;
3. all security headers and CSP restrictions are present;
4. traversal, encoding, query, Host, method, symlink, hardlink, and unexpected
   source-file tests fail closed;
5. concurrent reads remain bounded and consistent;
6. the systemd user unit installs, starts, survives a probe, and is restored on
   package rollback;
7. the complete repository static validation passes;
8. the existing Git tree, schema-20 database, and unrelated service states are
   unchanged except for the local milestone commit and new Console service;
9. no push occurs before independent adversarial audit.

## Deferred roadmap

- 2Q: browser session and Controller client;
- 2R: operational dashboard;
- 2S: project lifecycle;
- 2T: Hermesfile lifecycle;
- 2U: objective lifecycle;
- 2V: orchestration and execution views;
- 2W: human review and Recovery;
- 2X: realtime events and reconciliation;
- 2Y: UI-only end-to-end and resilience;
- 2Z: beta release hardening.
