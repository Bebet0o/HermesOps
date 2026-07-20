from __future__ import annotations

import json
import sqlite3
import sys
import threading
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_controller_api import APIFixture, TOKEN  # noqa: E402
from controller_api.objective_command_probe import probe_objective_commands  # noqa: E402


class ObjectiveCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = APIFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def post(
        self,
        path: str,
        body: dict[str, object],
        *,
        key: str | None = "idem-key-0001",
        csrf: str | None = None,
        authenticated: bool = True,
        origin: str | None = None,
    ):
        headers = {"Content-Type": "application/json"}
        if key is not None:
            headers["Idempotency-Key"] = key
        if csrf is not None:
            headers["X-CSRF-Token"] = csrf
        if origin is not None:
            headers["Origin"] = origin
        return self.fixture.request(
            "POST",
            path,
            authenticated=authenticated,
            headers_override=headers,
            body=json.dumps(body, separators=(",", ":")).encode(),
        )

    def csrf(self, key: str = "csrf-key-0001") -> str:
        status, _, payload = self.post(
            "/api/v1/auth/csrf",
            {},
            key=key,
        )
        self.assertEqual(status, 200)
        return str(payload["data"]["token"])

    def create_body(self) -> dict[str, object]:
        return {
            "project_ids": ["alpha"],
            "title": "Controller objective",
            "description": "Exercise secure objective mutations.",
            "priority": 90,
            "not_before": "2099-01-01T00:00:00Z",
            "max_parallel_tasks": 1,
            "planning_max_attempts": 3,
            "constraints": ["Do not start before the scheduled date"],
        }

    def create(self, *, key: str = "create-key-0001"):
        token = self.csrf(key="csrf-" + key)
        status, headers, payload = self.post(
            "/api/v1/objectives",
            self.create_body(),
            key=key,
            csrf=token,
        )
        self.assertEqual(status, 202)
        return token, headers, payload

    def test_installed_service_probe_is_safe_and_self_cancels(self) -> None:
        self.fixture.session_file.parent.chmod(0o700)
        result = probe_objective_commands(
            f"http://127.0.0.1:{self.fixture.port}",
            self.fixture.session_file,
            wait_seconds=5,
        )
        self.assertEqual(result.csrf_status, 200)
        self.assertEqual(result.create_status, 202)
        self.assertEqual(result.pause_status, 202)
        self.assertEqual(result.cancel_status, 202)
        with closing(sqlite3.connect(self.fixture.database)) as connection:
            row = connection.execute(
                "SELECT status, not_before FROM objective_queue "
                "WHERE objective LIKE 'HermesOps Controller command probe%'"
            ).fetchone()
            self.assertEqual(row[0], "CANCELLED")
            self.assertEqual(row[1], "2099-01-01T00:00:00.000Z")

    def test_csrf_requires_authentication(self) -> None:
        status, _, payload = self.post(
            "/api/v1/auth/csrf",
            {},
            authenticated=False,
        )
        self.assertEqual(status, 401)
        self.assertEqual(payload["code"], "authentication_required")

    def test_csrf_requires_valid_idempotency_key(self) -> None:
        status, _, payload = self.post(
            "/api/v1/auth/csrf",
            {},
            key=None,
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["code"], "invalid_idempotency_key")

    def test_csrf_issue_and_idempotent_replay(self) -> None:
        first = self.post("/api/v1/auth/csrf", {}, key="csrf-replay-01")
        second = self.post("/api/v1/auth/csrf", {}, key="csrf-replay-01")
        self.assertEqual(first[0], 200)
        self.assertEqual(first[2], second[2])
        self.assertRegex(first[2]["data"]["token"], r"^csrf1\.")

    def test_idempotency_key_conflict_is_rejected(self) -> None:
        self.post("/api/v1/auth/csrf", {}, key="same-key-0001")
        status, _, payload = self.post(
            "/api/v1/auth/csrf",
            {"unexpected": True},
            key="same-key-0001",
        )
        self.assertEqual(status, 400)
        # Body validation occurs before idempotency reservation for this route.
        self.assertEqual(payload["code"], "invalid_request_body")

    def test_create_requires_csrf(self) -> None:
        status, _, payload = self.post(
            "/api/v1/objectives",
            self.create_body(),
            key="create-no-csrf",
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["code"], "csrf_required")

    def test_create_rejects_invalid_csrf(self) -> None:
        status, _, payload = self.post(
            "/api/v1/objectives",
            self.create_body(),
            key="create-bad-csrf",
            csrf="csrf1.invalid",
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["code"], "csrf_invalid")

    def test_create_objective_is_atomic_and_audited(self) -> None:
        _, _, payload = self.create(key="create-atomic-01")
        operation = payload["data"]
        objective_id = operation["target"]["id"]
        self.assertEqual(operation["kind"], "objective.create")
        self.assertEqual(operation["state"], "succeeded")
        with closing(sqlite3.connect(self.fixture.database)) as connection:
            objective = connection.execute(
                "SELECT status, source, objective FROM objective_queue WHERE objective_id=?",
                (objective_id,),
            ).fetchone()
            self.assertEqual(objective[0], "QUEUED")
            self.assertEqual(objective[1], "AI")
            self.assertIn("Controller objective", objective[2])
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM controller_operations WHERE operation_id=?",
                    (operation["id"],),
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM controller_command_audit WHERE operation_id=?",
                    (operation["id"],),
                ).fetchone()[0],
                1,
            )

    def test_create_replay_is_identical_and_does_not_duplicate(self) -> None:
        token = self.csrf("csrf-create-replay")
        body = self.create_body()
        first = self.post(
            "/api/v1/objectives",
            body,
            key="create-replay-01",
            csrf=token,
        )
        second = self.post(
            "/api/v1/objectives",
            body,
            key="create-replay-01",
            csrf=token,
        )
        self.assertEqual(first[2], second[2])
        with closing(sqlite3.connect(self.fixture.database)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM objective_queue"
                ).fetchone()[0],
                1,
            )

    def test_create_reuse_with_different_body_conflicts(self) -> None:
        token = self.csrf("csrf-create-conflict")
        body = self.create_body()
        self.post(
            "/api/v1/objectives",
            body,
            key="create-conflict-01",
            csrf=token,
        )
        changed = dict(body)
        changed["priority"] = 91
        status, _, payload = self.post(
            "/api/v1/objectives",
            changed,
            key="create-conflict-01",
            csrf=token,
        )
        self.assertEqual(status, 409)
        self.assertEqual(payload["code"], "idempotency_conflict")

    def test_unknown_and_disabled_projects_fail_closed(self) -> None:
        token = self.csrf("csrf-project-errors")
        body = self.create_body()
        body["project_ids"] = ["missing"]
        status, _, payload = self.post(
            "/api/v1/objectives",
            body,
            key="unknown-project-1",
            csrf=token,
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["code"], "unknown_project")
        with closing(sqlite3.connect(self.fixture.database)) as connection:
            connection.execute("UPDATE projects SET enabled=0 WHERE project_id='alpha'")
            connection.commit()
        body["project_ids"] = ["alpha"]
        status, _, payload = self.post(
            "/api/v1/objectives",
            body,
            key="disabled-project-1",
            csrf=token,
        )
        self.assertEqual(status, 409)
        self.assertEqual(payload["code"], "project_disabled")

    def test_unknown_fields_and_oversized_objective_are_rejected(self) -> None:
        token = self.csrf("csrf-invalid-body")
        body = self.create_body()
        body["secret"] = "not allowed"
        status, _, payload = self.post(
            "/api/v1/objectives",
            body,
            key="invalid-field-1",
            csrf=token,
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["code"], "unknown_request_field")
        body = self.create_body()
        body["description"] = "x" * 16_384
        status, _, payload = self.post(
            "/api/v1/objectives",
            body,
            key="too-large-1",
            csrf=token,
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["code"], "objective_too_large")

    def test_pause_resume_cancel_lifecycle(self) -> None:
        token, _, payload = self.create(key="create-lifecycle")
        objective_id = payload["data"]["target"]["id"]
        for command, key, expected in (
            ("pause", "pause-lifecycle", "PAUSED"),
            ("resume", "resume-lifecycle", "QUEUED"),
            ("cancel", "cancel-lifecycle", "CANCELLED"),
        ):
            status, _, command_payload = self.post(
                f"/api/v1/objectives/{objective_id}/commands/{command}",
                {"reason": "safe test"},
                key=key,
                csrf=token,
            )
            self.assertEqual(status, 202)
            self.assertEqual(command_payload["data"]["kind"], f"objective.{command}")
            with closing(sqlite3.connect(self.fixture.database)) as connection:
                state = connection.execute(
                    "SELECT status FROM objective_queue WHERE objective_id=?",
                    (objective_id,),
                ).fetchone()[0]
            self.assertEqual(state, expected)

    def test_resume_from_non_paused_is_conflict(self) -> None:
        token, _, payload = self.create(key="create-resume-conflict")
        objective_id = payload["data"]["target"]["id"]
        status, _, problem = self.post(
            f"/api/v1/objectives/{objective_id}/commands/resume",
            {},
            key="resume-conflict-01",
            csrf=token,
        )
        self.assertEqual(status, 409)
        self.assertEqual(problem["code"], "objective_not_paused")

    def test_unsupported_command_is_explicitly_unavailable(self) -> None:
        token, _, payload = self.create(key="create-command-unavailable")
        objective_id = payload["data"]["target"]["id"]
        status, _, problem = self.post(
            f"/api/v1/objectives/{objective_id}/commands/archive",
            {},
            key="archive-unavailable",
            csrf=token,
        )
        self.assertEqual(status, 409)
        self.assertEqual(problem["code"], "objective_command_unavailable")

    def test_controller_operation_is_readable(self) -> None:
        _, _, payload = self.create(key="create-operation-read")
        operation_id = payload["data"]["id"]
        status, headers, operation = self.fixture.request(
            "GET",
            f"/api/v1/operations/{operation_id}",
            authenticated=True,
        )
        self.assertEqual(status, 200)
        self.assertEqual(operation["data"]["id"], operation_id)
        self.assertIn("etag", headers)

    def test_session_rotation_invalidates_csrf_and_idempotency_namespace(self) -> None:
        token = self.csrf("csrf-before-rotation")
        new_token = "b" * 64
        self.fixture.session_file.write_text(new_token + "\n", encoding="utf-8")
        status, _, payload = self.post(
            "/api/v1/objectives",
            self.create_body(),
            key="after-rotation-01",
            csrf=token,
        )
        self.assertEqual(status, 401)
        self.assertEqual(payload["code"], "authentication_required")

    def test_cross_origin_request_is_rejected(self) -> None:
        status, _, payload = self.post(
            "/api/v1/auth/csrf",
            {},
            key="origin-reject-01",
            origin="https://evil.invalid",
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["code"], "origin_forbidden")

    def test_audit_and_idempotency_do_not_store_raw_key_or_reason(self) -> None:
        token, _, payload = self.create(key="raw-secret-key-01")
        objective_id = payload["data"]["target"]["id"]
        self.post(
            f"/api/v1/objectives/{objective_id}/commands/pause",
            {"reason": "private operator explanation"},
            key="private-command-key-01",
            csrf=token,
        )
        with closing(sqlite3.connect(self.fixture.database)) as connection:
            values = "\n".join(
                str(value)
                for table in (
                    "controller_idempotency",
                    "controller_command_audit",
                )
                for row in connection.execute(f"SELECT * FROM {table}")
                for value in row
                if value is not None
            )
        self.assertNotIn("private-command-key-01", values)
        self.assertNotIn("private operator explanation", values)

    def test_concurrent_identical_retry_creates_one_objective(self) -> None:
        token = self.csrf("csrf-concurrent")
        body = self.create_body()
        results: list[tuple[int, object]] = []
        lock = threading.Lock()

        def invoke() -> None:
            status, _, payload = self.post(
                "/api/v1/objectives",
                body,
                key="concurrent-create-01",
                csrf=token,
            )
            with lock:
                results.append((status, payload))

        threads = [threading.Thread(target=invoke) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual([item[0] for item in results], [202, 202])
        self.assertEqual(results[0][1], results[1][1])
        with closing(sqlite3.connect(self.fixture.database)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM objective_queue").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
