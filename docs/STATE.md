# HermesOps state after milestone 4C

HermesOps now exposes a persistent operator layer above the autonomous
objective queue. The Notifier watches durable objective events, controller
events and human approvals, creates deduplicated outbox entries and records
every delivery attempt.

The Notifier is a permanent systemd user service with an exclusive lock,
heartbeat, crash reconciliation and bounded retry/backoff. File delivery is
always available. Telegram delivery is direct, optional and secret-driven;
credentials are stored outside Git and are never required for controller
correctness.

`hermesopsctl` provides one consistent interface for objective submission,
queue inspection, pause, resume, cancellation, approval inspection, safe
approval resolution and notification status.
