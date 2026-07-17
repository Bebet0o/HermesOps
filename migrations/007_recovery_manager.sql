CREATE TABLE recovery_executions (
    recovery_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    source_profile TEXT NOT NULL,
    controller_owner TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    observed_status TEXT NOT NULL CHECK (
        observed_status IN (
            'SNAPSHOTTING',
            'RUNNING',
            'REVIEWING',
            'WAITING_HUMAN',
            'COMMITTING',
            'RECOVERING',
            'FAILED'
        )
    ),
    decision TEXT NOT NULL CHECK (
        decision IN (
            'RESUME_SAFE',
            'ROLLBACK_SAFE',
            'BLOCK_HUMAN'
        )
    ),
    outcome TEXT NOT NULL CHECK (
        outcome IN (
            'ASSESSED',
            'RESUMED',
            'ROLLED_BACK',
            'BLOCKED',
            'FAILED'
        )
    ),
    evidence_sha256 TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    actions_json TEXT NOT NULL DEFAULT '[]',
    failure_reason TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    FOREIGN KEY (run_id)
        REFERENCES runs(run_id)
        ON DELETE CASCADE,
    FOREIGN KEY (role_id)
        REFERENCES roles(role_id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_recovery_executions_run
    ON recovery_executions(run_id, created_at);

CREATE INDEX idx_recovery_executions_decision
    ON recovery_executions(decision, outcome, created_at);

INSERT INTO schema_migrations(version, applied_at)
VALUES (
    7,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
);

PRAGMA user_version = 7;
