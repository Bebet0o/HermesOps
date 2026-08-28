# Changelog

All notable changes to HermesOps are documented in this file.

## [Unreleased]

No unreleased feature work is planned under the HermesOps name. Future product
development continues in [Orchestra](https://github.com/Bebet0o/Orchestra).

## [0.2.0] - 2026-08-27

HermesOps 0.2.0 closes the HermesOps product generation. The repository remains
available as installable software and a historical reference. Future product
development continues in Orchestra, which inherits the complete HermesOps Git
history.

### Added

- **Public install foundation:** Debian 12 preflight, idempotent installer,
  static/runtime validation, conservative uninstall, secret scanning,
  worker-image export/import, upgrade backups, and systemd user services.
- **Architecture/API contracts (2A–2C):** Controller ownership and privilege
  boundaries, OpenAPI/AsyncAPI contracts, replayable-event design, persistence
  delta, architecture decisions, and a loopback Controller service.
- **Reads and commands (2D–2M):** authenticated redacted APIs for objectives,
  operations, executions, events, review, recovery, plans, DAGs, attempts, and
  reviewer assignments; bounded objective/human-review commands; durable event
  journal; WebSocket replay; browser sessions; and reviewer assignments.
- **Hermesfile v1 (2N):** strict executable YAML parsing, semantic validation,
  canonical JSON, source/canonical SHA-256 fingerprints, and machine schema.
- **Sandbox profile persistence (2O):** durable immutable source revisions and
  authenticated redacted profile reads.
- **Console Web Foundation (2P):** independent loopback static Console,
  deterministic build, hardened service on port 8788, and bounded probes.
- **Browser session/Controller client (2Q):** same-origin login, refresh,
  CSRF logout, capability reads, bounded proxy, and degraded states.
- **Operational Dashboard (2R):** bounded project, objective, attention, plan,
  review, recovery, reviewer-assignment, and portfolio summaries.
- **Project Lifecycle (2S):** project revisions/archive state; secure
  create/import, update, enable, disable, rescan, and archive; compatibility
  TOML; idempotency/audit; and Console ETag/`If-Match` handling.
- **Hermesfile Lifecycle (2T):** operations/audit, templates, non-persisting
  validation, optimistic create/update, immutable history, canonical/runtime
  projections, path comparison, redaction, and a Console editor.
- **Objective Lifecycle (2U):** Console list, create/detail, pause/resume/cancel,
  and bounded operation following over existing secure Controller contracts.

### Orchestration and reliability

- Added durable SQLite state, a persistent objective queue, validated DAG
  planning, bounded scheduling, project affinity, and restart reconciliation.
- Added transactional Git worktrees/clones, snapshots, isolated workers,
  independent read-only review, reviewed integration, deterministic recovery,
  Supervisor, notifications, human approvals, and project memory/history.
- Hardened container adoption/cleanup using positive ownership, immutable IDs,
  durable bindings, and audited image/mount/network/resource checks.
- Preserved one active writer per project and no automatic push.

### Lifecycle Stabilization (2V)

- Made objective lifecycle gates authoritative across scheduling, reservation,
  approvals, orchestration, and recovery.
- Serialized pause/cancel transitions at safe boundaries and closed deferred
  human-gate and restart races.
- Stabilized recovery of requested, paused, cancelled, and human-gated work.
- Prevented task reservation from bypassing objective or approval gates.

### Agent Runtime Foundation (2W)

- Introduced runtime-neutral `AgentRuntime`, requests/results/errors, sandbox
  context, and bounded failure vocabulary.
- Added `HermesRuntime` as the Hermes Agent adapter and deterministic
  `FakeRuntime`.
- Kept lifecycle, persistence, Git, review, approval, and Recovery in the
  control plane while moving backend invocation behind the runtime boundary.
- Added normalized failure projection and runtime injection seams.

### Runtime-neutral Execution (2X)

- Added request/role-bound `STARTED` and `HEARTBEAT` facts with strict order.
- Persisted liveness from control-plane receipt time, not runtime timestamps.
- Removed Hermes discovery details from the public sandbox contract and
  hardened generic ownership/adoption/cleanup.
- Preserved neutral identity in compatibility columns without migration.

### Model Provider (2Y)

- Added synchronous `ModelProvider`, typed requests/results/messages/errors,
  plus a deterministic fake.
- Added bounded non-streaming `OpenAICompatibleProvider` with strict endpoint,
  system TLS, disabled proxy discovery, refused redirects, byte ceilings, and
  exact response parsing.
- Normalized failures without exposing prompts, credentials, endpoints, bodies,
  or secondary exception details.

### First NativeRuntime (2Z)

- Added the first real `NativeRuntime`, composed with one injected provider and
  one fixed model ID.
- Mapped one prompt to one user message, preserved timeout, emitted `STARTED`,
  invoked one synchronous generation, and returned text for domain validation.
- Added explicit provider-to-runtime failure mapping and fail-closed handling.
- Preserved default `HermesRuntime`: no model router, role routing, registry,
  fallback, native worker pool, or autonomous multi-agent behavior was added.

### Security

- Kept credentials/secrets outside Git with restrictive permissions.
- Kept the host Docker socket away from workers via a sandbox engine.
- Added browser authentication, CSRF/origin controls, bounded I/O, idempotency,
  optimistic concurrency, immutable audit, and redacted projections.
- Made review read-only/network-disabled and recovery fail closed.

### Known limits

- Hermesfile does not build/activate/rollback images, bind secrets, or delete
  revisions.
- NativeRuntime is synchronous and not selected by the default control plane;
  it has no in-flight cancellation or blocked-call heartbeat.
- Detailed execution/review/event/administration/recovery actions are absent
  from the Console.

## [0.1.0-alpha]

The validated technical foundation established the first public installation
and core local operations pipeline. No historical date is assigned here.

### Added

- Debian 12 installer, preflight, validation, conservative uninstall, secret
  scanning, examples, worker-image export/import, and Apache License 2.0;
- declarative projects, SQLite state, isolated Hermes Agent gateway, sandbox
  engine, role fleet, Git transactions, controlled workers, independent review,
  integration, recovery, Supervisor, DAG orchestration, objectives, and durable
  notifications.

### Changed

- normalized the public version to `0.1.0-alpha`;
- made fresh installations start with zero registered projects;
- moved fixtures under `tests/fixtures/projects/`;
- documented the upstream WebUI as a compatibility interface.

### Fixed

- supported minimal Debian dependency installation and administrative paths;
- made `util-linux` explicit and static validation source-archive compatible;
- allowed missing `auth.json` while deferring AI checks;
- fixed user-systemd ordering and deterministic service verification.

### Security

- protected `auth.json` and `secrets/`, backed up divergent upgrades, kept
  generated secrets out of Git, and withheld the host Docker socket from
  workers.
