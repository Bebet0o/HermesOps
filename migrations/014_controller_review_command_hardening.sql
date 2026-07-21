CREATE TABLE _controller_review_hardening_guard (
    valid INTEGER NOT NULL CHECK (valid = 1)
);

INSERT INTO _controller_review_hardening_guard(valid)
SELECT CASE
    WHEN EXISTS (
        SELECT 1
        FROM controller_review_actions
        GROUP BY review_id
        HAVING COUNT(*) > 1
    ) THEN 0
    WHEN EXISTS (
        SELECT 1
        FROM controller_review_actions
        WHERE length(action_id) != 46
           OR substr(action_id, 1, 14) != 'review-action-'
           OR substr(action_id, 15) GLOB '*[^0-9a-f]*'
    ) THEN 0
    WHEN EXISTS (
        SELECT 1
        FROM controller_review_operations
        WHERE length(operation_id) != 42
           OR substr(operation_id, 1, 10) != 'operation-'
           OR substr(operation_id, 11) GLOB '*[^0-9a-f]*'
    ) THEN 0
    WHEN EXISTS (
        SELECT 1
        FROM controller_review_command_audit
        WHERE length(audit_id) != 38
           OR substr(audit_id, 1, 6) != 'audit-'
           OR substr(audit_id, 7) GLOB '*[^0-9a-f]*'
    ) THEN 0
    ELSE 1
END;

DROP TABLE _controller_review_hardening_guard;

ALTER TABLE controller_review_actions
    RENAME TO controller_review_actions_013;

CREATE TABLE controller_review_actions (
    action_id TEXT PRIMARY KEY CHECK (
        length(action_id) = 46
        AND substr(action_id, 1, 14) = 'review-action-'
        AND substr(action_id, 15) NOT GLOB '*[^0-9a-f]*'
    ),
    review_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    command TEXT NOT NULL CHECK (
        command IN ('acknowledge-debt', 'request-human-review')
    ),
    reason_present INTEGER NOT NULL CHECK (reason_present IN (0, 1)),
    status TEXT NOT NULL CHECK (status = 'RECORDED'),
    created_at TEXT NOT NULL,
    UNIQUE (review_id),
    FOREIGN KEY (review_id) REFERENCES review_results(review_id) ON DELETE RESTRICT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE RESTRICT
);

INSERT INTO controller_review_actions (
    action_id,
    review_id,
    run_id,
    command,
    reason_present,
    status,
    created_at
)
SELECT
    action_id,
    review_id,
    run_id,
    command,
    reason_present,
    status,
    created_at
FROM controller_review_actions_013;

DROP TABLE controller_review_actions_013;

CREATE INDEX idx_controller_review_actions_run
    ON controller_review_actions(run_id, created_at);

CREATE TRIGGER controller_review_operation_id_insert_guard
BEFORE INSERT ON controller_review_operations
WHEN length(NEW.operation_id) != 42
  OR substr(NEW.operation_id, 1, 10) != 'operation-'
  OR substr(NEW.operation_id, 11) GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'invalid controller review operation id');
END;

CREATE TRIGGER controller_review_operation_id_update_guard
BEFORE UPDATE OF operation_id ON controller_review_operations
WHEN length(NEW.operation_id) != 42
  OR substr(NEW.operation_id, 1, 10) != 'operation-'
  OR substr(NEW.operation_id, 11) GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'invalid controller review operation id');
END;

CREATE TRIGGER controller_review_audit_id_insert_guard
BEFORE INSERT ON controller_review_command_audit
WHEN length(NEW.audit_id) != 38
  OR substr(NEW.audit_id, 1, 6) != 'audit-'
  OR substr(NEW.audit_id, 7) GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'invalid controller review audit id');
END;

CREATE TRIGGER controller_review_audit_id_update_guard
BEFORE UPDATE OF audit_id ON controller_review_command_audit
WHEN length(NEW.audit_id) != 38
  OR substr(NEW.audit_id, 1, 6) != 'audit-'
  OR substr(NEW.audit_id, 7) GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'invalid controller review audit id');
END;

INSERT INTO schema_migrations(version, applied_at)
VALUES (14, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

PRAGMA user_version = 14;
