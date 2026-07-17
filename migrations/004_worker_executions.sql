CREATE TABLE worker_executions (
    execution_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    source_profile TEXT NOT NULL,
    runtime_profile TEXT NOT NULL UNIQUE,
    outer_container_name TEXT NOT NULL UNIQUE,
    sandbox_container_id TEXT,
    prompt_path TEXT NOT NULL UNIQUE,
    output_path TEXT NOT NULL UNIQUE,
    workspace_mode TEXT NOT NULL CHECK (
        workspace_mode IN ('write', 'read_only')
    ),
    network_enabled INTEGER NOT NULL
        CHECK (network_enabled IN (0, 1)),
    cpu_limit INTEGER NOT NULL
        CHECK (cpu_limit BETWEEN 1 AND 64),
    memory_mb INTEGER NOT NULL
        CHECK (memory_mb BETWEEN 512 AND 131072),
    mount_verified INTEGER NOT NULL DEFAULT 0
        CHECK (mount_verified IN (0, 1)),
    isolation_verified INTEGER NOT NULL DEFAULT 0
        CHECK (isolation_verified IN (0, 1)),
    exit_code INTEGER,
    result_json TEXT NOT NULL DEFAULT '{}',
    failure_reason TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    FOREIGN KEY (task_id)
        REFERENCES tasks(task_id)
        ON DELETE CASCADE,
    FOREIGN KEY (run_id)
        REFERENCES runs(run_id)
        ON DELETE CASCADE,
    FOREIGN KEY (role_id)
        REFERENCES roles(role_id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_worker_executions_run
    ON worker_executions(run_id, created_at);

CREATE INDEX idx_worker_executions_role
    ON worker_executions(role_id, created_at);

INSERT INTO schema_migrations(version, applied_at)
VALUES (
    4,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
);

PRAGMA user_version = 4;
