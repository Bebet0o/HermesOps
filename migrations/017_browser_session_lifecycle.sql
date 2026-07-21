-- HermesOps milestone 2K: durable single-operator browser authentication.
-- Raw passwords and raw browser session tokens are never persisted.

CREATE TABLE controller_operator_credentials (
    actor_id TEXT PRIMARY KEY CHECK (actor_id = 'operator'),
    username TEXT NOT NULL UNIQUE CHECK (
        length(username) BETWEEN 3 AND 64
        AND username = lower(username)
        AND username NOT GLOB '*[^a-z0-9._-]*'
    ),
    password_algorithm TEXT NOT NULL CHECK (password_algorithm = 'scrypt'),
    password_salt TEXT NOT NULL CHECK (length(password_salt) BETWEEN 20 AND 32),
    password_digest TEXT NOT NULL CHECK (length(password_digest) BETWEEN 40 AND 64),
    scrypt_n INTEGER NOT NULL CHECK (scrypt_n BETWEEN 1024 AND 65536),
    scrypt_r INTEGER NOT NULL CHECK (scrypt_r BETWEEN 1 AND 16),
    scrypt_p INTEGER NOT NULL CHECK (scrypt_p BETWEEN 1 AND 4),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE controller_browser_sessions (
    session_id TEXT PRIMARY KEY CHECK (
        length(session_id) = 36
        AND substr(session_id, 1, 4) = 'ses_'
        AND substr(session_id, 5) NOT GLOB '*[^0-9a-f]*'
    ),
    token_hash TEXT NOT NULL UNIQUE CHECK (
        length(token_hash) = 64
        AND token_hash NOT GLOB '*[^0-9a-f]*'
    ),
    actor_id TEXT NOT NULL REFERENCES controller_operator_credentials(actor_id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint) = 32),
    user_agent_fingerprint TEXT NOT NULL CHECK (length(user_agent_fingerprint) = 32),
    CHECK (julianday(expires_at) > julianday(created_at)),
    CHECK (revoked_at IS NULL OR julianday(revoked_at) >= julianday(created_at))
);

CREATE INDEX idx_controller_browser_sessions_active
    ON controller_browser_sessions(token_hash, expires_at)
    WHERE revoked_at IS NULL;

CREATE TABLE controller_auth_idempotency (
    namespace TEXT NOT NULL CHECK (length(namespace) = 32),
    key_hash TEXT NOT NULL CHECK (length(key_hash) = 64),
    method TEXT NOT NULL CHECK (method = 'POST'),
    route TEXT NOT NULL CHECK (
        route IN ('/api/v1/auth/login', '/api/v1/auth/logout')
    ),
    request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
    response_status INTEGER NOT NULL CHECK (response_status IN (200, 401)),
    session_id TEXT REFERENCES controller_browser_sessions(session_id),
    created_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    PRIMARY KEY (namespace, key_hash),
    CHECK (
        (response_status = 200 AND session_id IS NOT NULL)
        OR (response_status = 401 AND session_id IS NULL)
    )
);

CREATE TABLE controller_auth_audit (
    auth_audit_id TEXT PRIMARY KEY CHECK (
        length(auth_audit_id) = 37
        AND substr(auth_audit_id, 1, 5) = 'auth_'
        AND substr(auth_audit_id, 6) NOT GLOB '*[^0-9a-f]*'
    ),
    action TEXT NOT NULL CHECK (action IN ('login', 'logout', 'password_change')),
    outcome TEXT NOT NULL CHECK (outcome IN ('success', 'failure', 'rate_limited')),
    actor_id TEXT,
    session_fingerprint TEXT CHECK (
        session_fingerprint IS NULL OR length(session_fingerprint) = 32
    ),
    username_fingerprint TEXT CHECK (
        username_fingerprint IS NULL OR length(username_fingerprint) = 32
    ),
    source_fingerprint TEXT CHECK (
        source_fingerprint IS NULL OR length(source_fingerprint) = 32
    ),
    request_id TEXT NOT NULL CHECK (length(request_id) BETWEEN 8 AND 128),
    created_at TEXT NOT NULL
);

CREATE INDEX idx_controller_auth_audit_source_time
    ON controller_auth_audit(source_fingerprint, created_at);
CREATE INDEX idx_controller_auth_audit_actor_time
    ON controller_auth_audit(actor_id, created_at);

CREATE TRIGGER controller_auth_audit_no_replace_insert
BEFORE INSERT ON controller_auth_audit
WHEN EXISTS (
    SELECT 1
    FROM controller_auth_audit
    WHERE auth_audit_id = NEW.auth_audit_id
)
BEGIN
    SELECT RAISE(ABORT, 'controller auth audit replacement is forbidden');
END;

CREATE TRIGGER controller_auth_audit_immutable_update
BEFORE UPDATE ON controller_auth_audit
BEGIN
    SELECT RAISE(ABORT, 'controller auth audit is immutable');
END;

CREATE TRIGGER controller_auth_audit_immutable_delete
BEFORE DELETE ON controller_auth_audit
BEGIN
    SELECT RAISE(ABORT, 'controller auth audit is immutable');
END;

INSERT INTO schema_migrations(version, applied_at)
VALUES (17, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

PRAGMA user_version = 17;
