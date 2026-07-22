# Milestone 2N — Hermesfile v1

Milestone 2N turns the experimental Hermesfile design contract into an
executable, deterministic source contract.

## Scope

The milestone adds:

- `hermesops.dev/v1` and `SandboxProfile`;
- a strict JSON Schema;
- bounded YAML parsing with duplicate-key, alias and multi-document rejection;
- semantic security and path checks beyond JSON Schema;
- deterministic canonical JSON;
- source and canonical SHA-256 fingerprints;
- structured safe diagnostics;
- a local CLI;
- a valid example Hermesfile;
- regression and adversarial tests.

## Architecture boundary

A Hermesfile defines a sandbox profile only.

It does not define:

- a project or repository;
- Git integration policy;
- task concurrency;
- objectives or DAGs;
- role prompts;
- reviewer or Recovery behavior;
- secret values or bindings.

Project registration remains in `config/projects.d/*.toml`. Roles and policies
remain separate Controller-owned sources.

## Security boundary

The validator rejects:

- unknown fields;
- duplicate YAML keys, aliases, merge keys and multiple documents;
- non-UTF-8, oversized or deeply nested sources;
- root identities;
- protected or overlapping container paths;
- host source paths;
- privileged mode;
- added capabilities;
- Docker socket and device access;
- secret-like environment keys or values;
- shell pass-through commands;
- credential-bearing network destinations.

## Persistence and runtime

No migration is required. SQLite remains at schema version 19.

The milestone does not persist sources and does not build images. The public
Controller continues to report `hermesfile_builds=false`.

## Acceptance

Acceptance requires:

1. the example Hermesfile validates;
2. formatting-only changes preserve the canonical digest;
3. equivalent durations and quantities preserve the canonical digest;
4. the source digest still reflects byte-level source changes;
5. all security invariants fail closed;
6. diagnostics do not echo rejected secret-like values;
7. schema, implementation, capabilities and documentation remain aligned;
8. existing Controller and release regressions pass;
9. Git remains clean and no automatic push or merge occurs.
