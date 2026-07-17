CREATE TABLE reviewer_executions (
    execution_id TEXT PRIMARY KEY,
    review_id TEXT UNIQUE,
    task_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    source_profile TEXT NOT NULL,
    runtime_profile TEXT NOT NULL UNIQUE,
    outer_container_name TEXT NOT NULL UNIQUE,
    sandbox_container_id TEXT,
    prompt_path TEXT NOT NULL UNIQUE,
    output_path TEXT NOT NULL UNIQUE,
    workspace_mode TEXT NOT NULL DEFAULT 'read_only'
        CHECK (workspace_mode = 'read_only'),
    network_enabled INTEGER NOT NULL DEFAULT 0
        CHECK (network_enabled = 0),
    cpu_limit INTEGER NOT NULL
        CHECK (cpu_limit BETWEEN 1 AND 64),
    memory_mb INTEGER NOT NULL
        CHECK (memory_mb BETWEEN 512 AND 131072),
    mount_verified INTEGER NOT NULL DEFAULT 0
        CHECK (mount_verified IN (0, 1)),
    isolation_verified INTEGER NOT NULL DEFAULT 0
        CHECK (isolation_verified IN (0, 1)),
    repository_unchanged INTEGER NOT NULL DEFAULT 0
        CHECK (repository_unchanged IN (0, 1)),
    decision TEXT CHECK (
        decision IS NULL OR decision IN (
            'APPROVE',
            'REJECT',
            'BLOCK_HUMAN'
        )
    ),
    verdict TEXT CHECK (
        verdict IS NULL OR verdict IN (
            'PASS',
            'PASS_WITH_DEBT',
            'FIX',
            'SECURITY',
            'PERFORMANCE',
            'ARCHITECTURE',
            'HUMAN'
        )
    ),
    exit_code INTEGER,
    result_json TEXT NOT NULL DEFAULT '{}',
    failure_reason TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    FOREIGN KEY (review_id)
        REFERENCES review_results(review_id)
        DEFERRABLE INITIALLY DEFERRED,
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

CREATE INDEX idx_reviewer_executions_run
    ON reviewer_executions(run_id, created_at);

CREATE INDEX idx_reviewer_executions_decision
    ON reviewer_executions(decision, created_at);

CREATE UNIQUE INDEX idx_review_results_one_per_run
    ON review_results(run_id);

INSERT INTO schema_migrations(version, applied_at)
VALUES (
    5,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
);

PRAGMA user_version = 5;
