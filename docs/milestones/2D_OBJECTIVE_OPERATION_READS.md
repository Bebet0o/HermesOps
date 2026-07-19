# Milestone 2D — Objective and operation read models

Milestone 2D adds the first business-level read models to the durable local
Controller API.

## Endpoints

Authenticated GET/HEAD routes:

- `/api/v1/objectives`;
- `/api/v1/objectives/{objective_id}`;
- `/api/v1/projects/{project_id}/objectives`;
- `/api/v1/operations/{operation_id}`.

The global objective list accepts `cursor`, `limit`, `project_id`, and `state`.
The project-scoped list accepts `cursor` and `limit`.

## Source of truth

Objectives are projected from the existing `objective_queue`,
`objective_events`, and linked `orchestration_plans` records. The API does not
create a parallel objective store and does not migrate or mutate the database.

Until a durable Controller operation table is introduced, objective planning
attempts are exposed as explicitly marked compatibility operations. Raw legacy
`result_json`, `failure_reason`, `last_error`, and event payloads are never
returned by these endpoints.

## State projection

Runtime states are mapped to the public contract without pretending that
requested transitions have completed:

- queued without a plan → `draft`;
- queued with a plan → `planned`;
- planning → `planning`;
- running → `running`;
- running with a blocked plan → `blocked`;
- pause requested → `running` plus `requested_transition=pause`;
- paused → `paused`;
- cancellation requested → `running` plus `requested_transition=cancel`;
- completed → `succeeded`;
- failed → `failed`;
- cancelled → `cancelled`.

## Pagination and isolation

Objective pagination uses an opaque, versioned, base64url cursor bound to its
project and state filters. Cursors from another filter set are rejected.
Project filtering uses SQLite JSON table functions against the canonical
multi-project scope instead of substring matching.

All database connections remain URI `mode=ro` with `PRAGMA query_only=ON`.
The service remains loopback-only, session-authenticated, and mutation-free.


## RC1 integration correction

The first server execution confirmed that all objective and operation
read-model tests passed. Global validation then exposed an integration
regression in the pre-existing durable-service probe fixture.

Milestone 2D intentionally extends Controller readiness so the service is not
reported ready unless the objective schema exists. The milestone 2C fixture
still created only `projects` and `schema_migrations`; its synthetic `/ready`
response therefore correctly became `503`.

RC1 updates that fixture with the actual table shapes used by the read models:

- `orchestration_plans`;
- `objective_queue`;
- `objective_attempts`;
- `objective_events`.

Production readiness remains strict. No migration, runtime write, or relaxed
health rule is introduced.


## RC3 standalone executable correction

RC2 passed every Controller API, objective/operation, durable-service, static,
secret, readiness, and base service probe check. The final objective probe
failed before sending HTTP because its executable imported `controller_api`
without first exposing the repository root.

RC3 applies the same self-bootstrap used by the main Controller executable:

```python
REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
```

The regression suite executes the probe from `/tmp` with `PYTHONPATH` removed,
including a request against a real temporary Controller HTTP server.
