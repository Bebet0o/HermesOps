-- HermesOps milestone 2L: durable reviewer assignment workflow.
-- Existing review_results and reviewer_executions rows remain unchanged.

CREATE TABLE reviewer_assignments (
    assignment_id TEXT PRIMARY KEY CHECK (
        length(assignment_id) = 50
        AND substr(assignment_id, 1, 18) = 'review-assignment-'
        AND substr(assignment_id, 19) NOT GLOB '*[^0-9a-f]*'
    ),
    run_id TEXT NOT NULL,
    orchestration_attempt_id TEXT NOT NULL,
    assignment_number INTEGER NOT NULL CHECK (
        assignment_number BETWEEN 1 AND 1000
    ),
    role_id TEXT NOT NULL,
    source_profile TEXT NOT NULL CHECK (
        length(source_profile) BETWEEN 1 AND 128
    ),
    status TEXT NOT NULL CHECK (
        status IN ('ASSIGNED', 'CLAIMED', 'COMPLETED', 'FAILED', 'CANCELLED')
    ),
    assigned_by TEXT NOT NULL CHECK (
        length(assigned_by) BETWEEN 1 AND 200
    ),
    claim_owner TEXT CHECK (
        claim_owner IS NULL OR length(claim_owner) BETWEEN 1 AND 200
    ),
    review_execution_id TEXT UNIQUE,
    review_id TEXT UNIQUE,
    failure_code TEXT CHECK (
        failure_code IS NULL OR (
            length(failure_code) BETWEEN 3 AND 64
            AND failure_code = upper(failure_code)
            AND failure_code NOT GLOB '*[^A-Z0-9_]*'
        )
    ),
    assigned_at TEXT NOT NULL,
    claimed_at TEXT,
    heartbeat_at TEXT,
    finished_at TEXT,
    UNIQUE (run_id, assignment_number),
    UNIQUE (orchestration_attempt_id, assignment_number),
    FOREIGN KEY (run_id)
        REFERENCES runs(run_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (orchestration_attempt_id)
        REFERENCES orchestration_attempts(attempt_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (role_id)
        REFERENCES roles(role_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (review_execution_id)
        REFERENCES reviewer_executions(execution_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (review_id)
        REFERENCES review_results(review_id)
        ON DELETE RESTRICT,
    CHECK (
        (status = 'ASSIGNED'
            AND claim_owner IS NULL
            AND review_execution_id IS NULL
            AND review_id IS NULL
            AND failure_code IS NULL
            AND claimed_at IS NULL
            AND heartbeat_at IS NULL
            AND finished_at IS NULL)
        OR
        (status = 'CLAIMED'
            AND claim_owner IS NOT NULL
            AND review_execution_id IS NOT NULL
            AND review_id IS NULL
            AND failure_code IS NULL
            AND claimed_at IS NOT NULL
            AND heartbeat_at IS NOT NULL
            AND finished_at IS NULL)
        OR
        (status = 'COMPLETED'
            AND claim_owner IS NOT NULL
            AND review_execution_id IS NOT NULL
            AND review_id IS NOT NULL
            AND failure_code IS NULL
            AND claimed_at IS NOT NULL
            AND heartbeat_at IS NOT NULL
            AND finished_at IS NOT NULL)
        OR
        (status = 'FAILED'
            AND review_id IS NULL
            AND failure_code IS NOT NULL
            AND finished_at IS NOT NULL)
        OR
        (status = 'CANCELLED'
            AND review_id IS NULL
            AND failure_code IS NULL
            AND finished_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX idx_reviewer_assignments_one_active_run
    ON reviewer_assignments(run_id)
    WHERE status IN ('ASSIGNED', 'CLAIMED');

CREATE INDEX idx_reviewer_assignments_attempt
    ON reviewer_assignments(orchestration_attempt_id, assignment_number);

CREATE INDEX idx_reviewer_assignments_status
    ON reviewer_assignments(status, assigned_at);

CREATE TRIGGER reviewer_assignment_insert_policy_guard
BEFORE INSERT ON reviewer_assignments
WHEN NEW.status != 'ASSIGNED'
  OR NOT EXISTS (
        SELECT 1
        FROM roles
        WHERE role_id = NEW.role_id
          AND profile_name = NEW.source_profile
          AND role_kind = 'reviewer'
          AND workspace_mode = 'read_only'
          AND may_commit = 0
          AND may_push = 0
          AND network_enabled = 0
          AND enabled = 1
    )
BEGIN
    SELECT RAISE(ABORT, 'invalid reviewer assignment policy');
END;

CREATE TRIGGER reviewer_assignment_claim_link_guard
BEFORE UPDATE OF status, review_execution_id ON reviewer_assignments
WHEN OLD.status = 'ASSIGNED'
 AND NEW.status = 'CLAIMED'
 AND NOT EXISTS (
        SELECT 1
        FROM reviewer_executions
        WHERE execution_id = NEW.review_execution_id
          AND run_id = OLD.run_id
          AND role_id = OLD.role_id
          AND source_profile = OLD.source_profile
          AND review_id IS NULL
          AND finished_at IS NULL
    )
BEGIN
    SELECT RAISE(ABORT, 'invalid reviewer assignment claim link');
END;

CREATE TRIGGER reviewer_assignment_completion_link_guard
BEFORE UPDATE OF status, review_id ON reviewer_assignments
WHEN OLD.status = 'CLAIMED'
 AND NEW.status = 'COMPLETED'
 AND NOT EXISTS (
        SELECT 1
        FROM reviewer_executions
        WHERE execution_id = OLD.review_execution_id
          AND run_id = OLD.run_id
          AND role_id = OLD.role_id
          AND source_profile = OLD.source_profile
          AND review_id = NEW.review_id
          AND finished_at IS NOT NULL
    )
BEGIN
    SELECT RAISE(ABORT, 'invalid reviewer assignment completion link');
END;

CREATE TRIGGER reviewer_assignment_identity_immutable
BEFORE UPDATE OF
    assignment_id,
    run_id,
    orchestration_attempt_id,
    assignment_number,
    role_id,
    source_profile,
    assigned_by,
    assigned_at
ON reviewer_assignments
BEGIN
    SELECT RAISE(ABORT, 'reviewer assignment identity is immutable');
END;

CREATE TRIGGER reviewer_assignment_transition_guard
BEFORE UPDATE OF status ON reviewer_assignments
WHEN NOT (
       (OLD.status = 'ASSIGNED' AND NEW.status IN ('CLAIMED', 'FAILED', 'CANCELLED'))
    OR (OLD.status = 'CLAIMED' AND NEW.status IN ('COMPLETED', 'FAILED', 'CANCELLED'))
)
BEGIN
    SELECT RAISE(ABORT, 'invalid reviewer assignment transition');
END;

CREATE TRIGGER reviewer_assignment_terminal_immutable
BEFORE UPDATE ON reviewer_assignments
WHEN OLD.status IN ('COMPLETED', 'FAILED', 'CANCELLED')
BEGIN
    SELECT RAISE(ABORT, 'terminal reviewer assignment is immutable');
END;

CREATE TRIGGER reviewer_assignment_delete_guard
BEFORE DELETE ON reviewer_assignments
BEGIN
    SELECT RAISE(ABORT, 'reviewer assignment history is immutable');
END;

CREATE TRIGGER reviewer_assignment_no_replace_insert
BEFORE INSERT ON reviewer_assignments
WHEN EXISTS (
    SELECT 1
    FROM reviewer_assignments
    WHERE assignment_id = NEW.assignment_id
       OR (
            run_id = NEW.run_id
            AND assignment_number = NEW.assignment_number
       )
       OR (
            orchestration_attempt_id = NEW.orchestration_attempt_id
            AND assignment_number = NEW.assignment_number
       )
       OR (
            NEW.review_execution_id IS NOT NULL
            AND review_execution_id = NEW.review_execution_id
       )
       OR (
            NEW.review_id IS NOT NULL
            AND review_id = NEW.review_id
       )
)
BEGIN
    SELECT RAISE(ABORT, 'reviewer assignment conflicts are immutable');
END;

CREATE TRIGGER reviewer_assignment_timestamp_insert_guard
BEFORE INSERT ON reviewer_assignments
WHEN strftime('%Y-%m-%dT%H:%M:%fZ', NEW.assigned_at) IS NOT NEW.assigned_at
  OR (NEW.claimed_at IS NOT NULL AND
      strftime('%Y-%m-%dT%H:%M:%fZ', NEW.claimed_at) IS NOT NEW.claimed_at)
  OR (NEW.heartbeat_at IS NOT NULL AND
      strftime('%Y-%m-%dT%H:%M:%fZ', NEW.heartbeat_at) IS NOT NEW.heartbeat_at)
  OR (NEW.finished_at IS NOT NULL AND
      strftime('%Y-%m-%dT%H:%M:%fZ', NEW.finished_at) IS NOT NEW.finished_at)
BEGIN
    SELECT RAISE(ABORT, 'invalid reviewer assignment timestamp');
END;

CREATE TRIGGER reviewer_assignment_timestamp_update_guard
BEFORE UPDATE OF claimed_at, heartbeat_at, finished_at ON reviewer_assignments
WHEN (NEW.claimed_at IS NOT NULL AND
      strftime('%Y-%m-%dT%H:%M:%fZ', NEW.claimed_at) IS NOT NEW.claimed_at)
  OR (NEW.heartbeat_at IS NOT NULL AND
      strftime('%Y-%m-%dT%H:%M:%fZ', NEW.heartbeat_at) IS NOT NEW.heartbeat_at)
  OR (NEW.finished_at IS NOT NULL AND
      strftime('%Y-%m-%dT%H:%M:%fZ', NEW.finished_at) IS NOT NEW.finished_at)
BEGIN
    SELECT RAISE(ABORT, 'invalid reviewer assignment timestamp');
END;

INSERT INTO schema_migrations(version, applied_at)
VALUES (19, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

PRAGMA user_version = 19;
