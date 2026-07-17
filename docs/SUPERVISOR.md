# HermesOps Supervisor and Watchdog

The Supervisor makes the deterministic Recovery Manager autonomous.

## Execution model

`hermesops-supervisor.service` is a persistent systemd user service running
as `trader`. User lingering is enabled once so the user manager starts during
boot without requiring an interactive login.

The service:

1. acquires an exclusive non-blocking file lock;
2. registers its process instance in SQLite;
3. waits for the host Docker daemon, `hermesops-sandbox-engine`, and
   `hermesops-agent` to become healthy;
4. performs an immediate startup sweep;
5. performs periodic sweeps using the configured interval;
6. records health, decisions, recovery counts, orphan cleanup and errors;
7. restarts automatically after a process crash.

## Fail-closed behavior

No recovery sweep runs while a required core service is unhealthy. The
Supervisor records a `SKIPPED` sweep and retries later. Recovery decisions
remain exclusively `RESUME_SAFE`, `ROLLBACK_SAFE`, and `BLOCK_HUMAN`, as
implemented by the deterministic Recovery Manager.

## Concurrency

`runtime/supervisor/supervisor.lock` is held for the whole daemon lifetime.
A second daemon or manual sweep exits with code 75 and performs no action.

## Configuration

`config/supervisor.toml` defines:

- periodic sweep interval;
- stale heartbeat threshold;
- startup health wait;
- health retry interval;
- Recovery Manager command timeout.

## Operations

```bash
systemctl --user status hermesops-supervisor.service
/opt/docker/hermesops/repo/scripts/hermesops-supervisor.py status
journalctl --user -u hermesops-supervisor.service
```


## Crash restart readiness

A replacement `MainPID` can become visible before Python completes its SQLite
registration. Restart validation therefore waits for both durable states:
the killed PID is `ABANDONED`, and the replacement PID is `RUNNING`.
