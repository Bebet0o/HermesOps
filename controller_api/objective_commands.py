from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import stat
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .core import ControllerError, PROJECT_ID_PATTERN, Settings
from .event_journal import EventJournal

IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._~:-]{8,200}$")
OBJECTIVE_ID_PATTERN = re.compile(r"^objective-[a-f0-9]{32}$")
OPERATION_ID_PATTERN = re.compile(r"^operation-[a-f0-9]{32}$")
CSRF_TOKEN_PATTERN = re.compile(
    r"^csrf1\.([0-9]{10})\.([A-Za-z0-9_-]{32})\.([A-Za-z0-9_-]{43})$"
)
TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELLED"}
KNOWN_OBJECTIVE_STATUSES = {
    "QUEUED",
    "PLANNING",
    "RUNNING",
    "PAUSE_REQUESTED",
    "PAUSED",
    "CANCEL_REQUESTED",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
}
MAX_JSON_BODY_BYTES = 65_536
CSRF_LIFETIME_SECONDS = 600


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


class ObjectiveCommandStore:
    """Small synchronous command adapter over the existing objective queue."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def connect(self) -> sqlite3.Connection:
        path = self.settings.database
        try:
            metadata = path.lstat()
        except OSError as error:
            raise ControllerError(
                503,
                "database_unavailable",
                "Controller database unavailable",
            ) from error
        mode = stat.S_IMODE(metadata.st_mode)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or path.is_symlink()
            or metadata.st_nlink != 1
            or metadata.st_uid != os.geteuid()
            or mode & 0o022
        ):
            raise ControllerError(
                503,
                "database_unavailable",
                "Controller database unavailable",
                "The control database path is not a safe service-owned regular file.",
            )
        try:
            connection = sqlite3.connect(
                path,
                timeout=10,
                check_same_thread=False,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
        except sqlite3.Error as error:
            raise ControllerError(
                503,
                "database_unavailable",
                "Controller database unavailable",
            ) from error
        return connection

    def readiness(self) -> tuple[bool, str]:
        required = {
            "controller_operations",
            "controller_idempotency",
            "controller_command_audit",
            "controller_event_journal",
        }
        try:
            with closing(self.connect()) as connection:
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
        except ControllerError:
            return False, "command database cannot be opened"
        missing = required - tables
        if missing:
            return False, "controller command tables are missing"
        return True, "ready"

    @staticmethod
    def _session_fingerprint(session_token: str) -> str:
        return hashlib.sha256(session_token.encode("ascii")).hexdigest()[:32]

    @staticmethod
    def _key_hash(session_token: str, idempotency_key: str) -> str:
        return hmac.new(
            session_token.encode("ascii"),
            b"hermesops-idempotency-v1\0" + idempotency_key.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _request_hash(
        session_token: str,
        method: str,
        route: str,
        body: dict[str, Any],
    ) -> str:
        material = (
            method.encode("ascii")
            + b"\0"
            + route.encode("utf-8")
            + b"\0"
            + canonical_json(body).encode("utf-8")
        )
        return hmac.new(
            session_token.encode("ascii"),
            b"hermesops-request-v1\0" + material,
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def validate_idempotency_key(value: str | None) -> str:
        if value is None or not IDEMPOTENCY_KEY_PATTERN.fullmatch(value):
            raise ControllerError(
                400,
                "invalid_idempotency_key",
                "Invalid Idempotency-Key",
                "Idempotency-Key must contain 8..200 safe ASCII characters.",
            )
        return value

    def issue_csrf_token(self, session_token: str) -> tuple[str, str]:
        issued = int(datetime.now(timezone.utc).timestamp())
        nonce = _b64url(secrets.token_bytes(24))
        material = f"csrf1\0{issued}\0{nonce}".encode("ascii")
        signature = _b64url(
            hmac.new(
                session_token.encode("ascii"),
                material,
                hashlib.sha256,
            ).digest()
        )
        expires = datetime.fromtimestamp(
            issued + CSRF_LIFETIME_SECONDS,
            timezone.utc,
        ).isoformat(timespec="seconds").replace("+00:00", "Z")
        return f"csrf1.{issued}.{nonce}.{signature}", expires

    def verify_csrf_token(self, session_token: str, token: str | None) -> None:
        if token is None:
            raise ControllerError(
                403,
                "csrf_required",
                "CSRF token required",
            )
        match = CSRF_TOKEN_PATTERN.fullmatch(token)
        if match is None:
            raise ControllerError(403, "csrf_invalid", "Invalid CSRF token")
        issued = int(match.group(1))
        nonce = match.group(2)
        signature = match.group(3)
        now = int(datetime.now(timezone.utc).timestamp())
        if issued > now + 30 or now - issued > CSRF_LIFETIME_SECONDS:
            raise ControllerError(403, "csrf_expired", "Expired CSRF token")
        expected = _b64url(
            hmac.new(
                session_token.encode("ascii"),
                f"csrf1\0{issued}\0{nonce}".encode("ascii"),
                hashlib.sha256,
            ).digest()
        )
        if not hmac.compare_digest(signature, expected):
            raise ControllerError(403, "csrf_invalid", "Invalid CSRF token")

    @staticmethod
    def _normalize_timestamp(value: Any) -> str:
        if value is None:
            return utc_now()
        if not isinstance(value, str) or not value.strip():
            raise ControllerError(400, "invalid_not_before", "Invalid not_before")
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as error:
            raise ControllerError(400, "invalid_not_before", "Invalid not_before") from error
        if parsed.tzinfo is None:
            raise ControllerError(400, "invalid_not_before", "Invalid not_before")
        return (
            parsed.astimezone(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    @staticmethod
    def _validate_create_body(body: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "project_ids",
            "title",
            "description",
            "priority",
            "not_before",
            "max_parallel_tasks",
            "planning_max_attempts",
            "constraints",
        }
        unknown = set(body) - allowed
        if unknown:
            raise ControllerError(
                400,
                "unknown_request_field",
                "Unknown request field",
            )
        for required in ("project_ids", "title", "description"):
            if required not in body:
                raise ControllerError(400, "invalid_objective", "Invalid objective request")
        projects = body["project_ids"]
        if (
            not isinstance(projects, list)
            or not projects
            or len(projects) > 64
            or any(not isinstance(item, str) for item in projects)
        ):
            raise ControllerError(400, "invalid_project_ids", "Invalid project identifiers")
        normalized_projects = sorted(set(projects))
        if len(normalized_projects) != len(projects) or any(
            not PROJECT_ID_PATTERN.fullmatch(item) for item in normalized_projects
        ):
            raise ControllerError(400, "invalid_project_ids", "Invalid project identifiers")
        title = body["title"]
        description = body["description"]
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
            raise ControllerError(400, "invalid_title", "Invalid objective title")
        if not isinstance(description, str) or not 1 <= len(description.strip()) <= 16_384:
            raise ControllerError(400, "invalid_description", "Invalid objective description")
        constraints = body.get("constraints", [])
        if (
            not isinstance(constraints, list)
            or len(constraints) > 128
            or any(
                not isinstance(item, str)
                or not item.strip()
                or len(item) > 1000
                for item in constraints
            )
        ):
            raise ControllerError(400, "invalid_constraints", "Invalid objective constraints")
        priority = body.get("priority", 100)
        max_parallel = body.get("max_parallel_tasks", 1)
        planning_attempts = body.get("planning_max_attempts", 3)
        if type(priority) is not int or not -1000 <= priority <= 1000:
            raise ControllerError(400, "invalid_priority", "Invalid objective priority")
        if type(max_parallel) is not int or not 1 <= max_parallel <= 16:
            raise ControllerError(400, "invalid_max_parallel_tasks", "Invalid max_parallel_tasks")
        if type(planning_attempts) is not int or not 1 <= planning_attempts <= 5:
            raise ControllerError(400, "invalid_planning_max_attempts", "Invalid planning_max_attempts")
        objective = title.strip() + "\n\n" + description.strip()
        if constraints:
            objective += "\n\nConstraints:\n" + "\n".join(
                f"- {item.strip()}" for item in constraints
            )
        if len(objective.encode("utf-8")) > 16_384:
            raise ControllerError(400, "objective_too_large", "Objective exceeds 16 KiB")
        return {
            "project_ids": normalized_projects,
            "objective": objective,
            "priority": priority,
            "not_before": ObjectiveCommandStore._normalize_timestamp(body.get("not_before")),
            "max_parallel_tasks": max_parallel,
            "planning_max_attempts": planning_attempts,
        }

    @staticmethod
    def _validate_command_body(body: dict[str, Any]) -> str | None:
        if set(body) - {"reason"}:
            raise ControllerError(400, "unknown_request_field", "Unknown request field")
        reason = body.get("reason")
        if reason is not None and (
            not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000
        ):
            raise ControllerError(400, "invalid_reason", "Invalid command reason")
        return reason.strip() if isinstance(reason, str) else None

    @staticmethod
    def _single_project_id(project_scope_json: str) -> str | None:
        try:
            project_ids = json.loads(project_scope_json)
        except (TypeError, json.JSONDecodeError) as error:
            raise ControllerError(
                503,
                "objective_projection_invalid",
                "Objective projection unavailable",
            ) from error
        if (
            not isinstance(project_ids, list)
            or not project_ids
            or any(not isinstance(value, str) for value in project_ids)
            or len(set(project_ids)) != len(project_ids)
        ):
            raise ControllerError(
                503,
                "objective_projection_invalid",
                "Objective projection unavailable",
            )
        return project_ids[0] if len(project_ids) == 1 else None

    @staticmethod
    def _add_event(
        connection: sqlite3.Connection,
        *,
        objective_id: str,
        event_type: str,
        old_status: str | None,
        new_status: str | None,
        operation_id: str,
        project_id: str | None,
        payload: dict[str, Any],
        occurred_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO objective_events (
                objective_event_id, objective_id, event_type,
                old_status, new_status, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "objective-event-" + uuid.uuid4().hex,
                objective_id,
                event_type,
                old_status,
                new_status,
                canonical_json(payload),
                occurred_at,
            ),
        )
        if old_status is None:
            journal_type = "objective.created"
            journal_data = {
                "state": str(new_status).lower(),
                "source": payload.get("source"),
                "priority": payload.get("priority"),
                "not_before": payload.get("not_before"),
                "project_ids": payload.get("projects", []),
            }
        else:
            journal_type = "objective.state_changed"
            journal_data = {
                "previous_state": old_status.lower(),
                "state": str(new_status).lower(),
                "reason_code": event_type.lower(),
                "reason_present": bool(payload.get("reason_present")),
            }
        EventJournal.emit(
            connection,
            event_type=journal_type,
            actor_type="operator",
            actor_id="operator:local-controller-session",
            aggregate_type="objective",
            aggregate_id=objective_id,
            correlation_id=EventJournal.correlation_for_causation(operation_id),
            causation_id=operation_id,
            project_id=project_id,
            objective_id=objective_id,
            data=journal_data,
            occurred_at=occurred_at,
        )

    @staticmethod
    def _running_task_count(connection: sqlite3.Connection, plan_id: str | None) -> int:
        if plan_id is None:
            return 0
        return int(
            connection.execute(
                "SELECT COUNT(*) FROM orchestration_tasks "
                "WHERE plan_id=? AND status='RUNNING'",
                (plan_id,),
            ).fetchone()[0]
        )

    @staticmethod
    def _cancel_plan(connection: sqlite3.Connection, plan_id: str | None, now: str) -> None:
        if plan_id is None:
            return
        connection.execute(
            """
            UPDATE orchestration_tasks
            SET status='CANCELLED', heartbeat_at=?, finished_at=?,
                failure_reason=COALESCE(failure_reason, 'objective cancelled')
            WHERE plan_id=? AND status IN ('PENDING','READY','BLOCKED')
            """,
            (now, now, plan_id),
        )
        connection.execute(
            """
            UPDATE orchestration_plans
            SET status='CANCELLED', heartbeat_at=?, finished_at=?,
                last_error='objective cancelled'
            WHERE plan_id=? AND status NOT IN ('COMPLETED','FAILED','CANCELLED')
            """,
            (now, now, plan_id),
        )

    def _replay_or_reserve(
        self,
        connection: sqlite3.Connection,
        *,
        session_token: str,
        idempotency_key: str,
        method: str,
        route: str,
        body: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str, str, str]:
        session_fp = self._session_fingerprint(session_token)
        key_hash = self._key_hash(session_token, idempotency_key)
        request_hash = self._request_hash(
            session_token, method, route, body
        )
        row = connection.execute(
            """
            SELECT method, route, request_hash, response_status, response_json
            FROM controller_idempotency
            WHERE session_fingerprint=? AND key_hash=?
            """,
            (session_fp, key_hash),
        ).fetchone()
        if row is not None:
            if (
                str(row["method"]) != method
                or str(row["route"]) != route
                or str(row["request_hash"]) != request_hash
            ):
                raise ControllerError(
                    409,
                    "idempotency_conflict",
                    "Idempotency key conflict",
                    "The key was already used for a different request.",
                )
            if row["response_json"] is None:
                raise ControllerError(409, "command_in_progress", "Command already in progress")
            return json.loads(str(row["response_json"])), session_fp, key_hash, request_hash
        connection.execute(
            """
            INSERT INTO controller_idempotency (
                session_fingerprint, key_hash, method, route, request_hash,
                response_status, response_json, operation_id, created_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, ?, NULL)
            """,
            (session_fp, key_hash, method, route, request_hash, utc_now()),
        )
        return None, session_fp, key_hash, request_hash

    @staticmethod
    def _complete_idempotency(
        connection: sqlite3.Connection,
        *,
        session_fp: str,
        key_hash: str,
        status: int,
        payload: dict[str, Any],
        operation_id: str | None,
    ) -> None:
        connection.execute(
            """
            UPDATE controller_idempotency
            SET response_status=?, response_json=?, operation_id=?, completed_at=?
            WHERE session_fingerprint=? AND key_hash=?
            """,
            (
                status,
                canonical_json(payload),
                operation_id,
                utc_now(),
                session_fp,
                key_hash,
            ),
        )

    @staticmethod
    def _operation_payload(
        operation_id: str,
        *,
        kind: str,
        objective_id: str,
        state: str,
        created_at: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "id": operation_id,
            "kind": kind,
            "state": state,
            "created_at": created_at,
            "updated_at": created_at,
            "finished_at": created_at,
            "target": {"type": "objective", "id": objective_id},
            "result": result,
            "error": None,
            "legacy_projection": False,
        }

    def _record_operation(
        self,
        connection: sqlite3.Connection,
        *,
        operation_id: str,
        kind: str,
        objective_id: str,
        result: dict[str, Any],
        created_at: str,
    ) -> dict[str, Any]:
        payload = self._operation_payload(
            operation_id,
            kind=kind,
            objective_id=objective_id,
            state="succeeded",
            created_at=created_at,
            result=result,
        )
        connection.execute(
            """
            INSERT INTO controller_operations (
                operation_id, command_kind, state, target_type, target_id,
                result_json, error_code, created_at, updated_at, finished_at
            ) VALUES (?, ?, 'SUCCEEDED', 'objective', ?, ?, NULL, ?, ?, ?)
            """,
            (
                operation_id,
                kind,
                objective_id,
                canonical_json(result),
                created_at,
                created_at,
                created_at,
            ),
        )
        return payload

    @staticmethod
    def _audit(
        connection: sqlite3.Connection,
        *,
        operation_id: str,
        action: str,
        objective_id: str,
        session_fp: str,
        key_hash: str,
        request_hash: str,
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO controller_command_audit (
                audit_id, operation_id, actor_type, actor_id,
                action, resource_type, resource_id,
                session_fingerprint, idempotency_key_hash, request_hash,
                outcome, created_at
            ) VALUES (?, ?, 'session', ?, ?, 'objective', ?, ?, ?, ?, 'SUCCEEDED', ?)
            """,
            (
                "audit-" + uuid.uuid4().hex,
                operation_id,
                "local-controller-session",
                action,
                objective_id,
                session_fp,
                key_hash,
                request_hash,
                created_at,
            ),
        )

    def issue_csrf(
        self,
        *,
        session_token: str,
        idempotency_key: str,
        route: str,
        body: dict[str, Any],
        meta_factory: Callable[[], dict[str, Any]],
    ) -> tuple[int, dict[str, Any]]:
        self.validate_idempotency_key(idempotency_key)
        with closing(self.connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                replay, session_fp, key_hash, _ = self._replay_or_reserve(
                    connection,
                    session_token=session_token,
                    idempotency_key=idempotency_key,
                    method="POST",
                    route=route,
                    body=body,
                )
                if replay is not None:
                    connection.commit()
                    return 200, replay
                if body:
                    raise ControllerError(
                        400,
                        "invalid_request_body",
                        "Expected an empty JSON object",
                    )
                token, expires_at = self.issue_csrf_token(session_token)
                payload = {
                    "data": {"token": token, "expires_at": expires_at},
                    "meta": meta_factory(),
                }
                self._complete_idempotency(
                    connection,
                    session_fp=session_fp,
                    key_hash=key_hash,
                    status=200,
                    payload=payload,
                    operation_id=None,
                )
                connection.commit()
                return 200, payload
            except Exception:
                connection.rollback()
                raise

    def create_objective(
        self,
        *,
        session_token: str,
        idempotency_key: str,
        route: str,
        body: dict[str, Any],
        meta_factory: Callable[[int | None], dict[str, Any]],
    ) -> tuple[int, dict[str, Any]]:
        self.validate_idempotency_key(idempotency_key)
        with closing(self.connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                replay, session_fp, key_hash, request_hash = self._replay_or_reserve(
                    connection,
                    session_token=session_token,
                    idempotency_key=idempotency_key,
                    method="POST",
                    route=route,
                    body=body,
                )
                if replay is not None:
                    connection.commit()
                    return 202, replay
                data = self._validate_create_body(body)
                objective_id = "objective-" + uuid.uuid4().hex
                operation_id = "operation-" + uuid.uuid4().hex
                now = utc_now()
                placeholders = ",".join("?" for _ in data["project_ids"])
                rows = list(
                    connection.execute(
                        f"SELECT project_id, enabled FROM projects WHERE project_id IN ({placeholders})",
                        tuple(data["project_ids"]),
                    )
                )
                if {str(row["project_id"]) for row in rows} != set(data["project_ids"]):
                    raise ControllerError(400, "unknown_project", "Unknown project")
                if any(not int(row["enabled"]) for row in rows):
                    raise ControllerError(409, "project_disabled", "Project is disabled")
                connection.execute(
                    """
                    INSERT INTO objective_queue (
                        objective_id, objective, source, status, priority,
                        not_before, project_scope_json, max_parallel_tasks,
                        planning_max_attempts, planning_attempt_count,
                        plan_id, planner_execution_id, created_at, started_at,
                        heartbeat_at, finished_at, paused_at, last_error
                    ) VALUES (?, ?, 'AI', 'QUEUED', ?, ?, ?, ?, ?, 0,
                              NULL, NULL, ?, NULL, ?, NULL, NULL, NULL)
                    """,
                    (
                        objective_id,
                        data["objective"],
                        data["priority"],
                        data["not_before"],
                        canonical_json(data["project_ids"]),
                        data["max_parallel_tasks"],
                        data["planning_max_attempts"],
                        now,
                        now,
                    ),
                )
                self._add_event(
                    connection,
                    objective_id=objective_id,
                    event_type="OBJECTIVE_SUBMITTED",
                    old_status=None,
                    new_status="QUEUED",
                    operation_id=operation_id,
                    project_id=(data["project_ids"][0] if len(data["project_ids"]) == 1 else None),
                    occurred_at=now,
                    payload={
                        "source": "AI",
                        "priority": data["priority"],
                        "not_before": data["not_before"],
                        "projects": data["project_ids"],
                    },
                )
                operation = self._record_operation(
                    connection,
                    operation_id=operation_id,
                    kind="objective.create",
                    objective_id=objective_id,
                    result={"objective_id": objective_id, "state": "queued"},
                    created_at=now,
                )
                self._audit(
                    connection,
                    operation_id=operation_id,
                    action="objective.create",
                    objective_id=objective_id,
                    session_fp=session_fp,
                    key_hash=key_hash,
                    request_hash=request_hash,
                    created_at=now,
                )
                payload = {"data": operation, "meta": meta_factory(None)}
                self._complete_idempotency(
                    connection,
                    session_fp=session_fp,
                    key_hash=key_hash,
                    status=202,
                    payload=payload,
                    operation_id=operation_id,
                )
                connection.commit()
                return 202, payload
            except Exception:
                connection.rollback()
                raise

    def command_objective(
        self,
        *,
        session_token: str,
        idempotency_key: str,
        route: str,
        objective_id: str,
        command: str,
        body: dict[str, Any],
        meta_factory: Callable[[int | None], dict[str, Any]],
    ) -> tuple[int, dict[str, Any]]:
        self.validate_idempotency_key(idempotency_key)
        with closing(self.connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                replay, session_fp, key_hash, request_hash = self._replay_or_reserve(
                    connection,
                    session_token=session_token,
                    idempotency_key=idempotency_key,
                    method="POST",
                    route=route,
                    body=body,
                )
                if replay is not None:
                    connection.commit()
                    return 202, replay
                if not OBJECTIVE_ID_PATTERN.fullmatch(objective_id):
                    raise ControllerError(
                        400,
                        "invalid_objective_id",
                        "Invalid objective identifier",
                    )
                if command not in {"pause", "resume", "cancel"}:
                    raise ControllerError(
                        409,
                        "objective_command_unavailable",
                        "Objective command unavailable",
                        "Milestone 2G implements pause, resume and cancel only.",
                    )
                reason = self._validate_command_body(body)
                operation_id = "operation-" + uuid.uuid4().hex
                now = utc_now()
                row = connection.execute(
                    "SELECT * FROM objective_queue WHERE objective_id=?",
                    (objective_id,),
                ).fetchone()
                if row is None:
                    raise ControllerError(
                        404,
                        "objective_not_found",
                        "Objective not found",
                        resource={"type": "objective", "id": objective_id},
                    )
                old = str(row["status"])
                if old not in KNOWN_OBJECTIVE_STATUSES:
                    raise ControllerError(
                        503,
                        "objective_state_invalid",
                        "Objective state unavailable",
                    )
                if command == "pause":
                    if old == "CANCEL_REQUESTED":
                        raise ControllerError(
                            409,
                            "objective_cancel_pending",
                            "Objective cancellation is pending",
                        )
                    if old in TERMINAL_STATUSES:
                        raise ControllerError(409, "objective_terminal", "Objective is terminal")
                    if old == "PAUSED":
                        new = "PAUSED"
                    else:
                        running = self._running_task_count(connection, row["plan_id"])
                        new = "PAUSE_REQUESTED" if old == "PLANNING" or running else "PAUSED"
                        connection.execute(
                            """
                            UPDATE objective_queue SET status=?, heartbeat_at=?,
                                paused_at=CASE WHEN ?='PAUSED' THEN ? ELSE paused_at END,
                                last_error=NULL WHERE objective_id=?
                            """,
                            (new, now, new, now, objective_id),
                        )
                        self._add_event(
                            connection,
                            objective_id=objective_id,
                            event_type=(
                                "OBJECTIVE_PAUSE_REQUESTED"
                                if new == "PAUSE_REQUESTED"
                                else "OBJECTIVE_PAUSED"
                            ),
                            old_status=old,
                            new_status=new,
                            operation_id=operation_id,
                            project_id=(self._single_project_id(str(row["project_scope_json"]))),
                            occurred_at=now,
                            payload={"reason_present": reason is not None},
                        )
                elif command == "resume":
                    if old != "PAUSED":
                        raise ControllerError(409, "objective_not_paused", "Objective can only resume from PAUSED")
                    new = "QUEUED"
                    connection.execute(
                        """
                        UPDATE objective_queue SET status='QUEUED',
                            heartbeat_at=?, paused_at=NULL, finished_at=NULL,
                            last_error=NULL WHERE objective_id=?
                        """,
                        (now, objective_id),
                    )
                    self._add_event(
                        connection,
                        objective_id=objective_id,
                        event_type="OBJECTIVE_RESUMED",
                        old_status=old,
                        new_status=new,
                        operation_id=operation_id,
                        project_id=(self._single_project_id(str(row["project_scope_json"]))),
                        occurred_at=now,
                        payload={"reason_present": reason is not None},
                    )
                else:
                    if old in TERMINAL_STATUSES:
                        raise ControllerError(409, "objective_terminal", "Objective is terminal")
                    running = self._running_task_count(connection, row["plan_id"])
                    new = "CANCEL_REQUESTED" if old == "PLANNING" or running else "CANCELLED"
                    self._cancel_plan(connection, row["plan_id"], now)
                    connection.execute(
                        """
                        UPDATE objective_queue SET status=?, heartbeat_at=?,
                            finished_at=CASE WHEN ?='CANCELLED' THEN ? ELSE NULL END,
                            last_error=CASE WHEN ?='CANCELLED' THEN 'cancelled by operator' ELSE last_error END
                        WHERE objective_id=?
                        """,
                        (new, now, new, now, new, objective_id),
                    )
                    self._add_event(
                        connection,
                        objective_id=objective_id,
                        event_type=(
                            "OBJECTIVE_CANCEL_REQUESTED"
                            if new == "CANCEL_REQUESTED"
                            else "OBJECTIVE_CANCELLED"
                        ),
                        old_status=old,
                        new_status=new,
                        operation_id=operation_id,
                        project_id=(self._single_project_id(str(row["project_scope_json"]))),
                        occurred_at=now,
                        payload={"reason_present": reason is not None},
                    )
                operation = self._record_operation(
                    connection,
                    operation_id=operation_id,
                    kind=f"objective.{command}",
                    objective_id=objective_id,
                    result={"objective_id": objective_id, "raw_state": new},
                    created_at=now,
                )
                self._audit(
                    connection,
                    operation_id=operation_id,
                    action=f"objective.{command}",
                    objective_id=objective_id,
                    session_fp=session_fp,
                    key_hash=key_hash,
                    request_hash=request_hash,
                    created_at=now,
                )
                payload = {"data": operation, "meta": meta_factory(None)}
                self._complete_idempotency(
                    connection,
                    session_fp=session_fp,
                    key_hash=key_hash,
                    status=202,
                    payload=payload,
                    operation_id=operation_id,
                )
                connection.commit()
                return 202, payload
            except Exception:
                connection.rollback()
                raise

    def get_operation(self, operation_id: str) -> dict[str, Any] | None:
        if not OPERATION_ID_PATTERN.fullmatch(operation_id):
            return None
        try:
            with closing(self.connect()) as connection:
                row = connection.execute(
                    """
                    SELECT operation_id, command_kind, state, target_type,
                           target_id, result_json, error_code,
                           created_at, updated_at, finished_at
                    FROM controller_operations WHERE operation_id=?
                    """,
                    (operation_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise ControllerError(503, "database_unavailable", "Controller database unavailable") from error
        if row is None:
            raise ControllerError(
                404,
                "operation_not_found",
                "Operation not found",
                resource={"type": "operation", "id": operation_id},
            )
        try:
            result = json.loads(str(row["result_json"]))
        except json.JSONDecodeError as error:
            raise ControllerError(503, "operation_projection_invalid", "Operation projection unavailable") from error
        payload = {
            "id": str(row["operation_id"]),
            "kind": str(row["command_kind"]),
            "state": str(row["state"]).lower(),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "finished_at": str(row["finished_at"]) if row["finished_at"] else None,
            "target": {"type": str(row["target_type"]), "id": str(row["target_id"])},
            "result": result,
            "error": ({"code": str(row["error_code"])} if row["error_code"] else None),
            "legacy_projection": False,
        }
        digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        payload["resource_revision"] = int(digest[:15], 16)
        return payload
