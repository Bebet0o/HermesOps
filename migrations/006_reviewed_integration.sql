CREATE TABLE integration_executions (
    integration_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    review_id TEXT NOT NULL,
    review_execution_id TEXT NOT NULL,
    controller_owner TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (
        decision IN (
            'APPROVE',
            'REJECT',
            'BLOCK_HUMAN'
        )
    ),
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
    status TEXT NOT NULL CHECK (
        status IN (
            'PREPARED',
            'COMPLETED',
            'REJECTED',
            'BLOCKED',
            'FAILED'
        )
    ),
    base_commit TEXT NOT NULL,
    reviewed_commit TEXT NOT NULL,
    main_before TEXT NOT NULL,
    main_after TEXT NOT NULL,
    snapshot_verified INTEGER NOT NULL DEFAULT 0
        CHECK (snapshot_verified IN (0, 1)),
    review_current INTEGER NOT NULL DEFAULT 0
        CHECK (review_current IN (0, 1)),
    approval_id TEXT,
    details_json TEXT NOT NULL DEFAULT '{}',
    failure_reason TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    FOREIGN KEY (run_id)
        REFERENCES runs(run_id)
        ON DELETE CASCADE,
    FOREIGN KEY (review_id)
        REFERENCES review_results(review_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (review_execution_id)
        REFERENCES reviewer_executions(execution_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (approval_id)
        REFERENCES approvals(approval_id)
        ON DELETE SET NULL
);

CREATE INDEX idx_integration_executions_run
    ON integration_executions(run_id, created_at);

CREATE INDEX idx_integration_executions_status
    ON integration_executions(status, created_at);

CREATE UNIQUE INDEX idx_integration_one_completed_per_run
    ON integration_executions(run_id)
    WHERE status = 'COMPLETED';

INSERT INTO schema_migrations(version, applied_at)
VALUES (
    6,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
);

PRAGMA user_version = 6;
