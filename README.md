# HermesOps

HermesOps 0.2.0 is the final complete generation of the product under the
HermesOps name.

> **Final HermesOps release**
>
> HermesOps 0.2.0 closes the HermesOps product generation. This repository
> remains available as installable software and as its historical record.
> Future development continues as
> [Orchestra](https://github.com/Bebet0o/Orchestra), which preserves the full
> HermesOps Git history.

HermesOps is a local project-operations platform that turns a complex objective
into durable, isolated, auditable, and recoverable work. Plans become persistent
task DAGs; specialized workers execute in isolated Git transactions; an
independent reviewer checks results; and the control plane records decisions in
durable state.

## Overview

HermesOps organizes work around projects, objectives, plans, persistent DAGs,
workers, independent review, human approval, and deterministic recovery. SQLite
holds lifecycle, execution, approval, event, audit, and project memory/history.
Git worktrees, clones, snapshots, and reviewed integration isolate changes.

HermesOps is not merely a wrapper around Hermes Agent. Hermes Agent remains a
supported execution backend; the Controller owns scheduling, lifecycle,
persistence, Git, review, approval, and recovery.

## What HermesOps can do

- manage project creation/import, updates, enable/disable, rescan, and archive;
- submit and track objectives, including pause, resume, and cancel at safe
  transaction boundaries;
- persist validated plans, DAG edges, attempts, executions, reviewer
  assignments, operations, audit, and replayable events in SQLite;
- plan objectives and run bounded worker/reviewer/integration workflows;
- isolate one active Git writer per project and integrate only reviewed local
  commits;
- recover interrupted work from durable evidence or request human approval;
- expose a loopback Controller API, CLI tools, and authenticated Console;
- validate, canonicalize, fingerprint, create, edit, and version Hermesfile v1;
- execute roles through `AgentRuntime`, using `HermesRuntime` or the real
  `NativeRuntime` implementation;
- call a synchronous OpenAI-compatible backend through `ModelProvider`.

## Architecture

```text
User
 |
 +-- HermesOps Console
 `-- CLI
       |
       v
 HermesOps Control Plane
       |
       +-- Projects
       +-- Objectives / plans / persistent DAG
       +-- Lifecycle
       +-- Planner / Workers / Reviewer / Recovery
       +-- Human approval
       +-- Git transactions / isolation
       `-- AgentRuntime
              +-- HermesRuntime
              |      `-- Hermes Agent
              `-- NativeRuntime
                     `-- ModelProvider
                            `-- OpenAI-compatible backend
```

The Controller and SQLite are authoritative. Browser state and LLM sessions are
not sources of transactional truth. The Orchestrator schedules the DAG; the
Supervisor and Recovery Manager reconcile interrupted work; Git and verified
snapshots retain repository evidence.

`HermesRuntime` remains the default control-plane path in 0.2.0.
`NativeRuntime` is real but is not selected by the default planner, worker, or
reviewer factory. A working HermesOps pipeline is therefore distinct from the
future native multi-agent Orchestra pipeline.

See [Architecture](docs/ARCHITECTURE.md),
[Control plane](docs/CONTROL_PLANE.md), and
[Orchestration](docs/ORCHESTRATION.md).

## Console and CLI

The Console is served on `127.0.0.1:8788`; the Controller API listens on
`127.0.0.1:8765`. Both are loopback-only. Remote access requires an
operator-managed SSH tunnel or secured reverse proxy.

Implemented Console surfaces are:

- operator login, session refresh, CSRF-protected logout, and degraded states;
- an operational dashboard covering projects, objectives, attention, plans,
  reviews, recoveries, and reviewer assignments;
- project creation/import, updates, enable, disable, rescan, and archive;
- Hermesfile validation, creation, editing, immutable history, previews, and
  revision comparison;
- objective creation, detail, pause, resume, and cancel.

Detailed executions, reviews, events, and administration remain placeholder
routes. Human review/recovery commands and detailed task/run views still need
the CLI or Controller API. The Console never opens SQLite, workspaces, Docker,
or host paths directly and stores no credentials in browser storage.

```bash
systemctl --user status hermesops-console.service
systemctl --user status hermesops-controller-api.service
systemctl --user status hermesops-orchestrator.service
curl --fail http://127.0.0.1:8788/health
```

Installed CLI examples:

```bash
/opt/docker/hermesops/repo/scripts/hermesops-objectives.py list
/opt/docker/hermesops/repo/scripts/hermesops-objectives.py status \
  --objective OBJECTIVE_ID
/opt/docker/hermesops/repo/scripts/hermesops-orchestrator.py list
```

## Hermesfile

A Hermesfile is strict YAML describing a reproducibility-oriented HermesOps
`SandboxProfile`. It is not a project configuration, objective, role,
scheduling policy, or permission grant.

The executable contract is `apiVersion: hermesops.dev/v1` and
`kind: SandboxProfile`. It describes a digest-pinned base image, declarative
build inputs, workspace identity, bounded runtime resources, network policy,
security, mounts, and validation commands. See the
[Hermesfile v1 specification](docs/hermesfile/SPECIFICATION_V1.md) and
[machine schema](specs/hermesfile-v1.schema.json).

```yaml
apiVersion: hermesops.dev/v1
kind: SandboxProfile
metadata:
  name: python-project
spec:
  base:
    registry: docker.io
    image: library/python
    tag: 3.12.10-slim-bookworm
    digest: sha256:REPLACE_WITH_AN_OCI_DIGEST
  build: {}
  workspace:
    user: hermes
    group: hermes
    directory: /workspace
    sourceMode: worktree
  runtime:
    cpu: 2
    memory: 4GiB
    pids: 256
    timeout: 1h
  network:
    build: {mode: none, allow: []}
    runtime: {mode: none, allow: []}
  security: {}
  mounts: []
  validation: {}
```

Validate locally without persisting:

```bash
python3 scripts/hermesops-hermesfile.py validate config/examples/Hermesfile
python3 scripts/hermesops-hermesfile.py fingerprint config/examples/Hermesfile
python3 scripts/hermesops-hermesfile.py canonicalize config/examples/Hermesfile
```

Strict parsing rejects unknown fields, duplicate keys, aliases, executable YAML
tags, shell command strings, secret-like values, and unbounded input.
Canonical JSON and source/canonical SHA-256 fingerprints are deterministic.

The Controller and Console provide templates, non-persisting validation,
creation, and editing. Updates require `If-Match` optimistic concurrency and
create immutable source revisions. Audit/events retain hashes and bounded
metadata, not raw source. Projects may reference sandbox profiles, but a
Hermesfile gains no project or objective authority.

HermesOps 0.2.0 does **not** build, pull, validate, activate, or roll back an
image from a Hermesfile. It does not bind secrets, delete revisions, or archive
profiles. In Orchestra, this concept evolves into **Orchestra Blueprint**.

## Runtime architecture

`AgentRuntime` separates one bounded AI invocation from control-plane policy.
Domain components validate plan, worker, and reviewer output; runtimes never
decide lifecycle, Git integration, approval, retry, or recovery.

- `HermesRuntime` is the adapter to Hermes Agent and the current default.
- `FakeRuntime` provides deterministic contract tests.
- `NativeRuntime` sends one prompt through one injected provider and fixed
  model ID, synchronously.
- `ModelProvider` normalizes results and failures.
- `OpenAICompatibleProvider` provides bounded, non-streaming chat completions
  with strict URLs, redirects disabled, system TLS, and proxy discovery off.

There is no ModelRouter, provider registry, role-to-model routing, fallback,
native worker pool, shared native context, parallel local 4B fleet, native 35B
judge, or autonomous Orchestra in HermesOps 0.2.0. See
[Agent runtime](docs/AGENT_RUNTIME.md) and
[Model provider](docs/MODEL_PROVIDER.md).

## Security and isolation

These are engineering boundaries, not an absolute certification:

- workers use a dedicated sandbox engine, not the host Docker socket;
- containers are adopted only after exact ownership, identity, mount, image,
  network, and resource inspection;
- workers write isolated Git clones/worktrees under an exclusive project lock;
- reviewers use a read-only workspace with remotes removed and network off;
- integration requires structured independent review and verified Git state;
- snapshots, bundles, patches, and SQLite evidence support recovery;
- ambiguity and corrupt evidence fail closed into human approval;
- secrets remain outside Git under `/opt/docker/hermesops/secrets` and
  `state/hermes-home/auth.json`;
- no workflow automatically pushes a project repository;
- resources, timeouts, mounts, network, and browser mutations are bounded.

Read [Security](docs/SECURITY.md), [Transactions](docs/TRANSACTIONS.md),
[Reviewers](docs/REVIEWERS.md), and [Recovery](docs/RECOVERY.md).

## Requirements

The public installer targets Debian 12 Bookworm on `amd64`, a non-root service
user with UID/GID `1000:1000`, fixed root `/opt/docker/hermesops`, systemd user
services, and loopback ports `8642`, `8765`, `8787`, and `8788`. Docker Engine
29.6.1 and Compose 5.3.0 are the tested versions.

## Installation

```bash
git clone https://github.com/Bebet0o/HermesOps.git
cd HermesOps
./preflight.sh
./install.sh
```

An immutable `v0.2.0` snapshot is intended for the final GitHub release, but it
does not exist during this pre-merge finalization. Do not check it out until
published. An existing OpenAI Codex credential can be supplied without printing
it:

```bash
./install.sh --auth-file /secure/path/auth.json
```

Without `auth.json`, AI profile verification and AI objectives are deferred.

### Worker sandbox image

The installer needs the image locked by `config/worker-sandbox.lock.toml`
(`hermesops-worker-sandbox:0.2`) and accepts a local archive:

```bash
./install.sh --offline \
  --auth-file /secure/path/auth.json \
  --worker-image-archive /secure/path/hermesops-worker-sandbox-0.2.tar.gz
```

The image ID must match the lock. The final release must publish
`hermesops-worker-sandbox-0.2.tar.gz` and
`hermesops-worker-sandbox-0.2.tar.gz.sha256`, or operators must supply an
equivalent archive.

## Quick start

After installation succeeds:

1. Read `/opt/docker/hermesops/secrets/controller-initial-password` as the
   service user and log into `http://127.0.0.1:8788` as `operator`.
2. Change the password (which removes the one-time file):

   ```bash
   HERMESOPS_ROOT=/opt/docker/hermesops \
     /opt/docker/hermesops/repo/scripts/hermesops-controller-operator.py \
     set-password
   ```

3. Create or import a disabled project in **Projects**, inspect it, then enable
   it.
4. Optionally create a sandbox profile in **Hermesfiles** and associate it
   through supported project metadata.
5. Create an objective in **Objectives** and follow it in the dashboard.
6. Pause, resume, or cancel only when the authoritative lifecycle allows it.
7. Use CLI/Controller operations for detailed review and recovery workflows.

CLI fallback:

```bash
printf '%s\n' 'Describe the desired outcome.' > /tmp/objective.txt
/opt/docker/hermesops/repo/scripts/hermesops-objectives.py submit \
  --objective-file /tmp/objective.txt --project PROJECT_ID --priority 100
/opt/docker/hermesops/repo/scripts/hermesops-objectives.py list
/opt/docker/hermesops/repo/scripts/hermesops-objectives.py pause \
  --objective OBJECTIVE_ID
/opt/docker/hermesops/repo/scripts/hermesops-objectives.py resume \
  --objective OBJECTIVE_ID
/opt/docker/hermesops/repo/scripts/hermesops-objectives.py cancel \
  --objective OBJECTIVE_ID
```

Lower numeric priority runs first. Pause/cancel become effective at a safe
transaction boundary; an active write is not killed merely for the request.

## Operations

```bash
./validate.sh --static
HERMESOPS_ROOT=/opt/docker/hermesops \
  /opt/docker/hermesops/repo/validate.sh --runtime
./uninstall.sh --user SERVICE_USER
```

The installer backs up Git and SQLite before divergent `--upgrade`. The default
uninstall disables services without deleting repositories, databases, secrets,
project data, or backups. Repository removal requires explicit
`--remove-repo --confirm REMOVE_REPO`.

## Known limitations

- NativeRuntime is not the default control-plane backend and cannot interrupt
  an in-flight synchronous provider call or emit a blocked-call heartbeat.
- ModelProvider has no streaming, tools, discovery, router, fallback, or retry.
- Hermesfile lifecycle does not build or activate images.
- Detailed execution, review, event, administration, and human recovery actions
  are absent from the Console.
- Deployment remains Debian 12/amd64 with a fixed root and loopback services.

## HermesOps → Orchestra

HermesOps began with Hermes Agent as its principal upstream engine. Across the
0.2 milestones, its control plane became runtime-neutral through `AgentRuntime`,
`HermesRuntime`, `NativeRuntime`, and `ModelProvider`. This enables evolution
toward true multi-agent and multi-model orchestration.

That generation continues as [Orchestra](https://github.com/Bebet0o/Orchestra),
which inherits the complete HermesOps Git history. Hermesfile evolves there
into **Orchestra Blueprint**. Native worker pools, parallel workers, shared
context, model routing, a native reviewer/judge, replanning, and multi-agent
recovery belong to Orchestra's roadmap, not HermesOps 0.2.0.

HermesOps 0.2.0 is the last feature release under this name. The repository
remains an installable historical reference; possible maintenance fixes do not
change where future product work occurs. Hermes Agent and `HermesRuntime`
remain supported and are not renamed.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Objectives](docs/OBJECTIVES.md)
- [Orchestration](docs/ORCHESTRATION.md)
- [Agent runtime](docs/AGENT_RUNTIME.md)
- [Model provider](docs/MODEL_PROVIDER.md)
- [Hermesfile v1](docs/hermesfile/SPECIFICATION_V1.md)
- [Console](docs/console/FOUNDATION.md)
- [Project lifecycle](docs/console/PROJECT_LIFECYCLE.md)
- [Objective lifecycle](docs/console/OBJECTIVE_LIFECYCLE.md)
- [Security](docs/SECURITY.md)
- [Recovery](docs/RECOVERY.md)

## License

HermesOps is licensed under the [Apache License 2.0](LICENSE).
