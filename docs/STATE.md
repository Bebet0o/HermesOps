# HermesOps state after milestone 4A

HermesOps now has a persistent multi-task DAG orchestrator. High-level
objectives can be transformed by the isolated `ops-orchestrator` planning role
into validated draft plans. Declarative plans are stored with canonical SHA-256
identity, explicit dependencies and bounded parallelism.

The daemon dispatches complete transaction -> worker -> reviewer -> integration
pipelines, blocks descendants after failure, and resumes safe interrupted work
after systemd restart. Existing project locks still guarantee one writer per
project, while independent controller tasks or different projects may execute
in parallel.


4A v2 aligns the Orchestrator user service with the portable hardening profile
already proven by the 3F Supervisor. Service readiness is no longer inferred
from `ActiveState` alone: HermesOps verifies a valid MainPID, the exclusive
lock, Supervisor health, and an exact SQLite `RUNNING` instance.

4A v3 classifies the observed `no SSE events` condition as a retryable provider
transport incident. Up to three bounded reviewer invocations may inspect the
same immutable result commit. Review decisions remain fail-closed: only a
successful structured reviewer execution reaches the integration gate.


4A v4 extends the deterministic recovery contract. `cleanup-orphans` treats
the `hermes-task-id` label of a SQLite `RUNNING` task as an authoritative live
reference. The milestone applies repeated concurrent cleanup pressure during
the real worker/reviewer pipeline.
