# ADR 0003: Hermes Agent Is Behind an Adapter

Status: **Accepted**
Date: 2026-07-18

## Context

Hermes Agent is the upstream AI execution engine used by HermesOps. Its
provider configuration, session protocol, output format, health behavior, and
future releases can change independently from HermesOps domain logic.

If objectives, tasks, reviews, and recovery directly depend on upstream
payloads, HermesOps becomes difficult to upgrade and impossible to test without
a live provider.

## Decision

The Controller accesses Hermes Agent only through a stable internal adapter.

The adapter normalizes:

- session creation;
- role/profile selection;
- prompts and context;
- streamed output;
- cancellation and timeout;
- usage;
- tool errors;
- model errors;
- transport errors;
- health.

Domain services consume normalized outcomes and never treat raw provider output
as authoritative state.

## Consequences

Positive:

- Hermes Agent upgrades are isolated;
- tests can use a deterministic fake adapter;
- a future alternate execution engine is possible;
- provider errors do not leak into domain schemas;
- review transport failures cannot become PASS.

Costs:

- adapter code must track upstream behavior;
- some upstream features may need explicit mapping before use;
- debugging requires correlation between Controller and Agent session IDs.

## Implementation status

Milestone 2W implements this decision as the runtime-neutral
`AgentRuntime.execute(RuntimeRequest) -> RuntimeResult` boundary. The planner,
worker execution, and reviewer depend on that boundary and receive a runtime at
their launch entry point. `HermesRuntime` is the transitional adapter that owns
the current Hermes CLI/container invocation, ephemeral profile mapping,
process supervision, completion-marker handling, timeout, and runtime error
normalization.

The successful result surface is intentionally limited to textual output. A
non-zero runtime exit is an execution error, never a successful result. Public
requests use one opaque logical runtime configuration identifier and one
runtime-neutral request identity. Sandboxed requests carry generic isolation
policy, a generic task binding, and an opaque precreated-sandbox handle. Hermes
container names,
ephemeral profile names, discovery labels, durable transcript paths, and
role-specific process completion mode are not public request fields. Existing
execution journal columns retain their schema for recovery compatibility but
store the neutral request identity.
Speculative cancellation callbacks and unused execution metadata are not
included in the 2W contract.

The control plane owns sandbox creation, network/read-only/resource policy,
pre/post audits, durable transcript persistence, Git integrity, and reviewer
immutability. The Hermes adapter owns the private translation from the opaque
handle to Hermes container reuse and profile mechanics. Runtime errors carry
partial textual output and a known process exit status so the control plane can
preserve historical diagnostics and journal semantics. Their stable kind is
encoded in the existing durable `failure_reason` text as
`runtime_error[<kind>]`, avoiding both provider leakage and a schema change.

The private Hermes adoption shim revalidates the full sandbox identity and the
effective sandbox policy immediately before reuse. Runtime outer containers
have explicit generic ownership labels. Recovery uses only positive ownership
proof: `NEW_GENERIC` labels or the exact `LEGACY_HERMES` labels, each combined
with coherent identity and durable execution binding. Names are classification
hints only and never authorize deletion.

The same rule applies before Recovery: sandbox name collisions fail closed,
and a worker baseline snapshot is not ownership. Worker/reviewer cleanup and
outer runtime stop/remove re-inspect the expected bindings and act only on the
verified full Docker ID. If that ID has disappeared, a same-name replacement is
never targeted.

This is the bounded execution subset required by current call sites. ADR items
without a current consumer, such as streamed usage and health normalization,
remain future extensions rather than speculative 2W contract surface.

The adapter does not own objective or task lifecycle, scheduling, SQLite
state, Git transactions, integration, approvals, retry or recovery policy, or
review verdict policy. Plan and review payloads remain untrusted domain input
and are validated by their existing control-plane code.

`FakeRuntime` is the deterministic test implementation. An alternate native
runtime is a future possibility, not an implementation delivered by 2W. The
current runtime is constructed through one centralized factory so future
selection does not enter domain launchers.

## Rejected alternatives

### Import Hermes Agent internals directly everywhere

Rejected because it couples all domain services to one upstream version.

### Store raw Agent responses as domain state

Rejected because model output is untrusted input requiring validation.

### Replace Hermes Agent as part of this decision

Rejected because HermesOps intentionally builds around the upstream engine
for the current product. The adapter permits a future alternative without
making that future runtime part of this decision.
