# Milestone 2D adversarial review

This review hardens the published objective and legacy-operation read
models without adding writes, migrations, or new public routes.

## Corrected defects

### Attempt ordering

Objective attempt identifiers are random hexadecimal identifiers. Selecting
the latest attempt with `MAX(objective_attempt_id)` is therefore not
chronological. The projection now selects the highest `attempt_number`,
with the identifier only as a deterministic tie-breaker.

### State-filter parity

Public state filters now use exactly the same rules as individual resource
projection. Pause and cancel requests remain `running` even when their plan
is blocked, and queued objectives use the joined plan record when deciding
between `draft` and `planned`.

### Cursor integrity

Objective cursors are authenticated with HMAC-SHA256 using the already
validated local Controller session. Unsigned, altered, or filter-mismatched
cursors are rejected with `invalid_cursor`. Session rotation invalidates
previously issued cursors.

### Resource revisions

Objective and legacy-operation revisions are now hashes of their complete
public projection rather than a small subset of state fields. Changes to
title, description, priority, executor identity, and other visible fields
therefore change the ETag even when heartbeat timestamps do not.

### Corrupt legacy data

Invalid objective and operation identifiers fail closed as projection
errors. Project-filtered reads safely skip unrelated rows containing
malformed JSON scope data rather than turning every project page into a
database failure.

## Regression coverage

The review adds tests for:

- chronological latest-attempt selection;
- list/detail operation consistency;
- transition and plan-state filter parity;
- unsigned and tampered cursor rejection;
- complete objective and operation ETag coverage;
- project-filter isolation from unrelated malformed JSON;
- invalid legacy identifier redaction;
- SQLite schema failure mapping;
- preservation of all existing read-only and service tests.
