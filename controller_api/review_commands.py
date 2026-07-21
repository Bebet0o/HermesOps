from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import closing
from typing import Any, Callable

from .core import ControllerError, Settings
from .event_journal import EventJournal
from .objective_commands import ObjectiveCommandStore, canonical_json, utc_now

REVIEW_ID_PATTERN = re.compile(r"^review-[a-f0-9]{32}$")
OPERATION_ID_PATTERN = re.compile(r"^operation-[a-f0-9]{32}$")
SAFE_REVIEW_COMMANDS = {"acknowledge-debt", "request-human-review"}
KNOWN_REVIEW_VERDICTS = {
    "PASS",
    "PASS_WITH_DEBT",
    "FIX",
    "SECURITY",
    "PERFORMANCE",
    "ARCHITECTURE",
    "HUMAN",
}


class ReviewCommandStore:
    """Bounded human review decisions without reviewer reruns or integration."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.shared = ObjectiveCommandStore(settings)

    def connect(self) -> sqlite3.Connection:
        return self.shared.connect()

    def readiness(self) -> tuple[bool, str]:
        required = {
            "controller_review_operations",
            "controller_review_idempotency",
            "controller_review_command_audit",
            "controller_review_actions",
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
            return False, "review command database cannot be opened"
        if required - tables:
            return False, "controller review command tables are missing"
        return True, "ready"

    @staticmethod
    def _validate_body(body: dict[str, Any]) -> str | None:
        return ObjectiveCommandStore._validate_command_body(body)

    def _replay_or_reserve(
        self,
        connection: sqlite3.Connection,
        *,
        session_token: str,
        idempotency_key: str,
        route: str,
        body: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str, str, str]:
        session_fp = self.shared._session_fingerprint(session_token)
        key_hash = self.shared._key_hash(session_token, idempotency_key)
        request_hash = self.shared._request_hash(
            session_token, "POST", route, body
        )
        row = connection.execute(
            """
            SELECT method, route, request_hash, response_json
            FROM controller_review_idempotency
            WHERE session_fingerprint=? AND key_hash=?
            """,
            (session_fp, key_hash),
        ).fetchone()
        if row is not None:
            if (
                str(row["method"]) != "POST"
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
                raise ControllerError(
                    503,
                    "idempotency_reservation_invalid",
                    "Idempotency reservation is incomplete",
                    "The persisted reservation cannot represent an active transaction.",
                )
            try:
                replay = json.loads(str(row["response_json"]))
            except json.JSONDecodeError as error:
                raise ControllerError(
                    503,
                    "operation_projection_invalid",
                    "Operation projection unavailable",
                ) from error
            if not isinstance(replay, dict):
                raise ControllerError(
                    503,
                    "operation_projection_invalid",
                    "Operation projection unavailable",
                )
            return replay, session_fp, key_hash, request_hash
        connection.execute(
            """
            INSERT INTO controller_review_idempotency (
                session_fingerprint, key_hash, method, route, request_hash,
                response_status, response_json, operation_id,
                created_at, completed_at
            ) VALUES (?, ?, 'POST', ?, ?, NULL, NULL, NULL, ?, NULL)
            """,
            (session_fp, key_hash, route, request_hash, utc_now()),
        )
        return None, session_fp, key_hash, request_hash

    @staticmethod
    def _complete_idempotency(
        connection: sqlite3.Connection,
        *,
        session_fp: str,
        key_hash: str,
        payload: dict[str, Any],
        operation_id: str,
    ) -> None:
        connection.execute(
            """
            UPDATE controller_review_idempotency
            SET response_status=202, response_json=?, operation_id=?, completed_at=?
            WHERE session_fingerprint=? AND key_hash=?
            """,
            (
                canonical_json(payload),
                operation_id,
                utc_now(),
                session_fp,
                key_hash,
            ),
        )

    @staticmethod
    def _operation_payload(
        *,
        operation_id: str,
        review_id: str,
        command: str,
        action_id: str,
        reason_present: bool,
        created_at: str,
    ) -> dict[str, Any]:
        return {
            "id": operation_id,
            "kind": f"review.{command}",
            "state": "succeeded",
            "created_at": created_at,
            "updated_at": created_at,
            "finished_at": created_at,
            "target": {"type": "review", "id": review_id},
            "result": {
                "review_id": review_id,
                "action_id": action_id,
                "command": command,
                "status": "recorded",
                "reason_present": reason_present,
            },
            "error": None,
            "legacy_projection": False,
        }

    @staticmethod
    def _revision(payload: dict[str, Any]) -> int:
        digest = hashlib.sha256(
            canonical_json(payload).encode("utf-8")
        ).hexdigest()
        return int(digest[:15], 16)

    def command_review(
        self,
        *,
        session_token: str,
        idempotency_key: str,
        route: str,
        review_id: str,
        command: str,
        body: dict[str, Any],
        meta_factory: Callable[[int], dict[str, Any]],
    ) -> tuple[int, dict[str, Any]]:
        self.shared.validate_idempotency_key(idempotency_key)
        if not REVIEW_ID_PATTERN.fullmatch(review_id):
            raise ControllerError(
                404,
                "review_not_found",
                "Review not found",
                resource={"type": "review", "id": review_id},
            )
        with closing(self.connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                replay, session_fp, key_hash, request_hash = self._replay_or_reserve(
                    connection,
                    session_token=session_token,
                    idempotency_key=idempotency_key,
                    route=route,
                    body=body,
                )
                if replay is not None:
                    connection.commit()
                    return 202, replay

                if command == "rerun":
                    raise ControllerError(
                        409,
                        "review_rerun_unavailable",
                        "Review rerun is unavailable",
                        "Milestone 2H does not schedule reviewer execution.",
                    )
                if command not in SAFE_REVIEW_COMMANDS:
                    raise ControllerError(
                        409,
                        "review_command_unavailable",
                        "Review command is unavailable",
                    )
                reason = self._validate_body(body)

                row = connection.execute(
                    """
                    SELECT review_id, run_id, verdict
                    FROM review_results
                    WHERE review_id=?
                    """,
                    (review_id,),
                ).fetchone()
                if row is None:
                    raise ControllerError(
                        404,
                        "review_not_found",
                        "Review not found",
                        resource={"type": "review", "id": review_id},
                    )
                run_row = connection.execute(
                    "SELECT project_id FROM runs WHERE run_id=?",
                    (str(row["run_id"]),),
                ).fetchone()
                if run_row is None or not isinstance(run_row["project_id"], str):
                    raise ControllerError(
                        503,
                        "review_projection_invalid",
                        "Review projection unavailable",
                    )
                verdict = str(row["verdict"])
                if verdict not in KNOWN_REVIEW_VERDICTS:
                    raise ControllerError(
                        503,
                        "review_projection_invalid",
                        "Review projection unavailable",
                    )
                if command == "acknowledge-debt" and verdict != "PASS_WITH_DEBT":
                    raise ControllerError(
                        409,
                        "review_debt_not_acknowledgeable",
                        "Review debt cannot be acknowledged",
                        "Only PASS_WITH_DEBT reviews support this command.",
                    )
                if command == "request-human-review" and verdict == "HUMAN":
                    raise ControllerError(
                        409,
                        "human_review_already_required",
                        "Human review is already required",
                    )
                existing = connection.execute(
                    """
                    SELECT action_id, command
                    FROM controller_review_actions
                    WHERE review_id=?
                    """,
                    (review_id,),
                ).fetchone()
                if existing is not None:
                    if str(existing["command"]) == command:
                        raise ControllerError(
                            409,
                            "review_action_already_recorded",
                            "Review action already recorded",
                        )
                    raise ControllerError(
                        409,
                        "review_action_conflict",
                        "Review action conflicts with an existing human decision",
                        "Only one bounded human action may be recorded per review.",
                    )
                now = utc_now()
                action_id = "review-action-" + uuid.uuid4().hex
                operation_id = "operation-" + uuid.uuid4().hex
                reason_present = reason is not None
                connection.execute(
                    """
                    INSERT INTO controller_review_actions (
                        action_id, review_id, run_id, command,
                        reason_present, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, 'RECORDED', ?)
                    """,
                    (
                        action_id,
                        review_id,
                        str(row["run_id"]),
                        command,
                        1 if reason_present else 0,
                        now,
                    ),
                )
                result = {
                    "review_id": review_id,
                    "action_id": action_id,
                    "command": command,
                    "status": "recorded",
                    "reason_present": reason_present,
                }
                connection.execute(
                    """
                    INSERT INTO controller_review_operations (
                        operation_id, command_kind, state, target_id,
                        result_json, error_code, created_at, updated_at, finished_at
                    ) VALUES (?, ?, 'SUCCEEDED', ?, ?, NULL, ?, ?, ?)
                    """,
                    (
                        operation_id,
                        f"review.{command}",
                        review_id,
                        canonical_json(result),
                        now,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO controller_review_command_audit (
                        audit_id, operation_id, actor_type, actor_id,
                        action, resource_type, resource_id,
                        session_fingerprint, idempotency_key_hash,
                        request_hash, outcome, reason_present, created_at
                    ) VALUES (?, ?, 'session', 'local-controller-session',
                              ?, 'review', ?, ?, ?, ?, 'SUCCEEDED', ?, ?)
                    """,
                    (
                        "audit-" + uuid.uuid4().hex,
                        operation_id,
                        command,
                        review_id,
                        session_fp,
                        key_hash,
                        request_hash,
                        1 if reason_present else 0,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO events (
                        project_id, run_id, task_id, event_type,
                        severity, payload_json, created_at
                    ) VALUES (?, ?, NULL, ?, 'INFO', ?, ?)
                    """,
                    (
                        str(run_row["project_id"]),
                        str(row["run_id"]),
                        (
                            "REVIEW_DEBT_ACKNOWLEDGED"
                            if command == "acknowledge-debt"
                            else "REVIEW_HUMAN_REQUESTED"
                        ),
                        canonical_json(
                            {
                                "review_id": review_id,
                                "command": command,
                                "reason_present": reason_present,
                            }
                        ),
                        now,
                    ),
                )
                EventJournal.emit(
                    connection,
                    event_type=(
                        "review.debt_acknowledged"
                        if command == "acknowledge-debt"
                        else "review.human_review_requested"
                    ),
                    actor_type="operator",
                    actor_id="operator:local-controller-session",
                    aggregate_type="review",
                    aggregate_id=review_id,
                    correlation_id=EventJournal.correlation_for_causation(operation_id),
                    causation_id=operation_id,
                    project_id=str(run_row["project_id"]),
                    objective_id=None,
                    data={
                        "command": command,
                        "status": "recorded",
                        "reason_present": reason_present,
                    },
                    occurred_at=now,
                )

                operation = self._operation_payload(
                    operation_id=operation_id,
                    review_id=review_id,
                    command=command,
                    action_id=action_id,
                    reason_present=reason_present,
                    created_at=now,
                )
                revision = self._revision(operation)
                operation["resource_revision"] = revision
                payload = {
                    "data": operation,
                    "meta": meta_factory(revision),
                }
                self._complete_idempotency(
                    connection,
                    session_fp=session_fp,
                    key_hash=key_hash,
                    payload=payload,
                    operation_id=operation_id,
                )
                connection.commit()
                return 202, payload
            except sqlite3.IntegrityError as error:
                connection.rollback()
                raise ControllerError(
                    503,
                    "review_command_persistence_failed",
                    "Review command persistence failed",
                ) from error
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
                    SELECT operation_id, command_kind, state, target_id,
                           result_json, error_code,
                           created_at, updated_at, finished_at
                    FROM controller_review_operations
                    WHERE operation_id=?
                    """,
                    (operation_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise ControllerError(
                503,
                "database_unavailable",
                "Controller database unavailable",
            ) from error
        if row is None:
            return None
        try:
            result = json.loads(str(row["result_json"]))
        except json.JSONDecodeError as error:
            raise ControllerError(
                503,
                "operation_projection_invalid",
                "Operation projection unavailable",
            ) from error
        if not isinstance(result, dict):
            raise ControllerError(
                503,
                "operation_projection_invalid",
                "Operation projection unavailable",
            )
        payload = {
            "id": str(row["operation_id"]),
            "kind": str(row["command_kind"]),
            "state": str(row["state"]).lower(),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "finished_at": str(row["finished_at"]) if row["finished_at"] else None,
            "target": {"type": "review", "id": str(row["target_id"])},
            "result": result,
            "error": ({"code": str(row["error_code"])} if row["error_code"] else None),
            "legacy_projection": False,
        }
        payload["resource_revision"] = self._revision(payload)
        return payload
