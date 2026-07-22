# Milestone 2M — Public orchestration reads

Milestone 2M exposes the durable orchestration graph to the future HermesOps
Console without exposing the Controller's internal execution payloads.

## Public resources

The authenticated read API implements:

```text
GET /api/v1/plans
GET /api/v1/plans/{plan_id}
GET /api/v1/plans/{plan_id}/tasks
GET /api/v1/plans/{plan_id}/dependencies
GET /api/v1/plans/{plan_id}/attempts
GET /api/v1/reviewer-assignments
GET /api/v1/reviewer-assignments/{assignment_id}
GET /api/v1/runs/{run_id}/reviewer-assignments
```

Collections use bounded, session-authenticated cursor pagination. Cursors are
bound to every active filter and become invalid after Controller session
rotation.

## Projection boundary

The API returns identifiers, state, timestamps, bounded counts, role metadata,
resource revisions and links between public resources. It never returns:

- plan JSON or full objective text;
- task instructions, acceptance criteria or completion markers;
- raw result objects, error messages or failure reasons;
- host paths, container names or executor instance identities;
- reviewer assignment owners or internal transaction run identifiers;
- prompts, logs, credentials or provider data.

Presence of a private error is represented only by bounded metadata. Historical
rows are projected according to their recorded state and are not rewritten.

## Compatibility

No database migration is required. Milestone 2M is read-only and does not add
plan, task, attempt or reviewer-assignment mutation routes. Existing objective,
execution, review, Recovery, event and browser-session contracts remain
unchanged.
