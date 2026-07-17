CREATE TABLE notifier_instances (
    instance_id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    hostname TEXT NOT NULL,
    pid INTEGER NOT NULL CHECK (pid > 0),
    version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('RUNNING', 'STOPPED', 'ABANDONED', 'FAILED')
    ),
    started_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    stopped_at TEXT,
    last_error TEXT
);

CREATE INDEX idx_notifier_instances_status
    ON notifier_instances(status, heartbeat_at);

CREATE TABLE notification_outbox (
    notification_id TEXT PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    event_kind TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (
        severity IN ('INFO', 'WARNING', 'CRITICAL')
    ),
    subject_type TEXT NOT NULL CHECK (
        subject_type IN ('OBJECTIVE', 'APPROVAL', 'RUN', 'SYSTEM', 'TEST')
    ),
    subject_id TEXT NOT NULL,
    channel TEXT NOT NULL CHECK (
        channel IN ('FILE', 'TELEGRAM')
    ),
    destination TEXT NOT NULL DEFAULT 'default',
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'PENDING',
            'DELIVERING',
            'RETRY',
            'DELIVERED',
            'DEAD_LETTER',
            'SUPPRESSED'
        )
    ),
    attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (attempt_count BETWEEN 0 AND 20),
    max_attempts INTEGER NOT NULL DEFAULT 5
        CHECK (max_attempts BETWEEN 1 AND 20),
    next_attempt_at TEXT NOT NULL,
    lease_owner TEXT,
    lease_expires_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    delivered_at TEXT
);

CREATE INDEX idx_notification_outbox_dispatch
    ON notification_outbox(
        status,
        next_attempt_at,
        severity,
        created_at
    );

CREATE INDEX idx_notification_outbox_subject
    ON notification_outbox(subject_type, subject_id, created_at);

CREATE TABLE notification_deliveries (
    delivery_id TEXT PRIMARY KEY,
    notification_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL CHECK (
        attempt_number BETWEEN 1 AND 20
    ),
    status TEXT NOT NULL CHECK (
        status IN ('DELIVERED', 'FAILED')
    ),
    transport_status TEXT,
    response_json TEXT NOT NULL DEFAULT '{}',
    failure_reason TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    UNIQUE (notification_id, attempt_number),
    FOREIGN KEY (notification_id)
        REFERENCES notification_outbox(notification_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_notification_deliveries_notification
    ON notification_deliveries(notification_id, attempt_number);

CREATE TABLE notification_cursors (
    source_name TEXT PRIMARY KEY,
    last_rowid INTEGER NOT NULL DEFAULT 0
        CHECK (last_rowid >= 0),
    updated_at TEXT NOT NULL
);

INSERT INTO schema_migrations(version, applied_at)
VALUES (
    11,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
);

PRAGMA user_version = 11;
