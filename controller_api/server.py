from __future__ import annotations

import json
import logging
import signal
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from . import SERVICE_NAME
from .core import ControllerError, ControllerService, Settings

LOGGER = logging.getLogger(SERVICE_NAME)
MAX_REQUEST_TARGET_BYTES = 4096
MAX_QUERY_FIELDS = 8
ALLOWED_PROJECT_QUERY_FIELDS = {"cursor", "limit"}
ALLOWED_OBJECTIVE_QUERY_FIELDS = {"cursor", "limit", "project_id", "state"}
ALLOWED_EXECUTION_LIST_QUERY_FIELDS = {"cursor", "limit"}
ALLOWED_REVIEW_RECOVERY_QUERY_FIELDS = {"cursor", "limit", "project_id", "state"}
ALLOWED_LOG_QUERY_FIELDS = {"after_sequence", "limit"}


class ControllerHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 32

    def __init__(
        self,
        server_address: tuple[str, int],
        service: ControllerService,
    ) -> None:
        self.service = service
        self._request_slots = threading.BoundedSemaphore(
            service.settings.max_concurrent_requests
        )
        super().__init__(server_address, ControllerRequestHandler)

    def get_request(self) -> tuple[socket.socket, Any]:
        request, client_address = super().get_request()
        request.settimeout(self.service.settings.socket_timeout_seconds)
        return request, client_address

    def process_request(
        self,
        request: socket.socket,
        client_address: Any,
    ) -> None:
        if not self._request_slots.acquire(blocking=False):
            try:
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Connection: close\r\n"
                    b"Content-Length: 0\r\n"
                    b"Cache-Control: no-store\r\n"
                    b"\r\n"
                )
            except OSError:
                pass
            finally:
                request.close()
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._request_slots.release()
            raise

    def process_request_thread(
        self,
        request: socket.socket,
        client_address: Any,
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


class ControllerRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = SERVICE_NAME
    sys_version = ""

    @property
    def controller(self) -> ControllerHTTPServer:
        return self.server  # type: ignore[return-value]

    @staticmethod
    def _safe_log(value: str) -> str:
        return "".join(
            character
            if character.isprintable() and character not in "\r\n"
            else "?"
            for character in value
        )

    def log_message(self, format_string: str, *args: object) -> None:
        LOGGER.info(
            "%s %s",
            self.client_address[0],
            self._safe_log(format_string % args),
        )

    def _request_id(self) -> str:
        return self.controller.service.request_id(
            self.headers.get("X-Request-ID")
        )

    def _security_headers(self) -> dict[str, str]:
        return {
            "Cross-Origin-Resource-Policy": "same-origin",
            "Content-Security-Policy": (
                "default-src 'none'; frame-ancestors 'none'"
            ),
            "Referrer-Policy": "no-referrer",
            "X-Frame-Options": "DENY",
        }

    def _send_json(
        self,
        status: int,
        payload: dict[str, Any],
        request_id: str,
        *,
        content_type: str = "application/json",
        head_only: bool = False,
        extra_headers: dict[str, str] | None = None,
        close_connection: bool = False,
    ) -> None:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

        if close_connection:
            self.close_connection = True

        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Request-ID", request_id)
        for name, value in self._security_headers().items():
            self.send_header(name, value)
        if close_connection:
            self.send_header("Connection", "close")
        if extra_headers:
            for name, value in extra_headers.items():
                self.send_header(name, value)
        self.end_headers()

        if not head_only:
            try:
                self.wfile.write(body)
            except (
                BrokenPipeError,
                ConnectionResetError,
                TimeoutError,
                socket.timeout,
            ):
                self.close_connection = True

    def _problem(
        self,
        error: ControllerError,
        request_id: str,
        *,
        head_only: bool = False,
        close_connection: bool = False,
    ) -> None:
        self._send_json(
            error.status,
            self.controller.service.problem(error, request_id),
            request_id,
            content_type="application/problem+json",
            head_only=head_only,
            close_connection=close_connection,
        )

    def _validate_host(self) -> None:
        host = self.headers.get("Host")
        if not host:
            raise ControllerError(
                400,
                "host_header_required",
                "Host header required",
            )

        accepted = {
            "localhost",
            f"localhost:{self.server.server_address[1]}",
            "127.0.0.1",
            f"127.0.0.1:{self.server.server_address[1]}",
            "[::1]",
            f"[::1]:{self.server.server_address[1]}",
        }
        if host.lower() not in accepted:
            raise ControllerError(
                421,
                "misdirected_request",
                "Misdirected request",
                "The Host header is not a permitted loopback authority.",
            )

    def _validate_request_target(self) -> None:
        if len(self.path.encode("utf-8", errors="replace")) > (
            MAX_REQUEST_TARGET_BYTES
        ):
            raise ControllerError(
                414,
                "request_target_too_long",
                "Request target too long",
            )

    def _reject_request_body(self) -> None:
        transfer_encoding = self.headers.get("Transfer-Encoding")
        content_length = self.headers.get("Content-Length")

        if transfer_encoding:
            raise ControllerError(
                400,
                "request_body_not_allowed",
                "Request body not allowed",
                "GET and HEAD requests must not use Transfer-Encoding.",
            )

        if content_length is None:
            return

        try:
            length = int(content_length)
        except ValueError as error:
            raise ControllerError(
                400,
                "invalid_content_length",
                "Invalid Content-Length",
            ) from error

        if length < 0:
            raise ControllerError(
                400,
                "invalid_content_length",
                "Invalid Content-Length",
            )
        if length > 0:
            raise ControllerError(
                400,
                "request_body_not_allowed",
                "Request body not allowed",
                "GET and HEAD requests must not include a request body.",
            )

    def _technical_probe(
        self,
        path: str,
        request_id: str,
    ) -> tuple[int, dict[str, Any]]:
        service = self.controller.service
        if path == "/health":
            return 200, {
                "status": "ok",
                "service": SERVICE_NAME,
                "version": service.version(),
                "request_id": request_id,
            }
        if path == "/version":
            return 200, {
                "service": SERVICE_NAME,
                "version": service.version(),
                "api_version": "v1",
                "request_id": request_id,
            }
        if path == "/ready":
            ready, reasons = service.readiness()
            return (200 if ready else 503), {
                "status": "ready" if ready else "not_ready",
                "service": SERVICE_NAME,
                "reasons": reasons,
                "request_id": request_id,
            }
        raise ControllerError(
            404,
            "route_not_found",
            "Route not found",
            "The requested Controller API route does not exist.",
        )

    def _parse_query(self, raw_query: str) -> dict[str, list[str]]:
        try:
            return parse_qs(
                raw_query,
                keep_blank_values=True,
                strict_parsing=False,
                max_num_fields=MAX_QUERY_FIELDS,
            )
        except ValueError as error:
            raise ControllerError(
                400,
                "invalid_query",
                "Invalid query string",
                "The query string contains too many fields.",
            ) from error

    def _protected_get(
        self,
        path: str,
        query: dict[str, list[str]],
        request_id: str,
    ) -> tuple[int, dict[str, Any], dict[str, str]]:
        service = self.controller.service
        session_token = service.authenticate(self.headers.get("Cookie"))

        if path == "/api/v1/system/health":
            payload = {
                "data": {
                    "status": (
                        "ok"
                        if service.database.readiness()[0]
                        else "unavailable"
                    )
                },
                "meta": service.meta(request_id),
            }
            return 200, payload, {}

        if path == "/api/v1/system/capabilities":
            return 200, {
                "data": service.capabilities(),
                "meta": service.meta(request_id),
            }, {}

        if path == "/api/v1/system/status":
            return 200, {
                "data": service.system_status(),
                "meta": service.meta(request_id),
            }, {}

        if path == "/api/v1/projects":
            unknown = set(query) - ALLOWED_PROJECT_QUERY_FIELDS
            if unknown:
                raise ControllerError(
                    400,
                    "unknown_query_parameter",
                    "Unknown query parameter",
                    "Only cursor and limit are supported.",
                )

            raw_limit = query.get("limit", ["50"])
            if len(raw_limit) != 1:
                raise ControllerError(
                    400,
                    "invalid_limit",
                    "Invalid pagination limit",
                )
            try:
                limit = int(raw_limit[0])
            except ValueError as error:
                raise ControllerError(
                    400,
                    "invalid_limit",
                    "Invalid pagination limit",
                    "limit must be an integer.",
                ) from error

            raw_cursor = query.get("cursor", [])
            if len(raw_cursor) > 1:
                raise ControllerError(
                    400,
                    "invalid_cursor",
                    "Invalid pagination cursor",
                )
            cursor = raw_cursor[0] if raw_cursor else None
            projects, next_cursor = service.database.list_projects(
                limit=limit,
                cursor=cursor,
            )
            return 200, {
                "data": projects,
                "meta": service.meta(
                    request_id,
                    next_cursor=next_cursor,
                ),
            }, {}

        if path == "/api/v1/objectives":
            unknown = set(query) - ALLOWED_OBJECTIVE_QUERY_FIELDS
            if unknown:
                raise ControllerError(
                    400,
                    "unknown_query_parameter",
                    "Unknown query parameter",
                    "Only cursor, limit, project_id and state are supported.",
                )
            raw_limit = query.get("limit", ["50"])
            if len(raw_limit) != 1:
                raise ControllerError(400, "invalid_limit", "Invalid pagination limit")
            try:
                limit = int(raw_limit[0])
            except ValueError as error:
                raise ControllerError(
                    400,
                    "invalid_limit",
                    "Invalid pagination limit",
                    "limit must be an integer.",
                ) from error
            raw_cursor = query.get("cursor", [])
            raw_project = query.get("project_id", [])
            raw_state = query.get("state", [])
            if len(raw_cursor) > 1 or len(raw_project) > 1 or len(raw_state) > 1:
                raise ControllerError(400, "invalid_query", "Invalid query string")
            project_id = raw_project[0] if raw_project else None
            state = raw_state[0] if raw_state else None
            objectives, next_cursor = service.objectives.list_objectives(
                limit=limit,
                cursor=raw_cursor[0] if raw_cursor else None,
                project_id=project_id,
                state=state,
                cursor_secret=session_token,
            )
            return 200, {
                "data": objectives,
                "meta": service.meta(request_id, next_cursor=next_cursor),
            }, {}

        nested_prefix = "/api/v1/projects/"
        nested_suffix = "/objectives"
        if path.startswith(nested_prefix) and path.endswith(nested_suffix):
            project_id = unquote(path[len(nested_prefix):-len(nested_suffix)])
            if not project_id or "/" in project_id:
                raise ControllerError(404, "route_not_found", "Route not found")
            unknown = set(query) - {"cursor", "limit"}
            if unknown:
                raise ControllerError(
                    400,
                    "unknown_query_parameter",
                    "Unknown query parameter",
                    "Only cursor and limit are supported.",
                )
            raw_limit = query.get("limit", ["50"])
            raw_cursor = query.get("cursor", [])
            if len(raw_limit) != 1 or len(raw_cursor) > 1:
                raise ControllerError(400, "invalid_query", "Invalid query string")
            try:
                limit = int(raw_limit[0])
            except ValueError as error:
                raise ControllerError(400, "invalid_limit", "Invalid pagination limit") from error
            objectives, next_cursor = service.objectives.list_objectives(
                limit=limit,
                cursor=raw_cursor[0] if raw_cursor else None,
                project_id=project_id,
                state=None,
                cursor_secret=session_token,
            )
            return 200, {
                "data": objectives,
                "meta": service.meta(request_id, next_cursor=next_cursor),
            }, {}

        if path in {"/api/v1/reviews", "/api/v1/recoveries"}:
            unknown = set(query) - ALLOWED_REVIEW_RECOVERY_QUERY_FIELDS
            if unknown:
                raise ControllerError(
                    400,
                    "unknown_query_parameter",
                    "Unknown query parameter",
                    "Only cursor, limit, project_id and state are supported.",
                )
            raw_limit = query.get("limit", ["50"])
            raw_cursor = query.get("cursor", [])
            raw_project = query.get("project_id", [])
            raw_state = query.get("state", [])
            if (
                len(raw_limit) != 1
                or len(raw_cursor) > 1
                or len(raw_project) > 1
                or len(raw_state) > 1
            ):
                raise ControllerError(400, "invalid_query", "Invalid query string")
            try:
                limit = int(raw_limit[0])
            except ValueError as error:
                raise ControllerError(
                    400,
                    "invalid_limit",
                    "Invalid pagination limit",
                    "limit must be an integer.",
                ) from error
            project_id = raw_project[0] if raw_project else None
            state = raw_state[0] if raw_state else None
            if path == "/api/v1/reviews":
                items, next_cursor = service.review_recovery.list_reviews(
                    limit=limit,
                    cursor=raw_cursor[0] if raw_cursor else None,
                    project_id=project_id,
                    state=state,
                    cursor_secret=session_token,
                )
            else:
                items, next_cursor = service.review_recovery.list_recoveries(
                    limit=limit,
                    cursor=raw_cursor[0] if raw_cursor else None,
                    project_id=project_id,
                    state=state,
                    cursor_secret=session_token,
                )
            return 200, {
                "data": items,
                "meta": service.meta(request_id, next_cursor=next_cursor),
            }, {}

        review_prefix = "/api/v1/reviews/"
        review_evidence_suffix = "/evidence"
        if path.startswith(review_prefix) and path.endswith(review_evidence_suffix):
            if query:
                raise ControllerError(400, "unknown_query_parameter", "Unknown query parameter")
            review_id = unquote(path[len(review_prefix):-len(review_evidence_suffix)])
            if not review_id or "/" in review_id:
                raise ControllerError(404, "route_not_found", "Route not found")
            evidence = service.review_recovery.get_review_evidence(review_id)
            return 200, {
                "data": evidence,
                "meta": service.meta(request_id),
            }, {}

        if path.startswith(review_prefix):
            if query:
                raise ControllerError(400, "unknown_query_parameter", "Unknown query parameter")
            review_id = unquote(path[len(review_prefix):])
            if not review_id or "/" in review_id:
                raise ControllerError(404, "route_not_found", "Route not found")
            review = service.review_recovery.get_review(review_id)
            revision = int(review["resource_revision"])
            return 200, {
                "data": review,
                "meta": service.meta(request_id, resource_revision=revision),
            }, {"ETag": f'"{revision}"'}

        recovery_prefix = "/api/v1/recoveries/"
        if path.startswith(recovery_prefix):
            if query:
                raise ControllerError(400, "unknown_query_parameter", "Unknown query parameter")
            recovery_id = unquote(path[len(recovery_prefix):])
            if not recovery_id or "/" in recovery_id:
                raise ControllerError(404, "route_not_found", "Route not found")
            recovery = service.review_recovery.get_recovery(recovery_id)
            revision = int(recovery["resource_revision"])
            return 200, {
                "data": recovery,
                "meta": service.meta(request_id, resource_revision=revision),
            }, {"ETag": f'"{revision}"'}

        objective_prefix = "/api/v1/objectives/"
        objective_tasks_suffix = "/tasks"
        if path.startswith(objective_prefix) and path.endswith(objective_tasks_suffix):
            objective_id = unquote(
                path[len(objective_prefix):-len(objective_tasks_suffix)]
            )
            if not objective_id or "/" in objective_id:
                raise ControllerError(404, "route_not_found", "Route not found")
            unknown = set(query) - ALLOWED_EXECUTION_LIST_QUERY_FIELDS
            if unknown:
                raise ControllerError(
                    400,
                    "unknown_query_parameter",
                    "Unknown query parameter",
                    "Only cursor and limit are supported.",
                )
            raw_limit = query.get("limit", ["50"])
            raw_cursor = query.get("cursor", [])
            if len(raw_limit) != 1 or len(raw_cursor) > 1:
                raise ControllerError(400, "invalid_query", "Invalid query string")
            try:
                limit = int(raw_limit[0])
            except ValueError as error:
                raise ControllerError(400, "invalid_limit", "Invalid pagination limit") from error
            tasks, next_cursor = service.executions.list_objective_tasks(
                objective_id,
                limit=limit,
                cursor=raw_cursor[0] if raw_cursor else None,
                cursor_secret=session_token,
            )
            return 200, {
                "data": tasks,
                "meta": service.meta(request_id, next_cursor=next_cursor),
            }, {}

        task_prefix = "/api/v1/tasks/"
        task_runs_suffix = "/runs"
        if path.startswith(task_prefix) and path.endswith(task_runs_suffix):
            task_id = unquote(path[len(task_prefix):-len(task_runs_suffix)])
            if not task_id or "/" in task_id:
                raise ControllerError(404, "route_not_found", "Route not found")
            unknown = set(query) - ALLOWED_EXECUTION_LIST_QUERY_FIELDS
            if unknown:
                raise ControllerError(
                    400,
                    "unknown_query_parameter",
                    "Unknown query parameter",
                    "Only cursor and limit are supported.",
                )
            raw_limit = query.get("limit", ["50"])
            raw_cursor = query.get("cursor", [])
            if len(raw_limit) != 1 or len(raw_cursor) > 1:
                raise ControllerError(400, "invalid_query", "Invalid query string")
            try:
                limit = int(raw_limit[0])
            except ValueError as error:
                raise ControllerError(400, "invalid_limit", "Invalid pagination limit") from error
            runs, next_cursor = service.executions.list_task_runs(
                task_id,
                limit=limit,
                cursor=raw_cursor[0] if raw_cursor else None,
                cursor_secret=session_token,
            )
            return 200, {
                "data": runs,
                "meta": service.meta(request_id, next_cursor=next_cursor),
            }, {}

        run_prefix = "/api/v1/runs/"
        run_logs_suffix = "/logs"
        if path.startswith(run_prefix) and path.endswith(run_logs_suffix):
            run_id = unquote(path[len(run_prefix):-len(run_logs_suffix)])
            if not run_id or "/" in run_id:
                raise ControllerError(404, "route_not_found", "Route not found")
            unknown = set(query) - ALLOWED_LOG_QUERY_FIELDS
            if unknown:
                raise ControllerError(
                    400,
                    "unknown_query_parameter",
                    "Unknown query parameter",
                    "Only after_sequence and limit are supported.",
                )
            raw_after = query.get("after_sequence", ["0"])
            raw_limit = query.get("limit", ["200"])
            if len(raw_after) != 1 or len(raw_limit) != 1:
                raise ControllerError(400, "invalid_query", "Invalid query string")
            try:
                after_sequence = int(raw_after[0])
                limit = int(raw_limit[0])
            except ValueError as error:
                raise ControllerError(400, "invalid_log_query", "Invalid log query") from error
            chunk, snapshot_sequence = service.executions.get_run_logs(
                run_id,
                after_sequence=after_sequence,
                limit=limit,
            )
            return 200, {
                "data": chunk,
                "meta": service.meta(
                    request_id,
                    snapshot_sequence=snapshot_sequence,
                ),
            }, {}

        if path.startswith(task_prefix):
            if query:
                raise ControllerError(400, "unknown_query_parameter", "Unknown query parameter")
            task_id = unquote(path[len(task_prefix):])
            if not task_id or "/" in task_id:
                raise ControllerError(404, "route_not_found", "Route not found")
            task = service.executions.get_task(task_id)
            revision = int(task["resource_revision"])
            return 200, {
                "data": task,
                "meta": service.meta(request_id, resource_revision=revision),
            }, {"ETag": f'"{revision}"'}

        if path.startswith(run_prefix):
            if query:
                raise ControllerError(400, "unknown_query_parameter", "Unknown query parameter")
            run_id = unquote(path[len(run_prefix):])
            if not run_id or "/" in run_id:
                raise ControllerError(404, "route_not_found", "Route not found")
            run = service.executions.get_run(run_id)
            revision = int(run["resource_revision"])
            return 200, {
                "data": run,
                "meta": service.meta(request_id, resource_revision=revision),
            }, {"ETag": f'"{revision}"'}

        objective_prefix = "/api/v1/objectives/"
        if path.startswith(objective_prefix):
            if query:
                raise ControllerError(400, "unknown_query_parameter", "Unknown query parameter")
            objective_id = unquote(path[len(objective_prefix):])
            if not objective_id or "/" in objective_id:
                raise ControllerError(404, "route_not_found", "Route not found")
            objective = service.objectives.get_objective(objective_id)
            revision = int(objective["resource_revision"])
            return 200, {
                "data": objective,
                "meta": service.meta(request_id, resource_revision=revision),
            }, {"ETag": f'"{revision}"'}

        operation_prefix = "/api/v1/operations/"
        if path.startswith(operation_prefix):
            if query:
                raise ControllerError(400, "unknown_query_parameter", "Unknown query parameter")
            operation_id = unquote(path[len(operation_prefix):])
            if not operation_id or "/" in operation_id:
                raise ControllerError(404, "route_not_found", "Route not found")
            operation = service.objectives.get_operation(operation_id)
            revision = int(operation["resource_revision"])
            return 200, {
                "data": operation,
                "meta": service.meta(request_id, resource_revision=revision),
            }, {"ETag": f'"{revision}"'}

        if query:
            raise ControllerError(
                400,
                "unknown_query_parameter",
                "Unknown query parameter",
                "This route does not accept query parameters.",
            )

        prefix = "/api/v1/projects/"
        if path.startswith(prefix):
            project_id = unquote(path[len(prefix):])
            if not project_id or "/" in project_id:
                raise ControllerError(
                    404,
                    "route_not_found",
                    "Route not found",
                )
            project = service.database.get_project(project_id)
            revision = int(project["resource_revision"])
            return 200, {
                "data": project,
                "meta": service.meta(
                    request_id,
                    resource_revision=revision,
                ),
            }, {"ETag": f'"{revision}"'}

        raise ControllerError(
            404,
            "route_not_found",
            "Route not found",
            "The requested Controller API route does not exist.",
        )

    def _handle_get(self, *, head_only: bool = False) -> None:
        request_id = self._request_id()
        try:
            self._validate_host()
            self._validate_request_target()
            self._reject_request_body()

            parsed = urlsplit(self.path)
            path = parsed.path
            if path in {"/health", "/ready", "/version"}:
                if parsed.query:
                    raise ControllerError(
                        400,
                        "unknown_query_parameter",
                        "Unknown query parameter",
                        "Technical probes do not accept query parameters.",
                    )
                status, payload = self._technical_probe(path, request_id)
                self._send_json(
                    status,
                    payload,
                    request_id,
                    head_only=head_only,
                )
                return

            status, payload, headers = self._protected_get(
                path,
                self._parse_query(parsed.query),
                request_id,
            )
            self._send_json(
                status,
                payload,
                request_id,
                head_only=head_only,
                extra_headers=headers,
            )
        except ControllerError as error:
            self._problem(
                error,
                request_id,
                head_only=head_only,
                close_connection=(
                    error.code
                    in {
                        "invalid_content_length",
                        "request_body_not_allowed",
                    }
                ),
            )
        except Exception:
            LOGGER.exception("Unhandled Controller API request failure")
            self._problem(
                ControllerError(
                    500,
                    "internal_error",
                    "Internal server error",
                ),
                request_id,
                head_only=head_only,
                close_connection=True,
            )

    def do_GET(self) -> None:
        self._handle_get()

    def do_HEAD(self) -> None:
        self._handle_get(head_only=True)

    def _method_not_allowed(self) -> None:
        request_id = self._request_id()
        error = ControllerError(
            405,
            "method_not_allowed",
            "Method not allowed",
            "The Controller exposes read-only GET and HEAD routes only.",
        )
        self._send_json(
            405,
            self.controller.service.problem(error, request_id),
            request_id,
            content_type="application/problem+json",
            extra_headers={"Allow": "GET, HEAD"},
            close_connection=True,
        )

    do_POST = _method_not_allowed
    do_PUT = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_DELETE = _method_not_allowed
    do_OPTIONS = _method_not_allowed
    do_TRACE = _method_not_allowed
    do_CONNECT = _method_not_allowed


def build_server(settings: Settings) -> ControllerHTTPServer:
    service = ControllerService(settings)
    return ControllerHTTPServer((settings.host, settings.port), service)


def serve(settings: Settings) -> None:
    server = build_server(settings)
    stop = threading.Event()

    def request_stop(
        signum: int,
        frame: object,
    ) -> None:
        del signum, frame
        if stop.is_set():
            return
        stop.set()
        threading.Thread(
            target=server.shutdown,
            name="controller-api-shutdown",
            daemon=True,
        ).start()

    previous: dict[int, Any] = {}
    for signum in (signal.SIGTERM, signal.SIGINT):
        previous[signum] = signal.signal(signum, request_stop)

    try:
        host, port = server.server_address[:2]
        LOGGER.info("Controller API listening on %s:%s", host, port)
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        for signum, handler in previous.items():
            signal.signal(signum, handler)
