# Milestone 2B — Read-only Controller API skeleton

## Status

Implementation milestone. This is the first executable slice of the future
HermesOps Controller API.

## Scope

Milestone 2B implements:

- a Python standard-library HTTP server;
- loopback-only binding;
- `/health`, `/ready`, and `/version` technical probes;
- authenticated reads for:
  - `/api/v1/system/health`;
  - `/api/v1/system/status`;
  - `/api/v1/system/capabilities`;
  - `/api/v1/projects`;
  - `/api/v1/projects/{project_id}`;
- read-only SQLite access using `mode=ro` and `PRAGMA query_only`;
- response envelopes and RFC 9457-style problem documents;
- request identifiers;
- cursor/limit project pagination;
- ETags for project resources;
- explicit feature flags that do not claim unimplemented functionality.

## Security boundary

The server refuses non-loopback bind addresses. Protected endpoints require a
cookie named `hermesops_session`.

For this implementation milestone, the expected cookie value is read from:

```text
/opt/docker/hermesops/secrets/controller-session
```

The file must:

- exist;
- have mode `0600`;
- contain between 32 and 4096 characters.

This is a deliberately small transitional authentication gate. It is not the
final login/session implementation defined by the complete Controller API
contract.

The technical probes are intentionally unauthenticated and return no secret or
project data.

## Read-only guarantee

No HTTP write method is implemented. `POST`, `PUT`, `PATCH`, and `DELETE`
return `405 Method Not Allowed`.

The SQLite adapter:

- opens the database with URI `mode=ro`;
- enables `PRAGMA query_only`;
- performs no migration;
- performs no registry synchronization;
- exposes no generic SQL endpoint.

## Persistence compatibility

The existing `projects` table does not yet contain every field in the future
API contract. The compatibility projection is:

| API field | Existing source |
| --- | --- |
| `id`, `slug` | `projects.project_id` |
| `name` | `projects.display_name` |
| `state` | `projects.enabled` |
| `policy_id` | `projects.policy_id` |
| `created_at` | `projects.registered_at` |
| `updated_at` | `projects.updated_at` |
| `default_branch` | safely read from the registered project TOML |
| `resource_revision` | deterministic projection of `config_hash` |
| `sandbox_profile_id` | `null` until future persistence exists |

The API does not modify the schema to conceal this delta.

## Running manually

Create the temporary session file without printing its value:

```bash
install -m 0600 /dev/null   /opt/docker/hermesops/secrets/controller-session

python3 - <<'PY' >   /opt/docker/hermesops/secrets/controller-session
import secrets
print(secrets.token_urlsafe(48))
PY

chmod 0600   /opt/docker/hermesops/secrets/controller-session
```

Then run:

```bash
cd /opt/docker/hermesops/repo

python3 scripts/hermesops-controller-api.py check

python3 scripts/hermesops-controller-api.py serve   --host 127.0.0.1   --port 8765
```

This milestone does not install or enable a systemd service. Service packaging
and durable session management belong to a later milestone.

## Non-goals

- project or objective writes;
- final authentication endpoints;
- WebSocket events;
- Hermesfile builds;
- Docker operations;
- Hermes Agent dispatch;
- Console code;
- database migrations;
- Internet exposure.


## Adversarial review hardening

The post-implementation review found and corrected the following issues before
merge:

- project responses exposed absolute host repository and data paths even
  though the Console does not require them;
- readiness and operator health endpoints ran `PRAGMA quick_check`, turning a
  frequent HTTP probe into an unbounded integrity scan;
- `GET`, `HEAD`, and disabled write methods could leave request bodies unread on
  HTTP/1.1 persistent connections;
- the threaded server had no per-connection timeout or concurrency bound;
- duplicate and percent-encoded session cookies were ambiguous;
- session files could be followed through symbolic links and were not checked
  for owner or hard links;
- arbitrary Host headers were accepted;
- query parsing had no field limit and silently accepted unknown parameters;
- SQLite read errors could escape as generic internal errors;
- API responses lacked several defensive browser-facing headers.

The corrected skeleton now:

- omits local filesystem paths from project API payloads;
- reserves `PRAGMA quick_check` for offline validation;
- closes connections whenever a request body cannot be safely consumed;
- limits concurrent request threads and applies socket timeouts;
- rejects ambiguous cookies and unsafe session files;
- validates loopback Host authorities;
- bounds and validates query parameters;
- maps SQLite failures to a stable `503 database_unavailable` problem;
- emits same-origin, frame, referrer, and content-type defenses.

These protections do not make the standard-library server Internet-facing.
Loopback-only binding remains mandatory.
