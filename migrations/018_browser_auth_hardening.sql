-- HermesOps milestone 2K adversarial hardening.
-- Preserve canonical authentication state and immutable replay/audit evidence.

CREATE TRIGGER controller_operator_credentials_validate_insert
BEFORE INSERT ON controller_operator_credentials
WHEN length(NEW.created_at) != 24
  OR length(NEW.updated_at) != 24
  OR (strftime('%Y-%m-%dT%H:%M:%fZ', NEW.created_at) IS NULL OR strftime('%Y-%m-%dT%H:%M:%fZ', NEW.created_at) != NEW.created_at)
  OR (strftime('%Y-%m-%dT%H:%M:%fZ', NEW.updated_at) IS NULL OR strftime('%Y-%m-%dT%H:%M:%fZ', NEW.updated_at) != NEW.updated_at)
  OR julianday(NEW.updated_at) < julianday(NEW.created_at)
BEGIN
    SELECT RAISE(ABORT, 'controller operator timestamp is invalid');
END;

CREATE TRIGGER controller_operator_credentials_validate_update
BEFORE UPDATE ON controller_operator_credentials
WHEN NEW.actor_id != OLD.actor_id
  OR NEW.username != OLD.username
  OR NEW.created_at != OLD.created_at
  OR length(NEW.updated_at) != 24
  OR (strftime('%Y-%m-%dT%H:%M:%fZ', NEW.updated_at) IS NULL OR strftime('%Y-%m-%dT%H:%M:%fZ', NEW.updated_at) != NEW.updated_at)
  OR julianday(NEW.updated_at) < julianday(NEW.created_at)
BEGIN
    SELECT RAISE(ABORT, 'controller operator update is invalid');
END;

CREATE TRIGGER controller_browser_sessions_validate_insert
BEFORE INSERT ON controller_browser_sessions
WHEN length(NEW.created_at) != 24
  OR length(NEW.expires_at) != 24
  OR (strftime('%Y-%m-%dT%H:%M:%fZ', NEW.created_at) IS NULL OR strftime('%Y-%m-%dT%H:%M:%fZ', NEW.created_at) != NEW.created_at)
  OR (strftime('%Y-%m-%dT%H:%M:%fZ', NEW.expires_at) IS NULL OR strftime('%Y-%m-%dT%H:%M:%fZ', NEW.expires_at) != NEW.expires_at)
  OR julianday(NEW.expires_at) <= julianday(NEW.created_at)
  OR (
      NEW.revoked_at IS NOT NULL
      AND (
          length(NEW.revoked_at) != 24
          OR (strftime('%Y-%m-%dT%H:%M:%fZ', NEW.revoked_at) IS NULL OR strftime('%Y-%m-%dT%H:%M:%fZ', NEW.revoked_at) != NEW.revoked_at)
          OR julianday(NEW.revoked_at) < julianday(NEW.created_at)
      )
  )
BEGIN
    SELECT RAISE(ABORT, 'controller browser session timestamp is invalid');
END;

CREATE TRIGGER controller_browser_sessions_revoke_only
BEFORE UPDATE ON controller_browser_sessions
WHEN NEW.session_id != OLD.session_id
  OR NEW.token_hash != OLD.token_hash
  OR NEW.actor_id != OLD.actor_id
  OR NEW.created_at != OLD.created_at
  OR NEW.expires_at != OLD.expires_at
  OR NEW.source_fingerprint != OLD.source_fingerprint
  OR NEW.user_agent_fingerprint != OLD.user_agent_fingerprint
  OR OLD.revoked_at IS NOT NULL
  OR NEW.revoked_at IS NULL
  OR length(NEW.revoked_at) != 24
  OR (strftime('%Y-%m-%dT%H:%M:%fZ', NEW.revoked_at) IS NULL OR strftime('%Y-%m-%dT%H:%M:%fZ', NEW.revoked_at) != NEW.revoked_at)
  OR julianday(NEW.revoked_at) < julianday(NEW.created_at)
BEGIN
    SELECT RAISE(ABORT, 'controller browser session update is forbidden');
END;

CREATE TRIGGER controller_auth_idempotency_validate_insert
BEFORE INSERT ON controller_auth_idempotency
WHEN length(NEW.created_at) != 24
  OR length(NEW.completed_at) != 24
  OR (strftime('%Y-%m-%dT%H:%M:%fZ', NEW.created_at) IS NULL OR strftime('%Y-%m-%dT%H:%M:%fZ', NEW.created_at) != NEW.created_at)
  OR (strftime('%Y-%m-%dT%H:%M:%fZ', NEW.completed_at) IS NULL OR strftime('%Y-%m-%dT%H:%M:%fZ', NEW.completed_at) != NEW.completed_at)
  OR julianday(NEW.completed_at) < julianday(NEW.created_at)
BEGIN
    SELECT RAISE(ABORT, 'controller auth idempotency timestamp is invalid');
END;

CREATE TRIGGER controller_auth_idempotency_no_replace_insert
BEFORE INSERT ON controller_auth_idempotency
WHEN EXISTS (
    SELECT 1 FROM controller_auth_idempotency
    WHERE namespace = NEW.namespace AND key_hash = NEW.key_hash
)
BEGIN
    SELECT RAISE(ABORT, 'controller auth idempotency replacement is forbidden');
END;

CREATE TRIGGER controller_auth_idempotency_immutable_update
BEFORE UPDATE ON controller_auth_idempotency
BEGIN
    SELECT RAISE(ABORT, 'controller auth idempotency is immutable');
END;

CREATE TRIGGER controller_auth_idempotency_immutable_delete
BEFORE DELETE ON controller_auth_idempotency
BEGIN
    SELECT RAISE(ABORT, 'controller auth idempotency is immutable');
END;

CREATE TRIGGER controller_auth_audit_validate_insert
BEFORE INSERT ON controller_auth_audit
WHEN length(NEW.created_at) != 24
  OR (strftime('%Y-%m-%dT%H:%M:%fZ', NEW.created_at) IS NULL OR strftime('%Y-%m-%dT%H:%M:%fZ', NEW.created_at) != NEW.created_at)
BEGIN
    SELECT RAISE(ABORT, 'controller auth audit timestamp is invalid');
END;

INSERT INTO schema_migrations(version, applied_at)
VALUES (18, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

PRAGMA user_version = 18;
