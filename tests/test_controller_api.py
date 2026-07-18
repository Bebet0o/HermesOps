from __future__ import annotations

import http.client
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path

from controller_api.core import (
    ControllerError,
    ReadOnlyDatabase,
    Settings,
)
from controller_api.server import build_server

TOKEN = "a" * 64


class APIFixture:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "root"
        self.database = (
            self.root / "state" / "controller" / "hermesops.db"
        )
        self.session_file = (
            self.root / "secrets" / "controller-session"
        )
        self.project_config = (
            self.root
            / "repo"
            / "config"
            / "projects.d"
            / "alpha.toml"
        )
        (self.root / "repo").mkdir(parents=True)
        (self.root / "repo" / "VERSION").write_text(
            "0.1.0-alpha\n",
            encoding="utf-8",
        )
        self.project_config.parent.mkdir(parents=True)
        self.project_config.write_text(
            """
schema_version = 1
[git]
default_branch = "main"
""".lstrip(),
            encoding="utf-8",
        )
        self.session_file.parent.mkdir(parents=True)
        self.session_file.write_text(TOKEN + "\n", encoding="utf-8")
        os.chmod(self.session_file, 0o600)
        self.database.parent.mkdir(parents=True)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.executescript(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE projects (
                    project_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    repo_path TEXT NOT NULL UNIQUE,
                    data_path TEXT NOT NULL UNIQUE,
                    policy_id TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    config_source TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    registered_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                INSERT INTO schema_migrations VALUES (
                    1, '2026-07-18T00:00:00.000Z'
                );
                """
            )
            connection.execute(
                """
                INSERT INTO projects VALUES (
                    'alpha',
                    'Alpha Project',
                    '/workspace/alpha',
                    '/data/alpha',
                    'default',
                    1,
                    ?,
                    '0123456789abcdef0123456789abcdef',
                    '2026-07-18T00:00:00.000Z',
                    '2026-07-18T01:00:00.000Z'
                )
                """,
                (str(self.project_config),),
            )
            connection.commit()
        self.settings = Settings.from_root(
            self.root,
            host="127.0.0.1",
            port=0,
        )
        self.server = build_server(self.settings)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        self.port = int(self.server.server_address[1])

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary.cleanup()

    def request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = False,
        request_id: str | None = None,
    ) -> tuple[int, dict[str, str], dict[str, object] | None]:
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            self.port,
            timeout=5,
        )
        headers: dict[str, str] = {}
        if authenticated:
            headers["Cookie"] = f"hermesops_session={TOKEN}"
        if request_id:
            headers["X-Request-ID"] = request_id
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        response_headers = {
            key.lower(): value
            for key, value in response.getheaders()
        }
        connection.close()
        payload = json.loads(raw) if raw else None
        return response.status, response_headers, payload


class ControllerAPITest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = APIFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def test_non_loopback_bind_is_rejected(self) -> None:
        settings = Settings.from_root(
            self.fixture.root,
            host="0.0.0.0",
            port=8765,
        )
        with self.assertRaises(ControllerError) as context:
            settings.validate_bind()
        self.assertEqual(
            context.exception.code,
            "non_loopback_bind_forbidden",
        )

    def test_database_connection_is_read_only(self) -> None:
        database = ReadOnlyDatabase(self.fixture.settings)
        with closing(database.connect()) as connection:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute(
                    "INSERT INTO projects VALUES "
                    "('x','x','x','y','z',1,'s','h','a','b')"
                )

    def test_health_is_public_and_has_request_id(self) -> None:
        status, headers, payload = self.fixture.request(
            "GET",
            "/health",
            request_id="request-12345678",
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["x-request-id"], "request-12345678")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["version"], "0.1.0-alpha")

    def test_ready_checks_database_and_auth_configuration(self) -> None:
        status, _, payload = self.fixture.request("GET", "/ready")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ready")

    def test_protected_endpoint_requires_cookie(self) -> None:
        status, headers, payload = self.fixture.request(
            "GET",
            "/api/v1/projects",
        )
        self.assertEqual(status, 401)
        self.assertTrue(
            headers["content-type"].startswith(
                "application/problem+json"
            )
        )
        self.assertEqual(payload["code"], "authentication_required")

    def test_project_list_matches_contract_shape(self) -> None:
        status, headers, payload = self.fixture.request(
            "GET",
            "/api/v1/projects?limit=50",
            authenticated=True,
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["cache-control"], "no-store")
        self.assertEqual(len(payload["data"]), 1)
        project = payload["data"][0]
        self.assertEqual(project["id"], "alpha")
        self.assertEqual(project["slug"], "alpha")
        self.assertEqual(project["default_branch"], "main")
        self.assertEqual(project["state"], "enabled")
        self.assertIsInstance(project["resource_revision"], int)
        self.assertIn("request_id", payload["meta"])

    def test_project_detail_has_etag(self) -> None:
        status, headers, payload = self.fixture.request(
            "GET",
            "/api/v1/projects/alpha",
            authenticated=True,
        )
        self.assertEqual(status, 200)
        self.assertIn("etag", headers)
        self.assertEqual(payload["data"]["name"], "Alpha Project")

    def test_unknown_project_returns_problem_json(self) -> None:
        status, _, payload = self.fixture.request(
            "GET",
            "/api/v1/projects/missing",
            authenticated=True,
        )
        self.assertEqual(status, 404)
        self.assertEqual(payload["code"], "project_not_found")
        self.assertEqual(
            payload["resource"],
            {"type": "project", "id": "missing"},
        )

    def test_invalid_limit_is_rejected(self) -> None:
        status, _, payload = self.fixture.request(
            "GET",
            "/api/v1/projects?limit=1000",
            authenticated=True,
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["code"], "invalid_limit")

    def test_write_methods_are_disabled(self) -> None:
        before = self.fixture.database.read_bytes()
        status, headers, payload = self.fixture.request(
            "POST",
            "/api/v1/projects",
            authenticated=True,
        )
        after = self.fixture.database.read_bytes()
        self.assertEqual(status, 405)
        self.assertEqual(headers["allow"], "GET, HEAD")
        self.assertEqual(payload["code"], "method_not_allowed")
        self.assertEqual(before, after)

    def test_capability_flags_do_not_claim_unimplemented_features(self) -> None:
        status, _, payload = self.fixture.request(
            "GET",
            "/api/v1/system/capabilities",
            authenticated=True,
        )
        self.assertEqual(status, 200)
        features = payload["data"]["features"]
        self.assertTrue(features["read_only_controller_api"])
        self.assertFalse(features["project_writes"])
        self.assertFalse(features["websocket_events"])
        self.assertFalse(features["hermesfile_builds"])


class MissingAuthenticationConfigurationTest(unittest.TestCase):
    def test_missing_session_file_is_not_ready(self) -> None:
        fixture = APIFixture()
        try:
            fixture.session_file.unlink()
            status, _, payload = fixture.request("GET", "/ready")
            self.assertEqual(status, 503)
            self.assertEqual(payload["status"], "not_ready")
            status, _, payload = fixture.request(
                "GET",
                "/api/v1/projects",
            )
            self.assertEqual(status, 503)
            self.assertEqual(
                payload["code"],
                "controller_auth_not_configured",
            )
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
