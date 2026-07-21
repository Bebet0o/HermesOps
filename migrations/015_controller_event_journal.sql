-- HermesOps milestone 2I: durable Controller event journal.
-- The legacy events and objective_events tables remain untouched.

CREATE TABLE controller_event_journal (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE CHECK (
        length(event_id) = 36
        AND substr(event_id, 1, 4) = 'evt_'
        AND substr(event_id, 5) NOT GLOB '*[^0-9a-f]*'
    ),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    event_type TEXT NOT NULL CHECK (
        length(event_type) BETWEEN 3 AND 128
        AND event_type = lower(event_type)
        AND substr(event_type, 1, 1) GLOB '[a-z]'
        AND substr(event_type, -1, 1) GLOB '[a-z0-9_]'
        AND instr(event_type, '.') > 1
        AND instr(event_type, '..') = 0
        AND event_type NOT GLOB '*[^a-z0-9_.]*'
    ),
    occurred_at TEXT NOT NULL CHECK (
        length(occurred_at) BETWEEN 20 AND 40
        AND substr(occurred_at, -1, 1) = 'Z'
    ),
    actor_type TEXT NOT NULL CHECK (
        actor_type IN ('operator', 'system', 'agent', 'worker')
    ),
    actor_id TEXT NOT NULL CHECK (
        length(actor_id) BETWEEN 1 AND 200
    ),
    aggregate_type TEXT NOT NULL CHECK (
        aggregate_type IN (
            'system', 'project', 'objective', 'task', 'run', 'review',
            'recovery', 'sandbox', 'sandbox_build', 'backup',
            'notification', 'confirmation', 'audit'
        )
    ),
    aggregate_id TEXT NOT NULL CHECK (
        length(aggregate_id) BETWEEN 1 AND 200
    ),
    aggregate_revision INTEGER NOT NULL CHECK (aggregate_revision >= 1),
    project_id TEXT CHECK (
        project_id IS NULL OR (
            length(project_id) BETWEEN 1 AND 200
        )
    ),
    objective_id TEXT CHECK (
        objective_id IS NULL OR (
            length(objective_id) BETWEEN 1 AND 200
        )
    ),
    correlation_id TEXT NOT NULL CHECK (
        length(correlation_id) = 37
        AND substr(correlation_id, 1, 5) = 'corr_'
        AND substr(correlation_id, 6) NOT GLOB '*[^0-9a-f]*'
    ),
    causation_id TEXT CHECK (
        causation_id IS NULL OR (
            length(causation_id) BETWEEN 1 AND 200
        )
    ),
    redacted_data_json TEXT NOT NULL CHECK (
        length(redacted_data_json) <= 16384
        AND json_valid(redacted_data_json)
        AND json_type(redacted_data_json) = 'object'
    ),
    UNIQUE (aggregate_type, aggregate_id, aggregate_revision)
);

CREATE TRIGGER controller_event_journal_immutable_update
BEFORE UPDATE ON controller_event_journal
BEGIN
    SELECT RAISE(ABORT, 'controller event journal is immutable');
END;

CREATE TRIGGER controller_event_journal_immutable_delete
BEFORE DELETE ON controller_event_journal
BEGIN
    SELECT RAISE(ABORT, 'controller event journal is immutable');
END;

CREATE INDEX idx_controller_event_journal_project_sequence
    ON controller_event_journal(project_id, sequence);

CREATE INDEX idx_controller_event_journal_objective_sequence
    ON controller_event_journal(objective_id, sequence);

CREATE INDEX idx_controller_event_journal_aggregate_revision
    ON controller_event_journal(
        aggregate_type, aggregate_id, aggregate_revision
    );

CREATE INDEX idx_controller_event_journal_correlation
    ON controller_event_journal(correlation_id, sequence);

PRAGMA user_version = 15;
