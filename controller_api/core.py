from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import re
import sqlite3
import stat
import tomllib
import uuid
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from . import API_VERSION, SERVICE_NAME

PROJECT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
SESSION_COOKIE = "hermesops_session"


class ControllerError(RuntimeError):
    """Expected Controller API failure."""

    def __init__(
        self,
        status: int,
        code: str,
        title: str,
        detail: str = "",
        *,
        resource: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail or title)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.resource = resource


@dataclass(frozen=True)
class Settings:
    root: Path
    database: Path
    version_file: Path
    session_file: Path
    host: str = "127.0.0.1"
    port: int = 8765

    @classmethod
    def from_root(
        cls,
        root: Path,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        database: Path | None = None,
        session_file: Path | None = None,
    ) -> "Settings":
        resolved_root = root.resolve(strict=False)
        return cls(
            root=resolved_root,
            database=(
                database
                or resolved_root / "state" / "controller" / "hermesops.db"
            ).resolve(strict=False),
            version_file=(
                resolved_root / "repo" / "VERSION"
            ).resolve(strict=False),
            session_file=(
                session_file
                or resolved_root / "secrets" / "controller-session"
            ).resolve(strict=False),
            host=host,
            port=port,
        )

    @classmethod
    def from_environment(
        cls,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
    ) -> "Settings":
        root = Path(
            os.environ.get("HERMESOPS_ROOT", "/opt/docker/hermesops")
        )
        database = os.environ.get("HERMESOPS_CONTROLLER_DATABASE")
        session_file = os.environ.get(
            "HERMESOPS_CONTROLLER_SESSION_FILE"
        )
        return cls.from_root(
            root,
            host=host,
            port=port,
            database=Path(database) if database else None,
            session_file=Path(session_file) if session_file else None,
        )

    def validate_bind(self) -> None:
        try:
            address = ipaddress.ip_address(self.host)
        except ValueError as error:
            raise ControllerError(
                400,
                "invalid_bind_address",
                "Invalid bind address",
                "The Controller API accepts a literal loopback IP address only.",
            ) from error
        if not address.is_loopback:
            raise ControllerError(
                400,
                "non_loopback_bind_forbidden",
                "Non-loopback binding is forbidden",
                "Milestone 2B may listen only on a loopback address.",
            )
        if not 0 <= self.port <= 65535:
            raise ControllerError(
                400,
                "invalid_port",
                "Invalid port",
                "Port must be between 0 and 65535.",
            )


class ReadOnlyDatabase:
    """Small SQLite read adapter that cannot open a writable connection."""

    REQUIRED_TABLES = {"projects", "schema_migrations"}

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def connect(self) -> sqlite3.Connection:
        if not self.settings.database.is_file():
            raise ControllerError(
                503,
                "database_unavailable",
                "Controller database unavailable",
                "The HermesOps control database does not exist.",
            )
        uri = f"{self.settings.database.as_uri()}?mode=ro"
        connection = sqlite3.connect(
            uri,
            uri=True,
            timeout=5,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 3000")
        return connection

    def readiness(self) -> tuple[bool, str]:
        try:
            with closing(self.connect()) as connection:
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        """
                        SELECT name
                        FROM sqlite_master
                        WHERE type = 'table'
                        """
                    )
                }
                missing = sorted(self.REQUIRED_TABLES - tables)
                if missing:
                    return False, "required database tables are missing"
                row = connection.execute("PRAGMA quick_check").fetchone()
                if row is None or row[0] != "ok":
                    return False, "SQLite quick_check did not return ok"
        except (sqlite3.Error, ControllerError):
            return False, "database cannot be read"
        return True, "ready"

    def _default_branch(self, row: sqlite3.Row) -> str:
        source = Path(str(row["config_source"])).resolve(strict=False)
        allowed = (
            self.settings.root
            / "repo"
            / "config"
            / "projects.d"
        ).resolve(strict=False)
        try:
            source.relative_to(allowed)
        except ValueError:
            return "unknown"
        if source.suffix != ".toml" or not source.is_file():
            return "unknown"
        try:
            with source.open("rb") as stream:
                data = tomllib.load(stream)
            value = data.get("git", {}).get("default_branch")
        except (OSError, tomllib.TOMLDecodeError, AttributeError):
            return "unknown"
        return value if isinstance(value, str) and value else "unknown"

    @staticmethod
    def _revision(config_hash: str) -> int:
        if re.fullmatch(r"[0-9a-fA-F]{16,}", config_hash):
            return int(config_hash[:15], 16)
        digest = hashlib.sha256(config_hash.encode("utf-8")).hexdigest()
        return int(digest[:15], 16)

    def _project(self, row: sqlite3.Row) -> dict[str, Any]:
        project_id = str(row["project_id"])
        return {
            "id": project_id,
            "slug": project_id,
            "name": str(row["display_name"]),
            "state": "enabled" if int(row["enabled"]) else "disabled",
            "default_branch": self._default_branch(row),
            "policy_id": str(row["policy_id"]),
            "sandbox_profile_id": None,
            "resource_revision": self._revision(str(row["config_hash"])),
            "created_at": str(row["registered_at"]),
            "updated_at": str(row["updated_at"]),
            "repo_path": str(row["repo_path"]),
            "data_path": str(row["data_path"]),
        }

    def list_projects(
        self,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if not 1 <= limit <= 200:
            raise ControllerError(
                400,
                "invalid_limit",
                "Invalid pagination limit",
                "limit must be between 1 and 200.",
            )
        if cursor is not None and not PROJECT_ID_PATTERN.fullmatch(cursor):
            raise ControllerError(
                400,
                "invalid_cursor",
                "Invalid pagination cursor",
                "cursor must be a valid project identifier.",
            )
        sql = """
            SELECT
                project_id,
                display_name,
                repo_path,
                data_path,
                policy_id,
                enabled,
                config_source,
                config_hash,
                registered_at,
                updated_at
            FROM projects
        """
        parameters: list[Any] = []
        if cursor is not None:
            sql += " WHERE project_id > ?"
            parameters.append(cursor)
        sql += " ORDER BY project_id LIMIT ?"
        parameters.append(limit + 1)
        with closing(self.connect()) as connection:
            rows = list(connection.execute(sql, parameters))
        has_more = len(rows) > limit
        selected = rows[:limit]
        projects = [self._project(row) for row in selected]
        next_cursor = (
            str(selected[-1]["project_id"])
            if has_more and selected
            else None
        )
        return projects, next_cursor

    def get_project(self, project_id: str) -> dict[str, Any]:
        if not PROJECT_ID_PATTERN.fullmatch(project_id):
            raise ControllerError(
                400,
                "invalid_project_id",
                "Invalid project identifier",
                "The project identifier does not match the public contract.",
            )
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                SELECT
                    project_id,
                    display_name,
                    repo_path,
                    data_path,
                    policy_id,
                    enabled,
                    config_source,
                    config_hash,
                    registered_at,
                    updated_at
                FROM projects
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()
        if row is None:
            raise ControllerError(
                404,
                "project_not_found",
                "Project not found",
                f"No project exists with identifier {project_id!r}.",
                resource={"type": "project", "id": project_id},
            )
        return self._project(row)


class ControllerService:
    def __init__(self, settings: Settings) -> None:
        settings.validate_bind()
        self.settings = settings
        self.database = ReadOnlyDatabase(settings)

    def version(self) -> str:
        try:
            value = self.settings.version_file.read_text(
                encoding="utf-8"
            ).strip()
        except OSError:
            return "unknown"
        return value or "unknown"

    def session_token(self) -> str:
        path = self.settings.session_file
        if not path.is_file():
            raise ControllerError(
                503,
                "controller_auth_not_configured",
                "Controller authentication is not configured",
                "Create the Controller session file before using protected endpoints.",
            )
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode != 0o600:
            raise ControllerError(
                503,
                "controller_auth_permissions_invalid",
                "Controller authentication is unavailable",
                "The Controller session file must have mode 0600.",
            )
        try:
            token = path.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise ControllerError(
                503,
                "controller_auth_unavailable",
                "Controller authentication is unavailable",
            ) from error
        if not 32 <= len(token) <= 4096:
            raise ControllerError(
                503,
                "controller_auth_invalid",
                "Controller authentication is unavailable",
                "The configured session value has an invalid length.",
            )
        return token

    def authenticate(self, cookie_header: str | None) -> None:
        expected = self.session_token()
        supplied = ""
        if cookie_header:
            for segment in cookie_header.split(";"):
                name, separator, value = segment.strip().partition("=")
                if separator and name == SESSION_COOKIE:
                    supplied = unquote(value)
                    break
        if not supplied or not hmac.compare_digest(supplied, expected):
            raise ControllerError(
                401,
                "authentication_required",
                "Authentication required",
                "A valid HermesOps Controller session cookie is required.",
            )

    @staticmethod
    def request_id(candidate: str | None = None) -> str:
        if candidate and re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", candidate):
            return candidate
        return str(uuid.uuid4())

    @staticmethod
    def meta(
        request_id: str,
        *,
        resource_revision: int | None = None,
        next_cursor: str | None = None,
    ) -> dict[str, Any]:
        return {
            "request_id": request_id,
            "resource_revision": resource_revision,
            "next_cursor": next_cursor,
            "snapshot_sequence": None,
        }

    def readiness(self) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        database_ready, database_reason = self.database.readiness()
        if not database_ready:
            reasons.append(database_reason)
        try:
            self.session_token()
        except ControllerError as error:
            reasons.append(error.code)
        return not reasons, reasons

    def capabilities(self) -> dict[str, Any]:
        return {
            "api_versions": [API_VERSION],
            "event_schema_versions": [1],
            "hermesfile_versions": ["v0alpha1"],
            "features": {
                "read_only_controller_api": True,
                "project_reads": True,
                "project_writes": False,
                "objective_reads": False,
                "objective_writes": False,
                "websocket_events": False,
                "hermesfile_builds": False,
                "console": False,
            },
        }

    def system_status(self) -> dict[str, Any]:
        database_ready, _ = self.database.readiness()
        components = [
            {"name": SERVICE_NAME, "status": "healthy"},
            {
                "name": "sqlite",
                "status": "healthy" if database_ready else "unavailable",
            },
            {"name": "hermes-agent", "status": "unknown"},
            {"name": "sandbox-engine", "status": "unknown"},
        ]
        return {
            "status": "healthy" if database_ready else "unavailable",
            "components": components,
            "capabilities": {
                key: value
                for key, value in self.capabilities().items()
                if key != "features"
            },
        }

    @staticmethod
    def problem(
        error: ControllerError,
        request_id: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": f"urn:hermesops:problem:{error.code}",
            "title": error.title,
            "status": error.status,
            "code": error.code,
            "request_id": request_id,
        }
        if error.detail:
            payload["detail"] = error.detail
        if error.resource is not None:
            payload["resource"] = error.resource
        return payload
