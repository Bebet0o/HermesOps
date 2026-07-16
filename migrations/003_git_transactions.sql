ALTER TABLE runs
ADD COLUMN branch_name TEXT;

ALTER TABLE runs
ADD COLUMN snapshot_id TEXT;

ALTER TABLE runs
ADD COLUMN transaction_owner TEXT;

ALTER TABLE runs
ADD COLUMN submitted_at TEXT;

CREATE TABLE snapshots (
    snapshot_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    run_id TEXT NOT NULL UNIQUE,
    base_commit TEXT NOT NULL,
    bundle_path TEXT NOT NULL UNIQUE,
    patch_path TEXT NOT NULL UNIQUE,
    status_path TEXT NOT NULL UNIQUE,
    refs_path TEXT NOT NULL UNIQUE,
    manifest_path TEXT NOT NULL UNIQUE,
    bundle_sha256 TEXT NOT NULL,
    patch_sha256 TEXT NOT NULL,
    status_sha256 TEXT NOT NULL,
    refs_sha256 TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0
        CHECK (verified IN (0, 1)),
    created_at TEXT NOT NULL,
    verified_at TEXT,
    FOREIGN KEY (project_id)
        REFERENCES projects(project_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (run_id)
        REFERENCES runs(run_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_snapshots_project_created
    ON snapshots(project_id, created_at);

CREATE INDEX idx_runs_transaction_owner
    ON runs(transaction_owner, status);

INSERT INTO schema_migrations(version, applied_at)
VALUES (
    3,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
);

PRAGMA user_version = 3;
