CREATE TABLE IF NOT EXISTS controller_operations (
    operation_id TEXT PRIMARY KEY CHECK (
        operation_id GLOB 'operation-[0-9a-f]*'
        AND length(operation_id) = 42
    ),
    command_kind TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('SUCCEEDED', 'FAILED')),
    target_type TEXT NOT NULL CHECK (target_type = 'objective'),
    target_id TEXT NOT NULL,
    result_json TEXT NOT NULL DEFAULT '{}',
    error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS controller_idempotency (
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
        REFERENCES controller_operations(operation_id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS controller_command_audit (
    audit_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL UNIQUE,
    actor_type TEXT NOT NULL CHECK (actor_type = 'session'),
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL CHECK (resource_type = 'objective'),
    resource_id TEXT NOT NULL,
    session_fingerprint TEXT NOT NULL,
    idempotency_key_hash TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('SUCCEEDED', 'FAILED')),
    created_at TEXT NOT NULL,
    FOREIGN KEY (operation_id)
        REFERENCES controller_operations(operation_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_controller_operations_target
    ON controller_operations(target_type, target_id, created_at);
CREATE INDEX IF NOT EXISTS idx_controller_audit_resource
    ON controller_command_audit(resource_type, resource_id, created_at);

INSERT INTO schema_migrations(version, applied_at)
VALUES (12, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

PRAGMA user_version = 12;
