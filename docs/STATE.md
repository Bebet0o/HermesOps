# HermesOps state after milestone 3C

Milestone 3C adds the first independent AI review gate.

Validated lifecycle:

1. begin a transaction from a verified snapshot;
2. execute a real controlled worker in an isolated sandbox;
3. import the worker commit and submit the run to `REVIEWING`;
4. execute `ops-reviewer` in a separate read-only sandbox;
5. parse and validate a structured decision;
6. persist the review in `review_results` and execution evidence in
   `reviewer_executions`;
7. prove the reviewer changed no Git state;
8. perform a verified `ROLLBACK_SAFE` cleanup of the fixture.

The existing `review_results.verdict` taxonomy remains unchanged. The
human-facing decision is stored in `details_json` and `reviewer_executions`.


3C v2 fixes the initial reviewer heartbeat failure. The first 3C attempt
proved that the 3B worker path, transaction submission, and rollback remained
healthy; execution stopped before the reviewer AI call because v1 referenced
a nonexistent `runs.updated_at` column. v2 copies the proven 3B heartbeat
contract and adds pre-execution schema validation.


3C v3 follows a fully successful real reviewer execution (`APPROVE/PASS`).
The v2 milestone rolled back only because the inherited 3B foundation test
still required `PRAGMA user_version = 4` after migration 005. The worker test
now derives the expected schema version from the latest migration filename.
Reviewer documentation is installed before the automated validation that
asserts its presence.
