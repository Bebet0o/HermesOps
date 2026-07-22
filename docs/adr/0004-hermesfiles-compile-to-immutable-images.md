# ADR 0004: Hermesfiles Compile to Immutable Images

Status: **Accepted**
Date: 2026-07-18

## Context

The `v0.1.0-alpha` release distributes a prebuilt worker image archive. The
future product must let operators define and manage sandbox environments more
easily from HermesOps Console.

A text file cannot replace a container image at runtime, but it can become the
single source definition from which a verified image is built.

## Decision

A Hermesfile is a strict declarative source specification.

The sandbox manager:

1. validates it;
2. canonicalizes it;
3. compiles it to a build plan;
4. builds in the dedicated sandbox engine;
5. runs validation commands;
6. records image ID and immutable digest;
7. activates a versioned profile.

Execution always uses an immutable digest, never only a mutable tag.

Hermesfile v0 rejects privileged mode, host-path mounts, Docker socket access,
added Linux capabilities, and build-time secrets.

## Consequences

Positive:

- operators edit one understandable source file;
- images remain reproducible and auditable;
- the Console can show source, build plan, diagnostics, and history;
- failed builds cannot replace the last known-good image;
- offline export remains possible for backup or transfer.

Costs:

- a builder and schema migration system are required;
- package repositories can still introduce variability unless versions are
  pinned and resolutions recorded;
- advanced Dockerfile features are intentionally unavailable in v0.

## Rejected alternatives

### Store only image archives

Rejected as the long-term primary workflow because manual transfer is
cumbersome and source intent is opaque.

### Accept arbitrary Dockerfiles in the first version

Rejected because unrestricted build instructions are difficult to validate and
secure through a WebUI.

### Execute mutable tags

Rejected because the same tag can resolve to different content over time.

## Milestone 2N implementation boundary

Hermesfile v1 makes parsing, semantic validation, canonical JSON and
fingerprinting executable. It deliberately does not build, test, activate or
roll back images yet. Project registration, role policy, concurrency and Git
configuration remain separate sources of truth.
