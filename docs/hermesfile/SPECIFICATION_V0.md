# Hermesfile v0 Specification

Status: **Experimental design contract**
API version: `hermesops.dev/v0alpha1`
Kind: `SandboxProfile`
Machine schema: [`../../specs/hermesfile-v0.schema.json`](../../specs/hermesfile-v0.schema.json)

Hermesfile v0 is not executable in `v0.1.0-alpha`. This document defines the
contract to be implemented on the path to `v0.2.0-beta`.

## Purpose

A Hermesfile is one declarative source file describing a reproducibility-oriented HermesOps
sandbox profile.

It replaces manual archive handling from the operator's perspective, but it
does not eliminate container images internally.

```text
Hermesfile
    ↓ parse and validate
canonical sandbox specification
    ↓ compile
deterministic build plan
    ↓ build in dedicated sandbox engine
immutable image
    ↓ validate
versioned ready profile
    ↓ activate
temporary worker containers
```

## Design principles

Hermesfile v0 is:

- declarative;
- strict;
- versioned;
- safe by default;
- digest-pinned;
- independent from host paths;
- suitable for WebUI editing;
- compilable to an inspectable build plan;
- separable from logical HermesOps roles.

It is not:

- a Dockerfile pass-through;
- a shell script executed on the host;
- a place to store secrets;
- a project orchestration definition;
- a reviewer or recovery configuration;
- a replacement for project policy.

## File name

The conventional file name is:

```text
Hermesfile
```

Alternative profile files may use:

```text
Hermesfile.python
Hermesfile.cpp
Hermesfile.docs
```

The Console stores source text and profile metadata in the Controller. The
source format is YAML 1.2-compatible data validated against the JSON Schema.

## Top-level structure

```yaml
apiVersion: hermesops.dev/v0alpha1
kind: SandboxProfile

metadata:
  name: default-python
  displayName: Default Python Worker
  description: Reproducible Python development sandbox
  labels:
    language: python
    purpose: general

spec:
  base: {}
  build: {}
  workspace: {}
  runtime: {}
  network: {}
  security: {}
  mounts: []
  validation: {}
```

Unknown fields are rejected in v0.

## `apiVersion`

Required exact value:

```yaml
apiVersion: hermesops.dev/v0alpha1
```

Breaking source-format changes require a new API version.

## `kind`

Required exact value:

```yaml
kind: SandboxProfile
```

Future kinds may exist, but are not accepted by this schema.

## `metadata`

### `metadata.name`

Required stable profile name.

Rules:

- lowercase ASCII;
- starts with a letter or digit;
- may contain `-`;
- maximum 63 characters;
- immutable after first successful build.

Example:

```yaml
name: cpp-vulkan
```

### `metadata.displayName`

Optional operator-facing name, maximum 120 characters.

### `metadata.description`

Optional operator-facing description, maximum 1,000 characters.

### `metadata.labels`

Optional string-to-string metadata.

Labels do not grant permissions.

## `spec.base`

Required.

```yaml
base:
  image: debian
  tag: "12.10-slim"
  digest: sha256:0123456789abcdef...
```

### Immutable identity

`digest` is mandatory and must be a SHA-256 OCI image digest.

A mutable tag may be included for readability, but the digest is authoritative.

The builder must pull and verify:

```text
image:tag@sha256:digest
```

A tag resolving to a different digest fails validation.

### Allowed registries

Registry policy is not embedded as a secret in the Hermesfile.

The Controller evaluates project and global policy to determine whether the
registry is allowed.

## `spec.build`

Optional build customization.

```yaml
build:
  apt:
    packages:
      - git
      - ca-certificates
      - build-essential
    update: true

  python:
    interpreter: python3
    packages:
      - pytest==9.0.2
      - ruff==0.14.10

  node:
    packageManager: npm
    packages:
      - typescript@5.9.3

  environment:
    DEBIAN_FRONTEND: noninteractive

  steps:
    - name: verify-toolchain
      run:
        - python3
        - --version
```

### Reproducibility and build identity

The base image is immutable, but external package repositories can still
change. Package declarations must be version-pinned where the ecosystem
supports it, and production-quality builders should use repository snapshots
or lock metadata.

A Hermesfile alone does not guarantee byte-for-byte rebuilding forever. The
compiled resolution record and resulting image digest are the authoritative
execution identity.

The compiled build record stores:

- canonical Hermesfile hash;
- base digest;
- resolved package versions;
- build engine version;
- generated build plan;
- image ID;
- image digest;
- validation results.

### Build steps

`steps[].run` is an argument vector, not a shell string.

Allowed:

```yaml
run:
  - cmake
  - --version
```

Not accepted in v0:

```yaml
run: "curl example | sh"
```

A future explicit shell step may be designed with stronger review and policy
gates, but arbitrary shell strings are excluded from v0.

### Build network

Build network access is controlled by `spec.network.build`.

The default is no network after required package-resolution phases. The builder
must make network use visible in the build record.

### Environment

Build environment values must be non-secret strings.

Secret references are forbidden during image build in v0. This prevents
credentials from being captured in layers or build logs.

## `spec.workspace`

Required.

```yaml
workspace:
  user: hermes
  group: hermes
  directory: /workspace
  sourceMode: worktree
```

### User

The worker must not run as root.

The builder assigns stable numeric UID/GID values according to the Controller's
sandbox ABI. The Hermesfile names the logical user and group; numeric mapping
is recorded in the build result.

### Directory

Must be an absolute container path.

It cannot be:

```text
/
 /root
 /proc
 /sys
 /dev
 /run/docker.sock
```

### Source modes

```text
worktree
clone
readOnly
```

- `worktree`: controlled writable project worktree;
- `clone`: isolated clone managed by HermesOps;
- `readOnly`: review or inspection use.

Project policy may narrow the allowed modes.

## `spec.runtime`

Required.

```yaml
runtime:
  cpu: 4
  memory: 8GiB
  pids: 512
  timeout: 2h
  stopGracePeriod: 30s
  tmpfsSize: 1GiB
```

### CPU

Positive number of logical CPU units.

### Memory

IEC quantity such as:

```text
512MiB
8GiB
```

### PIDs

Positive integer. Default and maximum are controlled by policy.

### Timeout

Duration using:

```text
30s
10m
2h
```

The Controller may impose a lower maximum.

### Concurrency

Concurrency is not defined in a Hermesfile.

Concurrency belongs to project, role, and Controller scheduling policy. One
image may back many containers, but Hermesfile does not authorize parallel
writers.

## `spec.network`

Required.

```yaml
network:
  runtime:
    mode: none
    allow: []

  build:
    mode: allowlist
    allow:
      - deb.debian.org
      - pypi.org
      - files.pythonhosted.org
```

Modes:

```text
none
allowlist
full
```

`full` requires global policy permission and usually operator confirmation.

Entries are DNS names or documented CIDR values. Credentials and URLs with
embedded tokens are forbidden.

Network policy is enforced by the sandbox infrastructure, not merely declared
to the worker.

## `spec.security`

Required.

```yaml
security:
  privileged: false
  noNewPrivileges: true
  readOnlyRoot: false

  capabilities:
    drop:
      - ALL
    add: []

  seccompProfile: default
  secrets: false
  allowDockerSocket: false
  allowDeviceAccess: false
```

Mandatory v0 invariants:

```text
privileged = false
noNewPrivileges = true
capabilities.drop contains ALL
capabilities.add is empty
allowDockerSocket = false
allowDeviceAccess = false
```

A project cannot weaken these invariants through the Console.

A future schema version may support narrowly scoped capabilities with explicit
policy and confirmation. v0 does not.

## `spec.mounts`

Optional list.

Allowed mount types:

```text
workspace
cache
tmpfs
artifact
```

Example:

```yaml
mounts:
  - name: build-cache
    type: cache
    target: /home/hermes/.cache
    readOnly: false

  - name: test-results
    type: artifact
    target: /artifacts
    readOnly: false
```

Hermesfile v0 does not accept a host source path.

Forbidden:

```yaml
source: /var/run/docker.sock
source: /etc
source: /home/operator
```

The Controller resolves logical mounts to controlled storage roots.

Mount targets must be absolute, non-overlapping paths and cannot cover
protected virtual filesystems.

## `spec.validation`

Required.

```yaml
validation:
  commands:
    - name: python
      run:
        - python3
        - --version
      timeout: 30s
      expectExitCode: 0

    - name: pytest
      run:
        - pytest
        - --version
      timeout: 30s
      expectExitCode: 0
```

A profile becomes `ready` only when all required validation commands pass.

Validation runs:

- in a fresh container;
- without project secrets;
- with runtime network policy;
- with the same user and security settings as task containers;
- with bounded logs and timeouts.

## Secret references

Hermesfile v0 contains no secret values.

Runtime secret access is a separate binding controlled by:

- project policy;
- role policy;
- operator configuration;
- Controller confirmation when required.

A future binding may reference:

```text
secret ID
target environment variable or file
allowed roles
allowed projects
expiration
```

The Hermesfile only declares:

```yaml
security:
  secrets: false
```

Hermesfile `v0alpha1` requires this value to remain `false`. A future schema
version may introduce explicit Controller-approved secret bindings; v0 does not
permit enabling them.

## Role binding

Logical roles and sandbox profiles remain separate.

Example future Controller mapping:

```yaml
roles:
  ops-worker-code:
    sandboxProfile: default-python

  ops-worker-tests:
    sandboxProfile: default-python

  ops-reviewer:
    sandboxProfile: read-only-review
```

The role controls behavior and permissions. The Hermesfile controls the
container environment. Neither replaces the other.

## Canonicalization

Before hashing, the Controller:

1. parses YAML into data;
2. validates against the schema;
3. applies explicit defaults;
4. sorts mapping keys;
5. normalizes quantities and durations;
6. serializes canonical JSON;
7. hashes the canonical bytes with SHA-256.

The source hash and canonical hash are both recorded.

Comments and formatting do not alter the canonical profile hash.

## Build lifecycle

```text
draft
→ validating
→ queued
→ building
→ testing
→ ready
```

Failure states:

```text
validation_failed
build_failed
test_failed
cancelled
```

Activation lifecycle:

```text
ready
→ active
→ inactive
→ archived
```

Only one active revision exists for a profile name.

Activation requires:

- successful schema validation;
- successful image build;
- successful validation commands;
- immutable image digest;
- policy approval;
- no unresolved critical diagnostics.

## Rollback

The sandbox manager retains:

- active image;
- previous known-good image;
- source revision;
- canonical specification;
- build evidence;
- validation evidence.

Rollback switches the active revision atomically.

A failed new build never replaces the active image.

Deleting the last known-good revision requires explicit confirmation.

## Diagnostics

Validation diagnostics use:

```json
{
  "severity": "error",
  "code": "immutable_digest_required",
  "path": "/spec/base/digest",
  "message": "Base image digest is required.",
  "documentation": "docs/hermesfile/SPECIFICATION_V0.md#immutable-identity"
}
```

Severities:

```text
info
warning
error
```

Errors block build.

Warnings are persisted and displayed before activation.

## Example

```yaml
apiVersion: hermesops.dev/v0alpha1
kind: SandboxProfile

metadata:
  name: python-project
  displayName: Python Project Worker
  description: Pinned Python worker with offline runtime network

spec:
  base:
    image: python
    tag: 3.12.10-slim-bookworm
    digest: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

  build:
    apt:
      update: true
      packages:
        - git
        - build-essential

    python:
      interpreter: python3
      packages:
        - pytest==9.0.2
        - ruff==0.14.10

  workspace:
    user: hermes
    group: hermes
    directory: /workspace
    sourceMode: worktree

  runtime:
    cpu: 4
    memory: 8GiB
    pids: 512
    timeout: 2h
    stopGracePeriod: 30s
    tmpfsSize: 1GiB

  network:
    build:
      mode: allowlist
      allow:
        - deb.debian.org
        - pypi.org
        - files.pythonhosted.org

    runtime:
      mode: none
      allow: []

  security:
    privileged: false
    noNewPrivileges: true
    readOnlyRoot: false
    capabilities:
      drop:
        - ALL
      add: []
    seccompProfile: default
    secrets: false
    allowDockerSocket: false
    allowDeviceAccess: false

  mounts:
    - name: python-cache
      type: cache
      target: /home/hermes/.cache
      readOnly: false

    - name: artifacts
      type: artifact
      target: /artifacts
      readOnly: false

  validation:
    commands:
      - name: python
        run:
          - python3
          - --version
        timeout: 30s
        expectExitCode: 0

      - name: pytest
        run:
          - pytest
          - --version
        timeout: 30s
        expectExitCode: 0
```

The digest in this example is a placeholder and is not valid for activation.

## Compatibility

- `v0alpha1` is experimental.
- Unknown fields are rejected.
- Implementations must preserve source text and parsed canonical data.
- A migration tool must produce a new source revision rather than silently
  rewriting the operator's file.
- The Console must show the schema version and diagnostics.
- A profile cannot be activated by a Controller that does not support its
  `apiVersion`.

## Explicit non-goals for v0

- arbitrary Dockerfile directives;
- privileged containers;
- host path mounts;
- Docker socket access;
- hardware device passthrough;
- added Linux capabilities;
- build-time secrets;
- orchestration DAG definitions;
- AI role prompts;
- project Git policy;
- distributed image builders.
