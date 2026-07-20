# Milestone 2G — secure objective commands

Milestone 2G introduces the first bounded Controller mutation surface. The
Console remains an unprivileged HTTP client and never writes SQLite directly.

Implemented routes:

- `POST /api/v1/auth/csrf`
- `POST /api/v1/objectives`
- `POST /api/v1/objectives/{objective_id}/commands/pause`
- `POST /api/v1/objectives/{objective_id}/commands/resume`
- `POST /api/v1/objectives/{objective_id}/commands/cancel`

Every mutation requires the local Controller session, an `Idempotency-Key`, a
same-session CSRF token, strict JSON and same-origin validation when an Origin
header is present. Idempotency state, synchronous operation projections and a
metadata-only audit trail are committed in the same SQLite transaction as the
objective mutation. Raw session values, idempotency keys, reasons and objective
contents are not written to the command audit tables.

The mutation adapter preserves the existing objective queue lifecycle. Freeform
Console submissions use the existing `AI` source and remain future-schedulable.
The installed-service probe creates an objective dated in 2099, pauses it and
cancels it before it is eligible for dispatch.

Not implemented in 2G: plan/start/replan/archive, approvals, recovery decisions,
project mutation, Git integration, role/model configuration or Console UI.
