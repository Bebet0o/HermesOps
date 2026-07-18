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

## Rejected alternatives

### Import Hermes Agent internals directly everywhere

Rejected because it couples all domain services to one upstream version.

### Store raw Agent responses as domain state

Rejected because model output is untrusted input requiring validation.

### Replace Hermes Agent

Rejected because HermesOps intentionally builds around the upstream engine
rather than duplicating it.
