CREATE TABLE objective_queue (
    objective_id TEXT PRIMARY KEY,
    objective TEXT NOT NULL,
    source TEXT NOT NULL CHECK (
        source IN ('AI', 'DECLARATIVE', 'TEST')
    ),
    status TEXT NOT NULL CHECK (
        status IN (
            'QUEUED',
            'PLANNING',
            'RUNNING',
            'PAUSE_REQUESTED',
            'PAUSED',
            'CANCEL_REQUESTED',
            'COMPLETED',
            'FAILED',
            'CANCELLED'
        )
    ),
    priority INTEGER NOT NULL DEFAULT 100
        CHECK (priority BETWEEN -1000 AND 1000),
    not_before TEXT NOT NULL,
    project_scope_json TEXT NOT NULL,
    max_parallel_tasks INTEGER NOT NULL DEFAULT 1
        CHECK (max_parallel_tasks BETWEEN 1 AND 16),
    planning_max_attempts INTEGER NOT NULL DEFAULT 3
        CHECK (planning_max_attempts BETWEEN 1 AND 5),
    planning_attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (planning_attempt_count BETWEEN 0 AND 5),
    plan_id TEXT UNIQUE,
    planner_execution_id TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    heartbeat_at TEXT NOT NULL,
    finished_at TEXT,
    paused_at TEXT,
    last_error TEXT,
    FOREIGN KEY (plan_id)
        REFERENCES orchestration_plans(plan_id)
        ON DELETE SET NULL,
    FOREIGN KEY (planner_execution_id)
        REFERENCES orchestrator_executions(execution_id)
        ON DELETE SET NULL
);

CREATE INDEX idx_objective_queue_dispatch
    ON objective_queue(status, not_before, priority, created_at);

CREATE INDEX idx_objective_queue_plan
    ON objective_queue(plan_id);

CREATE TABLE objective_attempts (
    objective_attempt_id TEXT PRIMARY KEY,
    objective_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL
        CHECK (attempt_number BETWEEN 1 AND 5),
    status TEXT NOT NULL CHECK (
        status IN (
            'RUNNING',
            'COMPLETED',
            'FAILED',
            'ABANDONED',
            'CANCELLED'
        )
    ),
    executor_instance_id TEXT,
    planner_execution_id TEXT,
    plan_id TEXT,
    result_json TEXT NOT NULL DEFAULT '{}',
    failure_reason TEXT,
    started_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    finished_at TEXT,
    next_attempt_at TEXT,
    UNIQUE (objective_id, attempt_number),
    FOREIGN KEY (objective_id)
        REFERENCES objective_queue(objective_id)
        ON DELETE CASCADE,
    FOREIGN KEY (executor_instance_id)
        REFERENCES orchestrator_instances(instance_id)
        ON DELETE SET NULL,
    FOREIGN KEY (planner_execution_id)
        REFERENCES orchestrator_executions(execution_id)
        ON DELETE SET NULL,
    FOREIGN KEY (plan_id)
        REFERENCES orchestration_plans(plan_id)
        ON DELETE SET NULL
);

CREATE INDEX idx_objective_attempts_status
    ON objective_attempts(status, heartbeat_at);

CREATE TABLE objective_events (
    objective_event_id TEXT PRIMARY KEY,
    objective_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (objective_id)
        REFERENCES objective_queue(objective_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_objective_events_objective
    ON objective_events(objective_id, created_at);

INSERT INTO schema_migrations(version, applied_at)
VALUES (
    10,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
);

PRAGMA user_version = 10;
