CREATE TABLE supervisor_instances (
    instance_id TEXT PRIMARY KEY,
    hostname TEXT NOT NULL,
    pid INTEGER NOT NULL CHECK (pid > 0),
    owner TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'STARTING',
            'RUNNING',
            'STOPPING',
            'STOPPED',
            'FAILED',
            'ABANDONED'
        )
    ),
    started_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    stopped_at TEXT,
    last_sweep_id TEXT,
    last_error TEXT
);

CREATE INDEX idx_supervisor_instances_status
    ON supervisor_instances(status, heartbeat_at);

CREATE TABLE supervisor_sweeps (
    sweep_id TEXT PRIMARY KEY,
    instance_id TEXT,
    controller_owner TEXT NOT NULL,
    trigger TEXT NOT NULL CHECK (
        trigger IN (
            'startup',
            'periodic',
            'manual',
            'test'
        )
    ),
    status TEXT NOT NULL CHECK (
        status IN (
            'RUNNING',
            'COMPLETED',
            'SKIPPED',
            'FAILED'
        )
    ),
    stale_seconds INTEGER NOT NULL
        CHECK (stale_seconds BETWEEN 30 AND 86400),
    services_healthy INTEGER NOT NULL
        CHECK (services_healthy IN (0, 1)),
    health_json TEXT NOT NULL DEFAULT '{}',
    active_runs_before INTEGER NOT NULL
        CHECK (active_runs_before >= 0),
    active_runs_after INTEGER
        CHECK (
            active_runs_after IS NULL
            OR active_runs_after >= 0
        ),
    recovered_runs INTEGER NOT NULL DEFAULT 0
        CHECK (recovered_runs >= 0),
    orphan_actions INTEGER NOT NULL DEFAULT 0
        CHECK (orphan_actions >= 0),
    result_json TEXT NOT NULL DEFAULT '{}',
    failure_reason TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    FOREIGN KEY (instance_id)
        REFERENCES supervisor_instances(instance_id)
        ON DELETE SET NULL
);

CREATE INDEX idx_supervisor_sweeps_started
    ON supervisor_sweeps(started_at);

CREATE INDEX idx_supervisor_sweeps_status
    ON supervisor_sweeps(status, started_at);

INSERT INTO schema_migrations(version, applied_at)
VALUES (
    8,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
);

PRAGMA user_version = 8;
