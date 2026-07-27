from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import tomllib
import uuid
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from .core import ControllerError, PROJECT_ID_PATTERN, Settings
from .event_journal import EventJournal
from .objective_commands import canonical_json, utc_now

IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._~:-]{8,200}$")
POLICY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
PROFILE_NAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
OPERATION_ID_PATTERN = re.compile(r"^operation-[0-9a-f]{32}$")
SAFE_BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")
ACTIVE_RUN_STATES = {
    "QUEUED", "SNAPSHOTTING", "RUNNING", "REVIEWING", "WAITING_HUMAN",
    "COMMITTING", "RECOVERING",
}
ACTIVE_OBJECTIVE_STATES = {
    "QUEUED", "PLANNING", "PLANNED", "RUNNING", "PAUSE_REQUESTED",
    "PAUSED", "CANCEL_REQUESTED", "BLOCKED",
}
MAX_CONFIG_BYTES = 128 * 1024
MAX_NAME_LENGTH = 120
MAX_URL_LENGTH = 2048


class ProjectCommandStore:
    REQUIRED_TABLES = {
        "projects",
        "controller_project_operations",
        "controller_project_idempotency",
        "controller_project_command_audit",
        "controller_event_journal",
        "schema_migrations",
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repo_root = settings.root / "repo"
        self.projects_directory = self.repo_root / "config" / "projects.d"
        self.policies_directory = self.repo_root / "config" / "policies"
        self.workspace_root = settings.root / "workspaces"
        self.data_root = settings.root / "project-data"
        self.runtime_root = settings.root / "runtime" / "project-operations"

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.settings.database,
            timeout=10,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def readiness(self) -> tuple[bool, str]:
        try:
            with closing(self.connect()) as connection:
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                if self.REQUIRED_TABLES - tables:
                    return False, "project lifecycle tables are missing"
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if version < 21:
                    return False, "project lifecycle migration is missing"
                connection.execute(
                    "SELECT resource_revision, archived, default_branch "
                    "FROM projects LIMIT 1"
                ).fetchone()
        except (sqlite3.Error, OSError):
            return False, "project lifecycle persistence cannot be read"
        return True, "ready"

    @staticmethod
    def _session_fingerprint(session_token: str) -> str:
        return hashlib.sha256(session_token.encode("ascii")).hexdigest()[:32]

    @staticmethod
    def _key_hash(session_token: str, key: str) -> str:
        return hmac.new(
            session_token.encode("ascii"),
            b"hermesops-project-idempotency-v1\0" + key.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _request_hash(method: str, route: str, body: dict[str, Any]) -> str:
        encoded = canonical_json({"method": method, "route": route, "body": body})
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def validate_idempotency_key(value: str | None) -> str:
        if value is None or IDEMPOTENCY_KEY_PATTERN.fullmatch(value) is None:
            raise ControllerError(
                400,
                "invalid_idempotency_key",
                "Invalid Idempotency-Key",
                "Idempotency-Key must contain 8..200 safe ASCII characters.",
            )
        return value

    @staticmethod
    def _public_text(value: Any, *, field: str, maximum: int) -> str:
        if not isinstance(value, str):
            raise ControllerError(400, f"invalid_{field}", f"Invalid {field.replace('_', ' ')}")
        normalized = value.strip()
        if (
            not normalized
            or len(normalized) > maximum
            or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
        ):
            raise ControllerError(400, f"invalid_{field}", f"Invalid {field.replace('_', ' ')}")
        return normalized

    @staticmethod
    def _validate_slug(value: Any) -> str:
        if not isinstance(value, str) or PROJECT_ID_PATTERN.fullmatch(value) is None:
            raise ControllerError(400, "invalid_project_id", "Invalid project identifier")
        return value

    @staticmethod
    def _validate_branch(value: Any) -> str:
        branch = ProjectCommandStore._public_text(value, field="default_branch", maximum=255)
        if (
            SAFE_BRANCH_PATTERN.fullmatch(branch) is None
            or branch.startswith("-")
            or branch.endswith(".")
            or ".." in branch
            or "//" in branch
            or "@{" in branch
            or branch.endswith("/")
            or branch.endswith(".lock")
            or "\\" in branch
            or " " in branch
            or "~" in branch
            or "^" in branch
            or ":" in branch
            or "?" in branch
            or "*" in branch
            or "[" in branch
        ):
            raise ControllerError(400, "invalid_default_branch", "Invalid default branch")
        return branch

    def _policy(self, value: Any) -> tuple[str, dict[str, Any]]:
        if not isinstance(value, str) or POLICY_ID_PATTERN.fullmatch(value) is None:
            raise ControllerError(400, "invalid_policy_id", "Invalid policy identifier")
        path = self.policies_directory / f"{value}.toml"
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(self.policies_directory.resolve(strict=True))
            metadata = resolved.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_size > MAX_CONFIG_BYTES:
                raise OSError("unsafe policy")
            with resolved.open("rb") as stream:
                data = tomllib.load(stream)
        except (OSError, ValueError, tomllib.TOMLDecodeError) as error:
            raise ControllerError(400, "policy_not_found", "Project policy not found") from error
        if data.get("schema_version") != 1 or data.get("policy_id") != value:
            raise ControllerError(503, "policy_invalid", "Project policy is invalid")
        return value, data

    def _sandbox_profile(self, connection: sqlite3.Connection, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or PROFILE_NAME_PATTERN.fullmatch(value) is None:
            raise ControllerError(400, "invalid_sandbox_profile_id", "Invalid sandbox profile identifier")
        row = connection.execute(
            "SELECT state FROM sandbox_profiles WHERE profile_name=?",
            (value,),
        ).fetchone()
        if row is None:
            raise ControllerError(404, "sandbox_profile_not_found", "Sandbox profile not found")
        if str(row["state"]) == "archived":
            raise ControllerError(409, "sandbox_profile_archived", "Sandbox profile is archived")
        return value

    @staticmethod
    def _repository_url(value: Any, mode: str) -> str | None:
        if mode != "clone":
            if value is not None:
                raise ControllerError(400, "repository_url_not_allowed", "Repository URL is not allowed")
            return None
        if not isinstance(value, str):
            raise ControllerError(400, "repository_url_required", "Repository URL is required")
        url = value.strip()
        if not url or len(url) > MAX_URL_LENGTH or any(ord(c) < 32 or ord(c) == 127 for c in url):
            raise ControllerError(400, "invalid_repository_url", "Invalid repository URL")
        parsed = urlsplit(url)
        valid_https = (
            parsed.scheme == "https"
            and parsed.hostname is not None
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment
        )
        valid_ssh = (
            parsed.scheme == "ssh"
            and parsed.hostname is not None
            and parsed.password is None
            and not parsed.fragment
        )
        valid_scp = re.fullmatch(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:[A-Za-z0-9._~/-]+", url) is not None
        if not (valid_https or valid_ssh or valid_scp):
            raise ControllerError(400, "invalid_repository_url", "Invalid repository URL")
        return url

    @staticmethod
    def _assert_directory(path: Path, *, must_exist: bool) -> None:
        if path.is_symlink():
            raise ControllerError(409, "unsafe_project_path", "Project path is unsafe")
        if must_exist:
            try:
                metadata = path.lstat()
            except OSError as error:
                raise ControllerError(409, "project_repository_missing", "Project repository is missing") from error
            if not stat.S_ISDIR(metadata.st_mode):
                raise ControllerError(409, "unsafe_project_path", "Project path is unsafe")
        elif path.exists():
            raise ControllerError(409, "project_path_conflict", "Project path already exists")

    @staticmethod
    def _run_git(arguments: list[str], *, timeout: int = 30, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_ASKPASS": "/bin/false",
                "SSH_ASKPASS": "/bin/false",
                "LC_ALL": "C",
            }
        )
        try:
            return subprocess.run(
                ["git", *arguments],
                cwd=cwd,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ControllerError(503, "git_unavailable", "Git operation is unavailable") from error

    def _validate_repository(self, path: Path, branch: str, *, require_clean: bool) -> dict[str, Any]:
        inside = self._run_git(["-C", str(path), "rev-parse", "--is-inside-work-tree"])
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            raise ControllerError(409, "repository_invalid", "Project repository is invalid")
        bare = self._run_git(["-C", str(path), "rev-parse", "--is-bare-repository"])
        if bare.returncode != 0 or bare.stdout.strip() != "false":
            raise ControllerError(409, "repository_invalid", "Project repository is invalid")
        branch_check = self._run_git(["check-ref-format", "--branch", branch])
        if branch_check.returncode != 0:
            raise ControllerError(400, "invalid_default_branch", "Invalid default branch")
        refs = self._run_git(["-C", str(path), "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"])
        unborn = self._run_git(["-C", str(path), "symbolic-ref", "--quiet", "--short", "HEAD"])
        branch_exists = refs.returncode == 0 or (unborn.returncode == 0 and unborn.stdout.strip() == branch)
        if not branch_exists:
            raise ControllerError(409, "default_branch_missing", "Default branch is missing")
        status = self._run_git(["-C", str(path), "status", "--porcelain=v1", "--untracked-files=all"])
        if status.returncode != 0:
            raise ControllerError(409, "repository_status_unavailable", "Repository status is unavailable")
        dirty = bool(status.stdout)
        if require_clean and dirty:
            raise ControllerError(409, "repository_dirty", "Project repository is not clean")
        return {"clean": not dirty, "default_branch": branch}

    @staticmethod
    def _toml_string(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)

    def _render_config(
        self,
        *,
        project_id: str,
        name: str,
        enabled: bool,
        policy_id: str,
        repo_path: Path,
        data_path: Path,
        default_branch: str,
        policy: dict[str, Any],
    ) -> bytes:
        execution = policy.get("execution") if isinstance(policy.get("execution"), dict) else {}
        review = policy.get("review") if isinstance(policy.get("review"), dict) else {}
        writer_concurrency = int(execution.get("writer_concurrency", 1))
        max_parallel_tasks = int(execution.get("max_parallel_tasks", 3))
        review_required = bool(review.get("required", True))
        if writer_concurrency != 1 or not 1 <= max_parallel_tasks <= 64 or not review_required:
            raise ControllerError(503, "policy_invalid", "Project policy is invalid")
        text = f'''schema_version = 1

[project]
id = {self._toml_string(project_id)}
name = {self._toml_string(name)}
enabled = {str(enabled).lower()}
policy = {self._toml_string(policy_id)}

[paths]
repo = {self._toml_string(str(repo_path))}
data = {self._toml_string(str(data_path))}

[git]
default_branch = {self._toml_string(default_branch)}
allow_push = false
require_clean = true

[execution]
writer_concurrency = 1
max_parallel_tasks = {max_parallel_tasks}

[review]
required = true
'''
        encoded = text.encode("utf-8")
        if len(encoded) > MAX_CONFIG_BYTES:
            raise ControllerError(500, "project_config_too_large", "Project configuration is too large")
        return encoded

    @staticmethod
    def _atomic_replace(path: Path, data: bytes, mode: int = 0o600) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary_path = Path(temporary)
        try:
            os.fchmod(descriptor, mode)
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, path)
            directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _read_regular(path: Path) -> bytes:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise ControllerError(409, "project_config_unavailable", "Project configuration is unavailable") from error
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_size > MAX_CONFIG_BYTES:
                raise ControllerError(409, "project_config_unsafe", "Project configuration is unsafe")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                return stream.read(MAX_CONFIG_BYTES + 1)
        finally:
            os.close(descriptor)

    @staticmethod
    def _parse_if_match(value: str | None) -> int:
        if value is None or re.fullmatch(r'"[1-9][0-9]*"', value) is None:
            raise ControllerError(428, "precondition_required", "If-Match is required")
        revision = int(value[1:-1])
        if revision > 2**63 - 1:
            raise ControllerError(400, "invalid_if_match", "Invalid If-Match")
        return revision

    def _project_row(self, connection: sqlite3.Connection, project_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if row is None:
            raise ControllerError(
                404,
                "project_not_found",
                "Project not found",
                resource={"type": "project", "id": project_id},
            )
        return row

    @staticmethod
    def _project_state(row: sqlite3.Row) -> str:
        if int(row["archived"]):
            return "archived"
        return "enabled" if int(row["enabled"]) else "disabled"

    @staticmethod
    def _operation_payload(row: sqlite3.Row) -> dict[str, Any]:
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
            "target": {"type": "project", "id": str(row["target_id"])},
            "result": result,
            "error": {"code": str(row["error_code"])} if row["error_code"] else None,
        }
        digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        payload["resource_revision"] = int(digest[:15], 16)
        return payload

    @contextmanager
    def _create_serialization(self):
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        lock_path = self.runtime_root / "project-create.lock"
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(lock_path, flags, 0o600)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ControllerError(503, "project_lock_unsafe", "Project creation lock is unsafe")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _lookup_replay(
        self,
        *,
        session_token: str,
        idempotency_key: str,
        method: str,
        route: str,
        body: dict[str, Any],
    ) -> dict[str, Any] | None:
        session_fp = self._session_fingerprint(session_token)
        key_hash = self._key_hash(session_token, idempotency_key)
        request_hash = self._request_hash(method, route, body)
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT method, route, request_hash, response_json "
                "FROM controller_project_idempotency "
                "WHERE session_fingerprint=? AND key_hash=?",
                (session_fp, key_hash),
            ).fetchone()
        if row is None:
            return None
        if (
            str(row["method"]) != method
            or str(row["route"]) != route
            or str(row["request_hash"]) != request_hash
        ):
            raise ControllerError(409, "idempotency_conflict", "Idempotency key conflict")
        if row["response_json"] is None:
            raise ControllerError(409, "idempotency_reservation_invalid", "Idempotency reservation is incomplete")
        try:
            replay = json.loads(str(row["response_json"]))
        except json.JSONDecodeError as error:
            raise ControllerError(503, "idempotency_projection_invalid", "Idempotency projection unavailable") from error
        if not isinstance(replay, dict):
            raise ControllerError(503, "idempotency_projection_invalid", "Idempotency projection unavailable")
        return replay

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
        request_hash = self._request_hash(method, route, body)
        row = connection.execute(
            "SELECT method, route, request_hash, response_json "
            "FROM controller_project_idempotency "
            "WHERE session_fingerprint=? AND key_hash=?",
            (session_fp, key_hash),
        ).fetchone()
        if row is not None:
            if (
                str(row["method"]) != method
                or str(row["route"]) != route
                or str(row["request_hash"]) != request_hash
            ):
                raise ControllerError(409, "idempotency_conflict", "Idempotency key conflict")
            if row["response_json"] is None:
                raise ControllerError(409, "idempotency_reservation_invalid", "Idempotency reservation is incomplete")
            try:
                replay = json.loads(str(row["response_json"]))
            except json.JSONDecodeError as error:
                raise ControllerError(503, "idempotency_projection_invalid", "Idempotency projection unavailable") from error
            if not isinstance(replay, dict):
                raise ControllerError(503, "idempotency_projection_invalid", "Idempotency projection unavailable")
            return replay, session_fp, key_hash, request_hash
        connection.execute(
            "INSERT INTO controller_project_idempotency ("
            "session_fingerprint,key_hash,method,route,request_hash,created_at"
            ") VALUES (?,?,?,?,?,?)",
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
        operation_id: str,
        now: str,
    ) -> None:
        connection.execute(
            "UPDATE controller_project_idempotency SET response_status=?, response_json=?, "
            "operation_id=?, completed_at=? WHERE session_fingerprint=? AND key_hash=?",
            (status, canonical_json(payload), operation_id, now, session_fp, key_hash),
        )

    @staticmethod
    def _record_operation(
        connection: sqlite3.Connection,
        *,
        operation_id: str,
        kind: str,
        project_id: str,
        result: dict[str, Any],
        now: str,
    ) -> dict[str, Any]:
        connection.execute(
            "INSERT INTO controller_project_operations ("
            "operation_id,command_kind,state,target_id,result_json,created_at,updated_at,finished_at"
            ") VALUES (?,?, 'SUCCEEDED', ?, ?, ?, ?, ?)",
            (operation_id, kind, project_id, canonical_json(result), now, now, now),
        )
        row = connection.execute(
            "SELECT * FROM controller_project_operations WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
        assert row is not None
        return ProjectCommandStore._operation_payload(row)

    @staticmethod
    def _audit(
        connection: sqlite3.Connection,
        *,
        operation_id: str,
        action: str,
        project_id: str,
        session_fp: str,
        key_hash: str,
        request_hash: str,
        reason_present: bool,
        now: str,
    ) -> None:
        connection.execute(
            "INSERT INTO controller_project_command_audit ("
            "audit_id,operation_id,actor_type,actor_id,action,resource_type,resource_id,"
            "session_fingerprint,idempotency_key_hash,request_hash,outcome,reason_present,created_at"
            ") VALUES (?,?,'session','operator',?,'project',?,?,?,?, 'SUCCEEDED',?,?)",
            (
                "audit-" + uuid.uuid4().hex,
                operation_id,
                action,
                project_id,
                session_fp,
                key_hash,
                request_hash,
                int(reason_present),
                now,
            ),
        )

    @staticmethod
    def _emit(
        connection: sqlite3.Connection,
        *,
        event_type: str,
        project_id: str,
        revision: int,
        operation_id: str,
        data: dict[str, Any],
        now: str,
    ) -> None:
        EventJournal.emit(
            connection,
            event_type=event_type,
            actor_type="operator",
            actor_id="operator",
            aggregate_type="project",
            aggregate_id=project_id,
            correlation_id="corr_" + uuid.uuid4().hex,
            causation_id=operation_id,
            data=data,
            project_id=project_id,
            occurred_at=now,
        )

    @staticmethod
    def _validate_reason_body(body: dict[str, Any]) -> str | None:
        if set(body) - {"reason"}:
            raise ControllerError(400, "unknown_field", "Unknown request field")
        reason = body.get("reason")
        if reason is None:
            return None
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
            raise ControllerError(400, "invalid_reason", "Invalid command reason")
        return reason.strip()

    def _active_work(self, connection: sqlite3.Connection, project_id: str) -> bool:
        if connection.execute(
            "SELECT 1 FROM project_locks WHERE project_id=? LIMIT 1", (project_id,)
        ).fetchone():
            return True
        placeholders = ",".join("?" for _ in ACTIVE_RUN_STATES)
        if connection.execute(
            f"SELECT 1 FROM runs WHERE project_id=? AND status IN ({placeholders}) LIMIT 1",
            (project_id, *sorted(ACTIVE_RUN_STATES)),
        ).fetchone():
            return True
        for row in connection.execute(
            "SELECT status, project_scope_json FROM objective_queue "
            "WHERE status NOT IN ('COMPLETED','FAILED','CANCELLED','ARCHIVED')"
        ):
            try:
                projects = json.loads(str(row["project_scope_json"]))
            except json.JSONDecodeError:
                raise ControllerError(503, "objective_projection_invalid", "Objective projection unavailable")
            if str(row["status"]) in ACTIVE_OBJECTIVE_STATES and isinstance(projects, list) and project_id in projects:
                return True
        return False

    def create_project(
        self,
        *,
        session_token: str,
        idempotency_key: str,
        route: str,
        body: dict[str, Any],
        meta_factory: Callable[[int | None], dict[str, Any]],
    ) -> tuple[int, dict[str, Any]]:
        self.validate_idempotency_key(idempotency_key)
        if set(body) != {"name", "slug", "repository", "policy_id", "sandbox_profile_id"}:
            raise ControllerError(400, "invalid_project_create", "Invalid project creation request")
        project_id = self._validate_slug(body.get("slug"))
        name = self._public_text(body.get("name"), field="project_name", maximum=MAX_NAME_LENGTH)
        repository = body.get("repository")
        if not isinstance(repository, dict) or set(repository) != {"mode", "url", "default_branch"}:
            raise ControllerError(400, "invalid_repository", "Invalid repository request")
        mode = repository.get("mode")
        if mode not in {"clone", "existing", "initialize"}:
            raise ControllerError(400, "invalid_repository_mode", "Invalid repository mode")
        branch = self._validate_branch(repository.get("default_branch"))
        url = self._repository_url(repository.get("url"), mode)
        policy_id, policy = self._policy(body.get("policy_id"))
        repo_path = self.workspace_root / project_id
        data_path = self.data_root / project_id
        config_path = self.projects_directory / f"{project_id}.toml"
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.projects_directory.mkdir(parents=True, exist_ok=True)
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        if any(path.is_symlink() for path in (self.workspace_root, self.data_root, self.projects_directory)):
            raise ControllerError(503, "project_root_unsafe", "Project root is unsafe")

        with self._create_serialization():
            replay = self._lookup_replay(
                session_token=session_token,
                idempotency_key=idempotency_key,
                method="POST",
                route=route,
                body=body,
            )
            if replay is not None:
                return 202, replay
            stage = Path(tempfile.mkdtemp(prefix=f"{project_id}-", dir=self.runtime_root))
            staged_repo = stage / "repo"
            staged_data = stage / "data"
            created_repo = False
            created_data = False
            created_config = False
            try:
                self._assert_directory(config_path, must_exist=False)
                self._assert_directory(data_path, must_exist=False)
                if mode == "existing":
                    self._assert_directory(repo_path, must_exist=True)
                else:
                    self._assert_directory(repo_path, must_exist=False)
                    if mode == "initialize":
                        staged_repo.mkdir(mode=0o750)
                        result = self._run_git(["init", "--initial-branch", branch, str(staged_repo)])
                    else:
                        result = self._run_git(
                            ["clone", "--origin", "origin", "--branch", branch, "--single-branch", "--no-tags", url or "", str(staged_repo)],
                            timeout=120,
                        )
                    if result.returncode != 0:
                        raise ControllerError(409, "repository_prepare_failed", "Repository could not be prepared")
                repository_path = repo_path if mode == "existing" else staged_repo
                self._validate_repository(repository_path, branch, require_clean=True)
                staged_data.mkdir(mode=0o750)

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
                        if connection.execute("SELECT 1 FROM projects WHERE project_id=?", (project_id,)).fetchone():
                            raise ControllerError(409, "project_exists", "Project already exists")
                        sandbox_profile = self._sandbox_profile(connection, body.get("sandbox_profile_id"))
                        config = self._render_config(
                            project_id=project_id,
                            name=name,
                            enabled=False,
                            policy_id=policy_id,
                            repo_path=repo_path,
                            data_path=data_path,
                            default_branch=branch,
                            policy=policy,
                        )
                        if mode != "existing":
                            os.replace(staged_repo, repo_path)
                            created_repo = True
                        os.replace(staged_data, data_path)
                        created_data = True
                        self._atomic_replace(config_path, config)
                        created_config = True
                        config_hash = hashlib.sha256(config).hexdigest()
                        now = utc_now()
                        connection.execute(
                            "INSERT INTO projects ("
                            "project_id,display_name,repo_path,data_path,policy_id,enabled,config_source,config_hash,"
                            "registered_at,updated_at,default_branch,sandbox_profile_id,archived,repository_mode,resource_revision"
                            ") VALUES (?,?,?,?,?,0,?,?,?,?,?,?,0,?,1)",
                            (
                                project_id,
                                name,
                                str(repo_path),
                                str(data_path),
                                policy_id,
                                str(config_path),
                                config_hash,
                                now,
                                now,
                                branch,
                                sandbox_profile,
                                mode,
                            ),
                        )
                        operation_id = "operation-" + uuid.uuid4().hex
                        operation = self._record_operation(
                            connection,
                            operation_id=operation_id,
                            kind="project.create",
                            project_id=project_id,
                            result={"project_id": project_id, "state": "disabled", "resource_revision": 1},
                            now=now,
                        )
                        self._audit(
                            connection,
                            operation_id=operation_id,
                            action="project.create",
                            project_id=project_id,
                            session_fp=session_fp,
                            key_hash=key_hash,
                            request_hash=request_hash,
                            reason_present=False,
                            now=now,
                        )
                        self._emit(
                            connection,
                            event_type="project.created",
                            project_id=project_id,
                            revision=1,
                            operation_id=operation_id,
                            data={"state": "disabled", "repository_mode": mode},
                            now=now,
                        )
                        payload = {"data": operation, "meta": meta_factory(1)}
                        self._complete_idempotency(
                            connection,
                            session_fp=session_fp,
                            key_hash=key_hash,
                            status=202,
                            payload=payload,
                            operation_id=operation_id,
                            now=now,
                        )
                        connection.commit()
                        return 202, payload
                    except Exception:
                        connection.rollback()
                        raise
            except Exception:
                if created_config:
                    try:
                        config_path.unlink()
                    except OSError:
                        pass
                if created_data:
                    shutil.rmtree(data_path, ignore_errors=True)
                if created_repo:
                    shutil.rmtree(repo_path, ignore_errors=True)
                raise
            finally:
                shutil.rmtree(stage, ignore_errors=True)

    def update_project(
        self,
        *,
        session_token: str,
        idempotency_key: str,
        route: str,
        project_id: str,
        if_match: str | None,
        body: dict[str, Any],
        meta_factory: Callable[[int | None], dict[str, Any]],
    ) -> tuple[int, dict[str, Any]]:
        self.validate_idempotency_key(idempotency_key)
        project_id = self._validate_slug(project_id)
        expected_revision = self._parse_if_match(if_match)
        allowed = {"name", "policy_id", "sandbox_profile_id"}
        if not body or set(body) - allowed:
            raise ControllerError(400, "invalid_project_update", "Invalid project update request")
        with closing(self.connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            backup: bytes | None = None
            config_path: Path | None = None
            try:
                replay, session_fp, key_hash, request_hash = self._replay_or_reserve(
                    connection,
                    session_token=session_token,
                    idempotency_key=idempotency_key,
                    method="PATCH",
                    route=route,
                    body=body,
                )
                if replay is not None:
                    connection.commit()
                    return 202, replay
                row = self._project_row(connection, project_id)
                current_revision = int(row["resource_revision"])
                if current_revision != expected_revision:
                    raise ControllerError(409, "resource_revision_conflict", "Project revision conflict")
                if int(row["archived"]):
                    raise ControllerError(409, "project_archived", "Project is archived")
                name = (
                    self._public_text(body["name"], field="project_name", maximum=MAX_NAME_LENGTH)
                    if "name" in body
                    else str(row["display_name"])
                )
                policy_id, policy = self._policy(body.get("policy_id", str(row["policy_id"])))
                sandbox_profile = (
                    self._sandbox_profile(connection, body["sandbox_profile_id"])
                    if "sandbox_profile_id" in body
                    else (str(row["sandbox_profile_id"]) if row["sandbox_profile_id"] is not None else None)
                )
                config_path = Path(str(row["config_source"]))
                backup = self._read_regular(config_path)
                config = self._render_config(
                    project_id=project_id,
                    name=name,
                    enabled=bool(row["enabled"]),
                    policy_id=policy_id,
                    repo_path=Path(str(row["repo_path"])),
                    data_path=Path(str(row["data_path"])),
                    default_branch=str(row["default_branch"]),
                    policy=policy,
                )
                new_revision = current_revision + 1
                now = utc_now()
                self._atomic_replace(config_path, config)
                connection.execute(
                    "UPDATE projects SET display_name=?, policy_id=?, sandbox_profile_id=?, "
                    "config_hash=?, updated_at=?, resource_revision=? WHERE project_id=?",
                    (name, policy_id, sandbox_profile, hashlib.sha256(config).hexdigest(), now, new_revision, project_id),
                )
                operation_id = "operation-" + uuid.uuid4().hex
                operation = self._record_operation(
                    connection,
                    operation_id=operation_id,
                    kind="project.update",
                    project_id=project_id,
                    result={"project_id": project_id, "state": self._project_state(row), "resource_revision": new_revision},
                    now=now,
                )
                self._audit(
                    connection,
                    operation_id=operation_id,
                    action="project.update",
                    project_id=project_id,
                    session_fp=session_fp,
                    key_hash=key_hash,
                    request_hash=request_hash,
                    reason_present=False,
                    now=now,
                )
                self._emit(
                    connection,
                    event_type="project.updated",
                    project_id=project_id,
                    revision=new_revision,
                    operation_id=operation_id,
                    data={"fields": sorted(body)},
                    now=now,
                )
                payload = {"data": operation, "meta": meta_factory(new_revision)}
                self._complete_idempotency(
                    connection,
                    session_fp=session_fp,
                    key_hash=key_hash,
                    status=202,
                    payload=payload,
                    operation_id=operation_id,
                    now=now,
                )
                connection.commit()
                return 202, payload
            except Exception:
                connection.rollback()
                if backup is not None and config_path is not None:
                    try:
                        self._atomic_replace(config_path, backup)
                    except Exception:
                        pass
                raise

    def command_project(
        self,
        *,
        session_token: str,
        idempotency_key: str,
        route: str,
        project_id: str,
        command: str,
        if_match: str | None,
        body: dict[str, Any],
        meta_factory: Callable[[int | None], dict[str, Any]],
    ) -> tuple[int, dict[str, Any]]:
        self.validate_idempotency_key(idempotency_key)
        project_id = self._validate_slug(project_id)
        expected_revision = self._parse_if_match(if_match)
        if command not in {"enable", "disable", "rescan", "archive"}:
            raise ControllerError(
                409,
                "project_command_unavailable",
                "Project command unavailable",
                "Project delete and remote/default-branch mutation are unavailable in milestone 2S.",
            )
        reason = self._validate_reason_body(body)
        with closing(self.connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            backup: bytes | None = None
            config_path: Path | None = None
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
                row = self._project_row(connection, project_id)
                current_revision = int(row["resource_revision"])
                if current_revision != expected_revision:
                    raise ControllerError(409, "resource_revision_conflict", "Project revision conflict")
                old_state = self._project_state(row)
                if int(row["archived"]) and command != "rescan":
                    raise ControllerError(409, "project_archived", "Project is archived")
                if command in {"disable", "archive"} and self._active_work(connection, project_id):
                    raise ControllerError(409, "project_has_active_work", "Project has active work")
                repo_path = Path(str(row["repo_path"]))
                branch = str(row["default_branch"])
                self._assert_directory(repo_path, must_exist=True)
                health = self._validate_repository(
                    repo_path,
                    branch,
                    require_clean=(command in {"enable", "rescan"}),
                )
                config_path = Path(str(row["config_source"]))
                backup = self._read_regular(config_path)
                policy_id, policy = self._policy(str(row["policy_id"]))
                enabled = bool(row["enabled"])
                archived = int(row["archived"])
                if command == "enable":
                    enabled = True
                elif command == "disable":
                    enabled = False
                elif command == "archive":
                    enabled = False
                    archived = 1
                config = self._render_config(
                    project_id=project_id,
                    name=str(row["display_name"]),
                    enabled=enabled,
                    policy_id=policy_id,
                    repo_path=repo_path,
                    data_path=Path(str(row["data_path"])),
                    default_branch=branch,
                    policy=policy,
                )
                new_hash = hashlib.sha256(config).hexdigest()
                changed = (
                    int(enabled) != int(row["enabled"])
                    or archived != int(row["archived"])
                    or new_hash != str(row["config_hash"])
                )
                new_revision = current_revision + (1 if changed else 0)
                now = utc_now()
                if changed:
                    self._atomic_replace(config_path, config)
                    connection.execute(
                        "UPDATE projects SET enabled=?, archived=?, config_hash=?, updated_at=?, "
                        "resource_revision=? WHERE project_id=?",
                        (int(enabled), archived, new_hash, now, new_revision, project_id),
                    )
                new_state = "archived" if archived else ("enabled" if enabled else "disabled")
                operation_id = "operation-" + uuid.uuid4().hex
                kind = f"project.{command}"
                operation = self._record_operation(
                    connection,
                    operation_id=operation_id,
                    kind=kind,
                    project_id=project_id,
                    result={
                        "project_id": project_id,
                        "state": new_state,
                        "resource_revision": new_revision,
                        "repository_clean": bool(health["clean"]),
                    },
                    now=now,
                )
                self._audit(
                    connection,
                    operation_id=operation_id,
                    action=kind,
                    project_id=project_id,
                    session_fp=session_fp,
                    key_hash=key_hash,
                    request_hash=request_hash,
                    reason_present=reason is not None,
                    now=now,
                )
                event_type = {
                    "enable": "project.enabled",
                    "disable": "project.disabled",
                    "archive": "project.archived",
                    "rescan": "project.rescanned",
                }[command]
                self._emit(
                    connection,
                    event_type=event_type,
                    project_id=project_id,
                    revision=max(new_revision, 1),
                    operation_id=operation_id,
                    data={"old_state": old_state, "new_state": new_state, "reason_present": reason is not None},
                    now=now,
                )
                payload = {"data": operation, "meta": meta_factory(new_revision)}
                self._complete_idempotency(
                    connection,
                    session_fp=session_fp,
                    key_hash=key_hash,
                    status=202,
                    payload=payload,
                    operation_id=operation_id,
                    now=now,
                )
                connection.commit()
                return 202, payload
            except Exception:
                connection.rollback()
                if backup is not None and config_path is not None:
                    try:
                        self._atomic_replace(config_path, backup)
                    except Exception:
                        pass
                raise

    def get_operation(self, operation_id: str) -> dict[str, Any] | None:
        if OPERATION_ID_PATTERN.fullmatch(operation_id) is None:
            return None
        try:
            with closing(self.connect()) as connection:
                row = connection.execute(
                    "SELECT * FROM controller_project_operations WHERE operation_id=?",
                    (operation_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise ControllerError(503, "database_unavailable", "Controller database unavailable") from error
        if row is None:
            return None
        return self._operation_payload(row)
