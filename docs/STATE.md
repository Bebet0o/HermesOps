# HermesOps state after milestone 3F

The deterministic Recovery Manager is now driven by an automatic,
single-instance systemd user Supervisor.

The service starts at boot through user lingering, waits for Docker,
the sandbox engine and Hermes Agent, then runs an immediate recovery/orphan
sweep followed by periodic sweeps. Every instance and sweep is durable in
SQLite. A killed Supervisor is restarted by systemd, and the next process
marks the interrupted instance `ABANDONED`.

The Supervisor never changes the Recovery Manager decision vocabulary and
does not run recovery while required core services are unhealthy.


3F v2 fixes the only failure observed during the first real Supervisor run.
systemd had already exposed a replacement MainPID, while the replacement
Python process had not yet completed its durable SQLite registration. The
milestone now waits, with a strict timeout, for the exact killed PID to become
`ABANDONED` and the exact replacement PID to become `RUNNING`.
