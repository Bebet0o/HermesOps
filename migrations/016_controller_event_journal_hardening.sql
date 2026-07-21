-- HermesOps milestone 2I adversarial hardening.
-- Prevent SQLite REPLACE from bypassing the immutable journal triggers and
-- reject non-canonical or calendar-invalid timestamps at the persistence boundary.

CREATE TRIGGER controller_event_journal_no_replace_insert
BEFORE INSERT ON controller_event_journal
WHEN EXISTS (
        SELECT 1
        FROM controller_event_journal
        WHERE sequence = NEW.sequence
           OR event_id = NEW.event_id
           OR (
                aggregate_type = NEW.aggregate_type
                AND aggregate_id = NEW.aggregate_id
                AND aggregate_revision = NEW.aggregate_revision
           )
    )
BEGIN
    SELECT RAISE(ABORT, 'controller event journal conflicts are immutable');
END;

CREATE TRIGGER controller_event_journal_timestamp_insert_guard
BEFORE INSERT ON controller_event_journal
WHEN length(NEW.occurred_at) < 20
  OR length(NEW.occurred_at) > 27
  OR substr(NEW.occurred_at, 5, 1) != '-'
  OR substr(NEW.occurred_at, 8, 1) != '-'
  OR substr(NEW.occurred_at, 11, 1) != 'T'
  OR substr(NEW.occurred_at, 14, 1) != ':'
  OR substr(NEW.occurred_at, 17, 1) != ':'
  OR substr(NEW.occurred_at, -1, 1) != 'Z'
  OR substr(NEW.occurred_at, 1, 4) GLOB '*[^0-9]*'
  OR substr(NEW.occurred_at, 6, 2) GLOB '*[^0-9]*'
  OR substr(NEW.occurred_at, 9, 2) GLOB '*[^0-9]*'
  OR substr(NEW.occurred_at, 12, 2) GLOB '*[^0-9]*'
  OR substr(NEW.occurred_at, 15, 2) GLOB '*[^0-9]*'
  OR substr(NEW.occurred_at, 18, 2) GLOB '*[^0-9]*'
  OR (
        length(NEW.occurred_at) > 20
        AND (
            substr(NEW.occurred_at, 20, 1) != '.'
            OR length(NEW.occurred_at) < 22
            OR substr(
                NEW.occurred_at,
                21,
                length(NEW.occurred_at) - 21
            ) GLOB '*[^0-9]*'
        )
    )
  OR CAST(substr(NEW.occurred_at, 1, 4) AS INTEGER) < 1
  OR CAST(substr(NEW.occurred_at, 6, 2) AS INTEGER) NOT BETWEEN 1 AND 12
  OR CAST(substr(NEW.occurred_at, 9, 2) AS INTEGER) < 1
  OR CAST(substr(NEW.occurred_at, 12, 2) AS INTEGER) NOT BETWEEN 0 AND 23
  OR CAST(substr(NEW.occurred_at, 15, 2) AS INTEGER) NOT BETWEEN 0 AND 59
  OR CAST(substr(NEW.occurred_at, 18, 2) AS INTEGER) NOT BETWEEN 0 AND 59
  OR CAST(substr(NEW.occurred_at, 9, 2) AS INTEGER) > CASE
        CAST(substr(NEW.occurred_at, 6, 2) AS INTEGER)
        WHEN 1 THEN 31
        WHEN 2 THEN 28 + CASE
            WHEN CAST(substr(NEW.occurred_at, 1, 4) AS INTEGER) % 400 = 0
              OR (
                    CAST(substr(NEW.occurred_at, 1, 4) AS INTEGER) % 4 = 0
                    AND CAST(substr(NEW.occurred_at, 1, 4) AS INTEGER) % 100 != 0
                 )
            THEN 1 ELSE 0 END
        WHEN 3 THEN 31
        WHEN 4 THEN 30
        WHEN 5 THEN 31
        WHEN 6 THEN 30
        WHEN 7 THEN 31
        WHEN 8 THEN 31
        WHEN 9 THEN 30
        WHEN 10 THEN 31
        WHEN 11 THEN 30
        WHEN 12 THEN 31
        ELSE 0
    END
BEGIN
    SELECT RAISE(ABORT, 'invalid controller event timestamp');
END;

INSERT INTO schema_migrations(version, applied_at)
VALUES (16, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

PRAGMA user_version = 16;
