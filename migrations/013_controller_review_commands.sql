CREATE TABLE IF NOT EXISTS controller_review_operations (
    operation_id TEXT PRIMARY KEY CHECK (operation_id GLOB 'operation-[0-9a-f]*'),
    command_kind TEXT NOT NULL CHECK (
        command_kind IN ('review.acknowledge-debt', 'review.request-human-review')
    ),
    state TEXT NOT NULL CHECK (state IN ('SUCCEEDED', 'FAILED')),
    target_id TEXT NOT NULL,
    result_json TEXT NOT NULL,
    error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT,
    FOREIGN KEY (target_id) REFERENCES review_results(review_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS controller_review_idempotency (
    session_fingerprint TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method = 'POST'),
    route TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_status INTEGER,
    response_json TEXT,
    operation_id TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (session_fingerprint, key_hash),
    FOREIGN KEY (operation_id)
        REFERENCES controller_review_operations(operation_id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS controller_review_command_audit (
    audit_id TEXT PRIMARY KEY CHECK (audit_id GLOB 'audit-[0-9a-f]*'),
    operation_id TEXT NOT NULL UNIQUE,
    actor_type TEXT NOT NULL CHECK (actor_type = 'session'),
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (
        action IN ('acknowledge-debt', 'request-human-review')
    ),
    resource_type TEXT NOT NULL CHECK (resource_type = 'review'),
    resource_id TEXT NOT NULL,
    session_fingerprint TEXT NOT NULL,
    idempotency_key_hash TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome = 'SUCCEEDED'),
    reason_present INTEGER NOT NULL CHECK (reason_present IN (0, 1)),
    created_at TEXT NOT NULL,
    FOREIGN KEY (operation_id)
        REFERENCES controller_review_operations(operation_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (resource_id)
        REFERENCES review_results(review_id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS controller_review_actions (
    action_id TEXT PRIMARY KEY CHECK (action_id GLOB 'review-action-[0-9a-f]*'),
    review_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    command TEXT NOT NULL CHECK (
        command IN ('acknowledge-debt', 'request-human-review')
    ),
    reason_present INTEGER NOT NULL CHECK (reason_present IN (0, 1)),
    status TEXT NOT NULL CHECK (status = 'RECORDED'),
    created_at TEXT NOT NULL,
    UNIQUE (review_id, command),
    FOREIGN KEY (review_id) REFERENCES review_results(review_id) ON DELETE RESTRICT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_controller_review_operations_target
    ON controller_review_operations(target_id, created_at);
CREATE INDEX IF NOT EXISTS idx_controller_review_actions_run
    ON controller_review_actions(run_id, created_at);
CREATE INDEX IF NOT EXISTS idx_controller_review_audit_resource
    ON controller_review_command_audit(resource_id, created_at);

INSERT INTO schema_migrations(version, applied_at)
VALUES (13, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
PRAGMA user_version = 13;
