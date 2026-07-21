# Milestone 2H — bounded human review commands

Milestone 2H adds the first human review mutations to the local Controller API.
It implements only the non-executing subset of the existing Controller v1
review-command contract:

- `POST /api/v1/reviews/{review_id}/commands/acknowledge-debt`
- `POST /api/v1/reviews/{review_id}/commands/request-human-review`

Both commands require the local session cookie, a valid CSRF challenge and an
`Idempotency-Key`. They create a durable Controller operation, an immutable
review action, a redacted audit record and a metadata-only event. Command
reasons are never persisted; only `reason_present` is recorded.

`acknowledge-debt` is accepted only for a historical `PASS_WITH_DEBT` verdict.
`request-human-review` records an escalation without changing the historical
review verdict or scheduling work.

The contract command `rerun` remains explicitly unavailable in 2H because it
would schedule reviewer execution. This milestone also excludes integration,
Git operations, recovery decisions, shell execution, role configuration,
Hermesfiles and the Console.
