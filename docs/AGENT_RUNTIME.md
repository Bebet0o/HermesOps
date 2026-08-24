# Agent runtime boundary

HermesOps separates control-plane decisions from execution of a bounded AI
role. Planner, worker, and reviewer code create a runtime-neutral
`RuntimeRequest` and invoke the `AgentRuntime` contract. The returned text is
input to the existing domain validation; it is never treated
as authoritative lifecycle state by the runtime.

## Responsibilities

The control plane continues to own objectives, scheduling, task DAGs, SQLite
state, approvals, retries, recovery decisions, reviewer verdict policy, Git
transactions and integration, project registration, durable transcripts, and
sandbox policy. Worker and reviewer create and audit a generic sandbox before
execution. They decide its workspace, access mode, network policy, CPU, and
memory without encoding how any runtime discovers it. Plan JSON and reviewer
JSON are parsed and validated by their domain components after execution.

The runtime boundary owns one bounded role invocation: prompt delivery,
logical runtime-configuration selection, execution supervision, timeout,
completion detection, textual output, and a stable failure classification. A
returned `RuntimeResult` always denotes runtime success and therefore contains
only output text; non-zero process exits are `execution_failed` errors. The
same textual output field is available on a `RuntimeError` so the control plane
can persist partial diagnostics without giving the runtime a durable path. The
failure vocabulary is deliberately small:
unavailable runtime, failed execution, timeout, invalid result, and
cancellation.

The public request carries a typed role, prompt, opaque `runtime_config_id`,
neutral request identifier, timeout, completion marker, optional sandbox
facts, and optional control-plane polling callback. `RuntimeSandboxContext`
contains only an absolute workspace, image identity, CPU and memory limits,
read-only and network policy, the control-plane task identity, and an opaque
sandbox handle. The task identity is a generic authorization binding, not a
runtime discovery protocol. The context contains no Hermes, Compose, profile,
container-name, or discovery-label field.

The runtime has no durable transcript path. `HermesRuntime` captures output in
a private temporary file and returns it; the control plane persists success or
partial failure output to its internally derived journal path using a
no-follow open. This removes arbitrary path and symlink writes from the public
runtime contract and makes `FakeRuntime` and `HermesRuntime` obey the same
output semantics.

The existing database columns named `runtime_profile` and
`outer_container_name` remain unchanged for schema and recovery compatibility.
They now contain the same runtime-neutral request identity. That identity is
also the cleanup key consumed by the current adapter; launchers no longer
fabricate Hermes role/profile/container names.

## Implementations

`HermesRuntime` is the current transitional adapter. It maps the neutral
request to the existing Hermes Agent Compose/CLI command and preserves the
planner, worker, and reviewer limits, sandbox mounts, and ephemeral profiles.
Hermes-specific command construction and process management belong here. For
worker and reviewer requests it passes the opaque handle to the private Hermes
entrypoint. At the point of adoption, that entrypoint re-inspects and verifies
the exact full container ID, generic owner/task/request bindings, running
state, image identity, `/workspace` source and access mode, effective network
mode and attached networks, CPU/RAM/PID limits, non-privileged mode,
`no-new-privileges`, dropped capabilities, and runtime user. Any mismatch is a
hard refusal; there is no alternate discovery fallback. Hermes discovery
labels are neither created nor understood by worker or reviewer.

Outer containers created by the adapter carry
`hermesops-runtime-container=1` and a matching
`hermesops-runtime-request-id`. Recovery discovery uses positive labels, then
re-inspects identity and checks durable execution bindings. Nested cleanup has
a documented two-entry ownership allowlist: `NEW_GENERIC` requires
`hermesops-sandbox=1` plus coherent task/request labels and SQLite binding;
`LEGACY_HERMES` requires the historical `hermes-agent=1` label plus coherent
historical task/profile labels and SQLite binding. A Hermes-looking name alone
is never ownership and is ignored.

Sandbox names are used only for creation. A collision fails closed; worker and
reviewer never pre-delete the existing name. The worker's before/after Docker
snapshot is only a discovery signal: every cleanup candidate is re-inspected
and must match the generic owner, task, request, image, workspace and mount mode
before removal by its full immutable ID. Outer runtime IDs are captured while
the launched process is live, then re-inspected before stop or removal; there
is no same-name fallback if the original ID disappears.

Cleanup is best-effort across independent process, container, and profile
phases. A primary runtime error is preserved if cleanup also fails; cleanup
failures are recorded as bounded secondary error types. A cleanup failure after
otherwise successful execution is itself `execution_failed`. Invalid Hermes
profile YAML, including a non-mapping document root, is an `invalid_result`
because the adapter cannot construct its completion protocol.

Timeout and exceptional supervision paths terminate and reap the process while
the private capture file is still open, then recover partial output. The
control plane persists the stable kind in the existing `failure_reason` column
as `runtime_error[<kind>]: <message>`; no provider string and no schema change
is needed.

`FakeRuntime` returns configured deterministic outcomes without invoking a
process. It strictly validates outcome types and uses the same request,
sandbox handle, output, completion, and normalized-error contract. Tests use
it to exercise success, failure, timeout, invalid output, cancellation, real
worker Git checks, and real reviewer immutability checks at the runtime seam.

The default launch paths call the centralized `create_runtime` factory, while
each launch function also accepts an injected `AgentRuntime`. The factory is
the sole future configuration seam: adding and selecting another
implementation does not require edits to planner, worker, reviewer, scheduler,
integrator, or Recovery.

## Future direction

The boundary makes a future `NativeRuntime` possible without changing the
scheduler, planner/worker/reviewer domain logic, integrator, or Recovery. Such
an implementation receives generic policy and the opaque sandbox handle; it
does not need to emulate Hermes labels or profiles. Only the implementation and
a future configuration/factory selection are required. No native provider,
model router, or multi-model policy is implemented by milestone 2W.
