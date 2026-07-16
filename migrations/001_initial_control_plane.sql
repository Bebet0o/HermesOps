CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    repo_path TEXT NOT NULL UNIQUE,
    data_path TEXT NOT NULL UNIQUE,
    policy_id TEXT NOT NULL,
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    config_source TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'QUEUED',
            'SNAPSHOTTING',
            'RUNNING',
            'REVIEWING',
            'WAITING_HUMAN',
            'COMMITTING',
            'COMPLETED',
            'FAILED',
            'CANCELLED',
            'RECOVERING'
        )
    ),
    recovery_decision TEXT CHECK (
        recovery_decision IS NULL
        OR recovery_decision IN (
            'RESUME_SAFE',
            'ROLLBACK_SAFE',
            'BLOCK_HUMAN'
        )
    ),
    base_commit TEXT,
    result_commit TEXT,
    worktree_path TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    heartbeat_at TEXT,
    FOREIGN KEY (project_id)
        REFERENCES projects(project_id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'QUEUED',
            'RUNNING',
            'BLOCKED',
            'COMPLETED',
            'FAILED',
            'CANCELLED'
        )
    ),
    description TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    heartbeat_at TEXT,
    FOREIGN KEY (run_id)
        REFERENCES runs(run_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_locks (
    project_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    holder TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    FOREIGN KEY (project_id)
        REFERENCES projects(project_id)
        ON DELETE CASCADE,
    FOREIGN KEY (run_id)
        REFERENCES runs(run_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT,
    run_id TEXT,
    task_id TEXT,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (
        severity IN (
            'DEBUG',
            'INFO',
            'WARNING',
            'ERROR',
            'CRITICAL'
        )
    ),
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id)
        REFERENCES projects(project_id)
        ON DELETE SET NULL,
    FOREIGN KEY (run_id)
        REFERENCES runs(run_id)
        ON DELETE SET NULL,
    FOREIGN KEY (task_id)
        REFERENCES tasks(task_id)
        ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'PENDING',
            'APPROVED',
            'REJECTED',
            'EXPIRED',
            'CANCELLED'
        )
    ),
    question TEXT NOT NULL,
    options_json TEXT NOT NULL DEFAULT '[]',
    decision TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (run_id)
        REFERENCES runs(run_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS review_results (
    review_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK (
        verdict IN (
            'PASS',
            'PASS_WITH_DEBT',
            'FIX',
            'SECURITY',
            'PERFORMANCE',
            'ARCHITECTURE',
            'HUMAN'
        )
    ),
    summary TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id)
        REFERENCES runs(run_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_records (
    memory_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    source_run_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id)
        REFERENCES projects(project_id)
        ON DELETE CASCADE,
    FOREIGN KEY (source_run_id)
        REFERENCES runs(run_id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_project_status
    ON runs(project_id, status);

CREATE INDEX IF NOT EXISTS idx_runs_heartbeat
    ON runs(heartbeat_at);

CREATE INDEX IF NOT EXISTS idx_tasks_run_status
    ON tasks(run_id, status);

CREATE INDEX IF NOT EXISTS idx_tasks_heartbeat
    ON tasks(heartbeat_at);

CREATE INDEX IF NOT EXISTS idx_events_run_created
    ON events(run_id, created_at);

CREATE INDEX IF NOT EXISTS idx_events_project_created
    ON events(project_id, created_at);

CREATE INDEX IF NOT EXISTS idx_approvals_status
    ON approvals(status, created_at);

INSERT INTO schema_migrations(version, applied_at)
VALUES (
    1,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
);

PRAGMA user_version = 1;
