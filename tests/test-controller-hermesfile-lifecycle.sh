#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C
export PYTHONDONTWRITEBYTECODE=1

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

python3 -m unittest -v tests.test_controller_hermesfile_lifecycle

python3 - <<'PY'
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

root = Path.cwd()
migration = root / "migrations/022_hermesfile_lifecycle.sql"
source = migration.read_text(encoding="utf-8")
for phrase in (
    "CREATE TABLE controller_hermesfile_operations",
    "CREATE TABLE controller_hermesfile_idempotency",
    "CREATE TABLE controller_hermesfile_command_audit",
    "controller Hermesfile audit is immutable",
    "PRAGMA user_version = 22",
):
    if phrase not in source:
        raise SystemExit(f"Hermesfile lifecycle migration contract missing: {phrase}")
for forbidden in (
    "create table sandbox_builds",
    "docker build",
    "active_image_digest =",
    "delete from sandbox_profile_revisions",
):
    if forbidden in source.lower():
        raise SystemExit(f"2T migration exceeds scope: {forbidden}")

with tempfile.TemporaryDirectory() as directory:
    database = Path(directory) / "fresh.db"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for item in sorted((root / "migrations").glob("[0-9][0-9][0-9]_*.sql")):
            connection.executescript(item.read_text(encoding="utf-8"))
        if connection.execute("PRAGMA user_version").fetchone()[0] != 22:
            raise SystemExit("fresh migration did not reach schema 22")
        if connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] != 22:
            raise SystemExit("fresh migration ledger did not reach 22")
        if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise SystemExit("fresh migration quick_check failed")
        required = {
            "controller_hermesfile_operations",
            "controller_hermesfile_idempotency",
            "controller_hermesfile_command_audit",
        }
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if not required <= tables:
            raise SystemExit(f"Hermesfile lifecycle tables missing: {sorted(required-tables)}")

        try:
            connection.executescript(migration.read_text(encoding="utf-8"))
        except sqlite3.Error:
            connection.rollback()
        else:
            raise SystemExit("Hermesfile lifecycle migration rerun unexpectedly succeeded")

        if connection.execute("PRAGMA user_version").fetchone()[0] != 22:
            raise SystemExit("migration rerun changed schema version")
        if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise SystemExit("migration rerun damaged database")

print("HERMESOPS_2T_MIGRATION_FRESH_PASS")
print("HERMESOPS_2T_MIGRATION_RERUN_FAIL_CLOSED_PASS")
PY

echo "HERMESOPS_2T_CONTROLLER_HERMESFILE_LIFECYCLE_PASS"
