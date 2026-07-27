-- HermesOps milestone 2S: secure project lifecycle persistence.
-- Legacy project TOML files remain compatibility sources. The Controller owns
-- all new HTTP mutations and keeps the TOML projection synchronized.

ALTER TABLE projects ADD COLUMN default_branch TEXT NOT NULL DEFAULT 'unknown'
    CHECK (length(default_branch) BETWEEN 1 AND 255);
ALTER TABLE projects ADD COLUMN sandbox_profile_id TEXT
    CHECK (sandbox_profile_id IS NULL OR length(sandbox_profile_id) BETWEEN 1 AND 63);
ALTER TABLE projects ADD COLUMN archived INTEGER NOT NULL DEFAULT 0
    CHECK (archived IN (0, 1));
ALTER TABLE projects ADD COLUMN repository_mode TEXT NOT NULL DEFAULT 'existing'
    CHECK (repository_mode IN ('clone', 'existing', 'initialize'));
ALTER TABLE projects ADD COLUMN resource_revision INTEGER NOT NULL DEFAULT 1
    CHECK (resource_revision >= 1);

CREATE TABLE controller_project_operations (
    operation_id TEXT PRIMARY KEY CHECK (
        length(operation_id) = 42
        AND substr(operation_id, 1, 10) = 'operation-'
        AND substr(operation_id, 11) NOT GLOB '*[^0-9a-f]*'
    ),
    command_kind TEXT NOT NULL CHECK (
        command_kind IN (
            'project.create', 'project.update', 'project.enable',
            'project.disable', 'project.rescan', 'project.archive'
        )
    ),
    state TEXT NOT NULL CHECK (state IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
    target_id TEXT NOT NULL CHECK (
        length(target_id) BETWEEN 2 AND 63
        AND target_id = lower(target_id)
        AND substr(target_id, 1, 1) GLOB '[a-z]'
        AND target_id NOT GLOB '*[^a-z0-9-]*'
    ),
    result_json TEXT NOT NULL DEFAULT '{}' CHECK (
        json_valid(result_json) AND json_type(result_json) = 'object'
    ),
    error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE controller_project_idempotency (
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
        REFERENCES controller_project_operations(operation_id)
        ON DELETE RESTRICT
);

CREATE TABLE controller_project_command_audit (
    audit_id TEXT PRIMARY KEY CHECK (
        length(audit_id) = 38
        AND substr(audit_id, 1, 6) = 'audit-'
        AND substr(audit_id, 7) NOT GLOB '*[^0-9a-f]*'
    ),
    operation_id TEXT NOT NULL UNIQUE,
    actor_type TEXT NOT NULL CHECK (actor_type = 'session'),
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (
        action IN (
            'project.create', 'project.update', 'project.enable',
            'project.disable', 'project.rescan', 'project.archive'
        )
    ),
    resource_type TEXT NOT NULL CHECK (resource_type = 'project'),
    resource_id TEXT NOT NULL,
    session_fingerprint TEXT NOT NULL CHECK (length(session_fingerprint) = 32),
    idempotency_key_hash TEXT NOT NULL CHECK (length(idempotency_key_hash) = 64),
    request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
    outcome TEXT NOT NULL CHECK (outcome IN ('SUCCEEDED', 'FAILED')),
    reason_present INTEGER NOT NULL DEFAULT 0 CHECK (reason_present IN (0, 1)),
    created_at TEXT NOT NULL,
    FOREIGN KEY (operation_id)
        REFERENCES controller_project_operations(operation_id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_controller_project_operations_target
    ON controller_project_operations(target_id, created_at);
CREATE INDEX idx_controller_project_audit_resource
    ON controller_project_command_audit(resource_id, created_at);

CREATE TRIGGER controller_project_audit_update_guard
BEFORE UPDATE ON controller_project_command_audit
BEGIN
    SELECT RAISE(ABORT, 'controller project audit is immutable');
END;

CREATE TRIGGER controller_project_audit_delete_guard
BEFORE DELETE ON controller_project_command_audit
BEGIN
    SELECT RAISE(ABORT, 'controller project audit is immutable');
END;

CREATE TRIGGER controller_project_idempotency_delete_guard
BEFORE DELETE ON controller_project_idempotency
BEGIN
    SELECT RAISE(ABORT, 'controller project idempotency is immutable');
END;

CREATE TRIGGER project_resource_revision_guard
BEFORE UPDATE ON projects
WHEN (
       NEW.display_name IS NOT OLD.display_name
    OR NEW.repo_path IS NOT OLD.repo_path
    OR NEW.data_path IS NOT OLD.data_path
    OR NEW.policy_id IS NOT OLD.policy_id
    OR NEW.enabled IS NOT OLD.enabled
    OR NEW.config_source IS NOT OLD.config_source
    OR NEW.config_hash IS NOT OLD.config_hash
    OR NEW.default_branch IS NOT OLD.default_branch
    OR NEW.sandbox_profile_id IS NOT OLD.sandbox_profile_id
    OR NEW.archived IS NOT OLD.archived
    OR NEW.repository_mode IS NOT OLD.repository_mode
) AND NEW.resource_revision != OLD.resource_revision + 1
BEGIN
    SELECT RAISE(ABORT, 'project resource revision must advance by one');
END;

CREATE TRIGGER project_resource_revision_stable_guard
BEFORE UPDATE ON projects
WHEN NOT (
       NEW.display_name IS NOT OLD.display_name
    OR NEW.repo_path IS NOT OLD.repo_path
    OR NEW.data_path IS NOT OLD.data_path
    OR NEW.policy_id IS NOT OLD.policy_id
    OR NEW.enabled IS NOT OLD.enabled
    OR NEW.config_source IS NOT OLD.config_source
    OR NEW.config_hash IS NOT OLD.config_hash
    OR NEW.default_branch IS NOT OLD.default_branch
    OR NEW.sandbox_profile_id IS NOT OLD.sandbox_profile_id
    OR NEW.archived IS NOT OLD.archived
    OR NEW.repository_mode IS NOT OLD.repository_mode
) AND NEW.resource_revision != OLD.resource_revision
BEGIN
    SELECT RAISE(ABORT, 'project resource revision changed without resource change');
END;

INSERT INTO schema_migrations(version, applied_at)
VALUES (21, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

PRAGMA user_version = 21;
