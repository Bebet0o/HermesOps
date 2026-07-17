# HermesOps notifications and operator control

Milestone 4C adds a durable notification outbox above the persistent objective
queue. Objective state changes, blocked runs and human approvals are collected
from SQLite, deduplicated and delivered with bounded retries.

## Delivery guarantees

Each notification has a unique deduplication key, a durable status, an attempt
history and a lease. A daemon crash leaves no ambiguous delivery ownership:
expired `DELIVERING` rows return to `RETRY`. Successful rows are never resent by
normal collection.

The file transport is always enabled and writes auditable JSON Lines to:

```text
/opt/docker/hermesops/runtime/notifications/delivered.jsonl
```

Telegram is optional and activates automatically when this root-owned-outside-
Git secret file exists:

```text
/opt/docker/hermesops/secrets/notifications.env
```

Use the interactive helper; do not paste a bot token into Git or a report:

```bash
/opt/docker/hermesops/repo/scripts/configure-hermesops-telegram.sh
```

## Operator CLI

```bash
/opt/docker/hermesops/repo/scripts/hermesopsctl queue --active
/opt/docker/hermesops/repo/scripts/hermesopsctl submit \
  --project PROJECT_ID \
  --text "Implement the requested change."
/opt/docker/hermesops/repo/scripts/hermesopsctl show OBJECTIVE_ID
/opt/docker/hermesops/repo/scripts/hermesopsctl pause OBJECTIVE_ID
/opt/docker/hermesops/repo/scripts/hermesopsctl resume OBJECTIVE_ID
/opt/docker/hermesops/repo/scripts/hermesopsctl cancel OBJECTIVE_ID
/opt/docker/hermesops/repo/scripts/hermesopsctl approvals
/opt/docker/hermesops/repo/scripts/hermesopsctl \
  resolve APPROVAL_ID ROLLBACK_SAFE
/opt/docker/hermesops/repo/scripts/hermesopsctl notifications --status
```

Approval resolution remains deterministic. The CLI delegates to the Recovery
Manager with an expected decision; it never edits approval rows directly.
