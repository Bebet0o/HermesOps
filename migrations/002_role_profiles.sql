CREATE TABLE IF NOT EXISTS roles (
    role_id TEXT PRIMARY KEY,
    profile_name TEXT NOT NULL UNIQUE,
    role_kind TEXT NOT NULL CHECK (
        role_kind IN (
            'orchestrator',
            'worker',
            'reviewer',
            'recovery'
        )
    ),
    description TEXT NOT NULL,
    reasoning_effort TEXT NOT NULL CHECK (
        reasoning_effort IN (
            'none',
            'minimal',
            'low',
            'medium',
            'high',
            'xhigh',
            'max',
            'ultra'
        )
    ),
    max_turns INTEGER NOT NULL CHECK (max_turns BETWEEN 1 AND 500),
    toolsets_json TEXT NOT NULL,
    skills_json TEXT NOT NULL,
    workspace_mode TEXT NOT NULL CHECK (
        workspace_mode IN (
            'none',
            'write',
            'read_only',
            'controller_only'
        )
    ),
    may_commit INTEGER NOT NULL CHECK (may_commit IN (0, 1)),
    may_push INTEGER NOT NULL CHECK (may_push IN (0, 1)),
    network_enabled INTEGER NOT NULL CHECK (network_enabled IN (0, 1)),
    cpu_limit INTEGER NOT NULL CHECK (cpu_limit BETWEEN 1 AND 64),
    memory_mb INTEGER NOT NULL CHECK (memory_mb BETWEEN 512 AND 131072),
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    config_source TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_roles_kind_enabled
    ON roles(role_kind, enabled);

INSERT INTO schema_migrations(version, applied_at)
VALUES (
    2,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
);

PRAGMA user_version = 2;
