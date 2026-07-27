# Changelog
- Added durable, immutable Hermesfile v1 sandbox profile source revisions and authenticated profile reads.

All notable changes to HermesOps will be documented in this file.

## [Unreleased]

- Add authenticated, redacted public reads for orchestration plans, DAG edges, attempts and reviewer assignments.
- Add executable Hermesfile v1 parsing, semantic validation, canonical JSON and deterministic source/canonical SHA-256 fingerprints.

### Added

- public Debian 12 installer, preflight, validation, and conservative
  uninstaller;
- local and CI secret scanning;
- examples for Hermes Agent, the temporary upstream WebUI, and notifications;
- reproducible worker-image export and verified import;
- Apache License 2.0;
- English public README covering architecture, installation, sandbox
  concepts, security, current limitations, and roadmap;
- explicit long-term direction for HermesOps Console and Hermesfiles in
  `v0.2.0-beta`.
- Milestone 2A architecture contracts for the future Controller, Console,
  replayable event stream, and Hermesfile sandbox profiles;
- machine-readable OpenAPI and JSON Schema design contracts;
- accepted architecture decisions covering state ownership, privilege
  boundaries, Agent adaptation, immutable images, replay, and confirmations.

### Fixed

- synchronized the complete Controller HTTP documentation with OpenAPI;
- preserved multi-project objectives and numeric queue priorities in API v1;
- added a machine-readable AsyncAPI WebSocket contract;
- removed forward-compatibility contradictions from response and event schemas;
- prohibited unsupported Hermesfile v0 secret eligibility;
- documented the persistence delta required before Controller writes.

- scanner-safe CSRF and Hermesfile schema identifiers that preserve the
  security contract without resembling tracked secret assignments;

### Changed

- public version normalized to `0.1.0-alpha`;
- a fresh public installation starts with zero registered projects;
- local project configurations are ignored and test fixtures live only
  under `tests/fixtures/projects/`;
- the current upstream WebUI is documented as a temporary compatibility
  interface rather than the final HermesOps product;
- `v0.1.0-alpha` is explicitly positioned as the validated technical
  foundation for future releases.

### Fixed

- minimal Debian preflight no longer fails before installable dependencies
  can be installed;
- `/usr/sbin` and `/sbin` are included when locating administrative
  commands;
- `util-linux` is an explicit installer dependency;
- local test fixtures are no longer accidentally tracked as active projects;
- static validation works from source archives without `.git` metadata;
- installation without `auth.json` defers AI-profile verification instead
  of failing;
- runtime layout validation accepts source-archive installations;
- user systemd services no longer create a `default.target` ordering cycle;
- the installer restarts user services deterministically and verifies that
  all three are active.

### Security

- explicit protection for `auth.json` and `secrets/`;
- backups before divergent upgrades;
- no generated secret is stored in the source repository;
- host Docker socket is not exposed to workers.

### Milestone 2P — Console Web Foundation

- add the independent loopback-only HermesOps Console shell;
- add a deterministic Python-only static build and manifest;
- add a dedicated hardened user service on port 8788;
- add bounded HTTP, build, install, probe, and adversarial test coverage;
- keep Controller integration and all business workflows disabled until later
  beta milestones.

### Milestone 2Q — Browser Session and Controller Client

- add a narrow same-origin Console gateway for browser session lifecycle and
  capability reads;
- add login, authoritative session refresh, CSRF-protected logout, and degraded
  Controller-unavailable states;
- keep passwords, cookies, CSRF values, and pending actions out of browser
  storage;
- add bounded proxy, origin, header, body, response, and live-probe coverage;
- keep business workflows and WebSocket events assigned to later milestones.

### Milestone 2R — Operational Dashboard

- add six explicit query-free read-only Controller collections to the Console gateway;
- add bounded project, objective, attention, plan and portfolio summaries;
- add partial-data, session-expiry, empty-state and manual-refresh handling;
- keep SQLite, host paths, browser storage, WebSocket and all mutations outside the Console;
- add deterministic dashboard source, proxy, build and live-probe coverage.

### Milestone 2S — Project Lifecycle

- add schema 21 project revisions, archive state, repository mode, operations, idempotency and immutable audit;
- add secure create/import, metadata update, enable, disable, rescan and archive Controller commands;
- preserve compatibility project TOML files while making Controller mutations authoritative;
- add a bounded same-origin Console project page with ETag/If-Match and fresh CSRF per intent;
- keep delete, remote/default-branch mutation, automatic push and Hermesfile editing unavailable.
