CREATE TABLE orchestrator_instances (
    instance_id TEXT PRIMARY KEY,
    hostname TEXT NOT NULL,
    pid INTEGER NOT NULL CHECK (pid > 0),
    owner TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'STARTING',
            'RUNNING',
            'STOPPED',
            'FAILED',
            'ABANDONED'
        )
    ),
    started_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    stopped_at TEXT,
    last_error TEXT
);

CREATE INDEX idx_orchestrator_instances_status
    ON orchestrator_instances(status, heartbeat_at);

CREATE TABLE orchestration_plans (
    plan_id TEXT PRIMARY KEY,
    objective TEXT NOT NULL,
    source TEXT NOT NULL CHECK (
        source IN ('AI', 'DECLARATIVE', 'TEST')
    ),
    planner_role_id TEXT NOT NULL DEFAULT 'orchestrator',
    status TEXT NOT NULL CHECK (
        status IN (
            'DRAFT',
            'READY',
            'RUNNING',
            'BLOCKED',
            'COMPLETED',
            'FAILED',
            'CANCELLED'
        )
    ),
    max_parallel_tasks INTEGER NOT NULL
        CHECK (max_parallel_tasks BETWEEN 1 AND 64),
    plan_sha256 TEXT NOT NULL CHECK (length(plan_sha256) = 64),
    plan_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    heartbeat_at TEXT,
    finished_at TEXT,
    last_error TEXT,
    FOREIGN KEY (planner_role_id)
        REFERENCES roles(role_id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_orchestration_plans_status
    ON orchestration_plans(status, created_at);

CREATE TABLE orchestrator_executions (
    execution_id TEXT PRIMARY KEY,
    plan_id TEXT,
    role_id TEXT NOT NULL,
    source_profile TEXT NOT NULL,
    outer_container_name TEXT NOT NULL UNIQUE,
    prompt_path TEXT NOT NULL UNIQUE,
    output_path TEXT NOT NULL UNIQUE,
    marker TEXT NOT NULL,
    exit_code INTEGER,
    result_json TEXT NOT NULL DEFAULT '{}',
    failure_reason TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    FOREIGN KEY (plan_id)
        REFERENCES orchestration_plans(plan_id)
        ON DELETE SET NULL,
    FOREIGN KEY (role_id)
        REFERENCES roles(role_id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_orchestrator_executions_plan
    ON orchestrator_executions(plan_id, created_at);

CREATE TABLE orchestration_tasks (
    orchestration_task_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    task_key TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (
        kind IN (
            'PIPELINE',
            'NOOP',
            'TEST_SLEEP',
            'TEST_FAIL'
        )
    ),
    project_id TEXT,
    role_id TEXT,
    status TEXT NOT NULL CHECK (
        status IN (
            'PENDING',
            'READY',
            'RUNNING',
            'BLOCKED',
            'COMPLETED',
            'FAILED',
            'CANCELLED'
        )
    ),
    priority INTEGER NOT NULL DEFAULT 100,
    instruction TEXT NOT NULL,
    acceptance_json TEXT NOT NULL DEFAULT '[]',
    marker TEXT,
    max_attempts INTEGER NOT NULL DEFAULT 1
        CHECK (max_attempts BETWEEN 1 AND 10),
    attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (attempt_count BETWEEN 0 AND 10),
    result_json TEXT NOT NULL DEFAULT '{}',
    failure_reason TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    heartbeat_at TEXT,
    finished_at TEXT,
    UNIQUE (plan_id, task_key),
    FOREIGN KEY (plan_id)
        REFERENCES orchestration_plans(plan_id)
        ON DELETE CASCADE,
    FOREIGN KEY (project_id)
        REFERENCES projects(project_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (role_id)
        REFERENCES roles(role_id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_orchestration_tasks_ready
    ON orchestration_tasks(plan_id, status, priority, created_at);

CREATE INDEX idx_orchestration_tasks_project
    ON orchestration_tasks(project_id, status);

CREATE INDEX idx_orchestration_tasks_heartbeat
    ON orchestration_tasks(heartbeat_at);

CREATE TABLE orchestration_dependencies (
    plan_id TEXT NOT NULL,
    orchestration_task_id TEXT NOT NULL,
    depends_on_task_id TEXT NOT NULL,
    dependency_condition TEXT NOT NULL DEFAULT 'SUCCESS'
        CHECK (dependency_condition = 'SUCCESS'),
    PRIMARY KEY (
        plan_id,
        orchestration_task_id,
        depends_on_task_id
    ),
    CHECK (orchestration_task_id <> depends_on_task_id),
    FOREIGN KEY (plan_id)
        REFERENCES orchestration_plans(plan_id)
        ON DELETE CASCADE,
    FOREIGN KEY (orchestration_task_id)
        REFERENCES orchestration_tasks(orchestration_task_id)
        ON DELETE CASCADE,
    FOREIGN KEY (depends_on_task_id)
        REFERENCES orchestration_tasks(orchestration_task_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_orchestration_dependencies_parent
    ON orchestration_dependencies(depends_on_task_id);

CREATE TABLE orchestration_attempts (
    attempt_id TEXT PRIMARY KEY,
    orchestration_task_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL
        CHECK (attempt_number BETWEEN 1 AND 10),
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
    run_id TEXT,
    worker_execution_id TEXT,
    review_execution_id TEXT,
    integration_id TEXT,
    result_json TEXT NOT NULL DEFAULT '{}',
    failure_reason TEXT,
    started_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    finished_at TEXT,
    UNIQUE (orchestration_task_id, attempt_number),
    FOREIGN KEY (orchestration_task_id)
        REFERENCES orchestration_tasks(orchestration_task_id)
        ON DELETE CASCADE,
    FOREIGN KEY (executor_instance_id)
        REFERENCES orchestrator_instances(instance_id)
        ON DELETE SET NULL,
    FOREIGN KEY (run_id)
        REFERENCES runs(run_id)
        ON DELETE SET NULL
);

CREATE INDEX idx_orchestration_attempts_status
    ON orchestration_attempts(status, heartbeat_at);

CREATE INDEX idx_orchestration_attempts_run
    ON orchestration_attempts(run_id);

INSERT INTO schema_migrations(version, applied_at)
VALUES (
    9,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
);

PRAGMA user_version = 9;
