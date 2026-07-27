# Milestone 2S — Project Lifecycle

Status: **implementation candidate**

## Delivered boundary

Milestone 2S turns the existing project read contract into a secure Controller
and Console lifecycle without exposing host paths or SQLite.

- migration 021 adds durable project revisions, repository mode, default branch,
  sandbox profile linkage, archive state, project operations, idempotency, and
  immutable command audit;
- the Controller implements create, update, enable, disable, rescan, and archive;
- compatibility files under `config/projects.d` remain synchronized for the
  existing orchestrator and operator tools;
- repository modes are bounded to managed workspace paths: existing,
  initialize, or clone;
- the Console provides a same-origin list, create form, detail editor, and
  explicit command controls;
- project writes require authentication, CSRF, idempotency, strict JSON, and
  optimistic concurrency;
- active locks, runs, or objectives block disable and archive;
- all public project strings remain redacted projections.

## Deliberate exclusions

- project deletion;
- repository remote or default-branch mutation;
- automatic Git push;
- Hermesfile source editing or build/activation, owned by 2T;
- objective lifecycle, owned by 2U;
- generic Controller proxying or browser persistence.

## Validation contract

The milestone requires migration and registry compatibility tests, direct and
HTTP Controller lifecycle tests, Console source/proxy tests, deterministic build,
full static validation, production migration rehearsal, SQLite/config rollback,
and an independent adversarial audit before push.
