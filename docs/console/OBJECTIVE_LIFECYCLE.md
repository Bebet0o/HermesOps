# Console Objective Lifecycle

Status: **implemented by milestone 2U**

The `/objectives` route is an unprivileged same-origin client of the existing
Controller objective API. It presents the first bounded objective page, a
single-project creation form, an authoritative detail projection, and only the
pause, resume and cancel commands already implemented by the Controller.

Creation accepts the Controller fields `project_ids`, `title`, `description`,
`constraints`, `priority`, `not_before`, `max_parallel_tasks` and
`planning_max_attempts`. The Console does not invent policy, autonomy,
acceptance, sandbox override or approval fields that the current API does not
support.

Every mutation obtains a same-session CSRF token and a fresh cryptographically
random idempotency key. The resulting operation is read through the explicit
`/api/v1/operations/{operation_id}` route with at most three bounded reads.
Nothing is queued or persisted by the browser.

Available controls derive from `raw_state`:

- pause: `QUEUED`, `PLANNING`, `RUNNING`;
- resume: `PAUSED`;
- cancel: `QUEUED`, `PLANNING`, `RUNNING`, `PAUSE_REQUESTED`, `PAUSED`.

Pending cancellation and terminal states expose no command. Start, replan,
archive, delete, objective tasks and arbitrary operations remain outside the
Console proxy boundary.
