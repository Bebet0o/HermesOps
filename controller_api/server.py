from __future__ import annotations

import json
import logging
import signal
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from . import SERVICE_NAME
from .core import ControllerError, ControllerService, Settings

LOGGER = logging.getLogger(SERVICE_NAME)


class ControllerHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        service: ControllerService,
    ) -> None:
        super().__init__(server_address, ControllerRequestHandler)
        self.service = service


class ControllerRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = SERVICE_NAME
    sys_version = ""

    @property
    def controller(self) -> ControllerHTTPServer:
        return self.server  # type: ignore[return-value]

    def log_message(self, format_string: str, *args: object) -> None:
        LOGGER.info(
            "%s %s",
            self.client_address[0],
            format_string % args,
        )

    def _request_id(self) -> str:
        return self.controller.service.request_id(
            self.headers.get("X-Request-ID")
        )

    def _send_json(
        self,
        status: int,
        payload: dict[str, Any],
        request_id: str,
        *,
        content_type: str = "application/json",
        head_only: bool = False,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Request-ID", request_id)
        if extra_headers:
            for name, value in extra_headers.items():
                self.send_header(name, value)
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _problem(
        self,
        error: ControllerError,
        request_id: str,
        *,
        head_only: bool = False,
    ) -> None:
        self._send_json(
            error.status,
            self.controller.service.problem(error, request_id),
            request_id,
            content_type="application/problem+json",
            head_only=head_only,
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

    def _protected_get(
        self,
        path: str,
        query: dict[str, list[str]],
        request_id: str,
    ) -> tuple[int, dict[str, Any], dict[str, str]]:
        service = self.controller.service
        service.authenticate(self.headers.get("Cookie"))

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
            parsed = urlsplit(self.path)
            path = parsed.path
            if path in {"/health", "/ready", "/version"}:
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
                parse_qs(
                    parsed.query,
                    keep_blank_values=True,
                    strict_parsing=False,
                ),
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
            self._problem(error, request_id, head_only=head_only)
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
            "Milestone 2B exposes read-only GET and HEAD routes only.",
        )
        self._send_json(
            405,
            self.controller.service.problem(error, request_id),
            request_id,
            content_type="application/problem+json",
            extra_headers={"Allow": "GET, HEAD"},
        )

    do_POST = _method_not_allowed
    do_PUT = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_DELETE = _method_not_allowed


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
