-- HermesOps milestone 2T: secure Hermesfile lifecycle commands.
-- Hermesfile source and canonical data remain owned by the existing
-- sandbox_profiles and immutable sandbox_profile_revisions tables.

CREATE TABLE controller_hermesfile_operations (
    operation_id TEXT PRIMARY KEY CHECK (
        length(operation_id) = 42
        AND substr(operation_id, 1, 10) = 'operation-'
        AND substr(operation_id, 11) NOT GLOB '*[^0-9a-f]*'
    ),
    command_kind TEXT NOT NULL CHECK (
        command_kind IN ('hermesfile.create', 'hermesfile.update')
    ),
    state TEXT NOT NULL CHECK (state IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
    target_id TEXT NOT NULL CHECK (
        length(target_id) = 40
        AND substr(target_id, 1, 8) = 'sandbox-'
        AND substr(target_id, 9) NOT GLOB '*[^0-9a-f]*'
    ),
    result_json TEXT NOT NULL DEFAULT '{}' CHECK (
        json_valid(result_json) AND json_type(result_json) = 'object'
    ),
    error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE controller_hermesfile_idempotency (
    session_fingerprint TEXT NOT NULL CHECK (length(session_fingerprint) = 32),
    key_hash TEXT NOT NULL CHECK (length(key_hash) = 64),
    method TEXT NOT NULL CHECK (method IN ('POST', 'PATCH')),
    route TEXT NOT NULL CHECK (length(route) BETWEEN 1 AND 512),
    request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
    response_status INTEGER,
    response_json TEXT CHECK (
        response_json IS NULL OR (
            json_valid(response_json) AND json_type(response_json) = 'object'
        )
    ),
    operation_id TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (session_fingerprint, key_hash),
    FOREIGN KEY (operation_id)
        REFERENCES controller_hermesfile_operations(operation_id)
        ON DELETE RESTRICT
);

CREATE TABLE controller_hermesfile_command_audit (
    audit_id TEXT PRIMARY KEY CHECK (
        length(audit_id) = 38
        AND substr(audit_id, 1, 6) = 'audit-'
        AND substr(audit_id, 7) NOT GLOB '*[^0-9a-f]*'
    ),
    operation_id TEXT NOT NULL UNIQUE,
    actor_type TEXT NOT NULL CHECK (actor_type = 'session'),
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (
        action IN ('hermesfile.create', 'hermesfile.update')
    ),
    resource_type TEXT NOT NULL CHECK (resource_type = 'sandbox_profile'),
    resource_id TEXT NOT NULL,
    session_fingerprint TEXT NOT NULL CHECK (length(session_fingerprint) = 32),
    idempotency_key_hash TEXT NOT NULL CHECK (length(idempotency_key_hash) = 64),
    request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
    outcome TEXT NOT NULL CHECK (outcome IN ('SUCCEEDED', 'FAILED')),
    created_at TEXT NOT NULL,
    FOREIGN KEY (operation_id)
        REFERENCES controller_hermesfile_operations(operation_id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_controller_hermesfile_operations_target
    ON controller_hermesfile_operations(target_id, created_at);

CREATE INDEX idx_controller_hermesfile_audit_resource
    ON controller_hermesfile_command_audit(resource_id, created_at);

CREATE TRIGGER controller_hermesfile_audit_update_guard
BEFORE UPDATE ON controller_hermesfile_command_audit
BEGIN
    SELECT RAISE(ABORT, 'controller Hermesfile audit is immutable');
END;

CREATE TRIGGER controller_hermesfile_audit_delete_guard
BEFORE DELETE ON controller_hermesfile_command_audit
BEGIN
    SELECT RAISE(ABORT, 'controller Hermesfile audit is immutable');
END;

CREATE TRIGGER controller_hermesfile_idempotency_delete_guard
BEFORE DELETE ON controller_hermesfile_idempotency
BEGIN
    SELECT RAISE(ABORT, 'controller Hermesfile idempotency is immutable');
END;

INSERT INTO schema_migrations(version, applied_at)
VALUES (22, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

PRAGMA user_version = 22;
