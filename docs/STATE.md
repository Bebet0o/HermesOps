# HermesOps state after milestone 4B

HermesOps accepts persistent high-level objectives through a deterministic
SQLite queue. Each objective records priority, project scope, earliest dispatch
time, planning attempts, linked plan, control requests and a complete event
history.

The permanent Orchestrator applies one global priority order across AI and
declarative work, limits active objectives and tasks independently, and keeps
one project-bound task at a time across all plans. Pause and cancellation are
fail-safe and wait for running transactions to reach a safe boundary.

Planning is asynchronous so normal task scheduling and heartbeats continue
while GPT-5.6 Sol creates a validated DAG. Daemon restart marks interrupted
planning attempts ABANDONED, removes unfinished planner containers, and retries
within the durable attempt budget.


4B v2 removes the obsolete assumption that every controlled worker uses the
same completion marker. Markers are task-scoped and validated by the worker
launcher. Foundation tests now verify the persisted `marker_found` evidence
instead of one historical literal marker.


4B v3 hardens validation against concurrent Supervisor sweeps. A temporary
`RUNNING` sweep is treated as an in-progress observation, not a failure. The
test waits for a terminal snapshot and remains fail-closed after a bounded
60-second deadline.


4B v4 makes inherited milestone evidence monotonic. The 4A cancelled AI audit
plan is located by its own objective contract and successful planner evidence,
not by global recency. New completed AI objectives therefore coexist with the
historical 4A proof.


4B v5 separates repository integrity from commit timing. Pre-commit validation
permits only the complete, exact set of milestone-owned changes; post-commit
validation requires the normal clean tree. This removes the impossible clean
assertion without weakening fail-closed repository protection.
