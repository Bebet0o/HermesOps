#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import http.server
import ipaddress
import json
import logging
import os
import signal
import socket
import stat
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlsplit

MAX_FILE_SIZE = 512 * 1024
ROUTES = frozenset(
    {
        "/",
        "/dashboard",
        "/projects",
        "/objectives",
        "/executions",
        "/reviews",
        "/events",
        "/administration",
    }
)
ASSETS = {
    "/assets/app.js": (Path("assets/app.js"), "text/javascript"),
    "/assets/styles.css": (Path("assets/styles.css"), "text/css"),
}
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "img-src 'self'; font-src 'self'; connect-src 'none'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'; object-src 'none'"
    ),
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


class ConsoleServiceError(RuntimeError):
    pass


def read_safe_file(path: Path, maximum: int = MAX_FILE_SIZE) -> bytes:
    try:
        before = path.lstat()
    except OSError as error:
        raise ConsoleServiceError("Console file is unavailable") from error
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size <= 0 or before.st_size > maximum:
        raise ConsoleServiceError("Console file is unsafe")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ConsoleServiceError("Console file cannot be opened safely") from error
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise ConsoleServiceError("Console file changed type")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(maximum + 1)
    finally:
        os.close(descriptor)
    if (
        before.st_dev != opened.st_dev
        or before.st_ino != opened.st_ino
        or before.st_size != opened.st_size
        or len(data) != opened.st_size
        or len(data) > maximum
    ):
        raise ConsoleServiceError("Console file changed while reading")
    return data


@dataclass(frozen=True)
class Settings:
    root: Path
    version_file: Path
    host: str = "127.0.0.1"
    port: int = 8788
    max_connections: int = 16

    @classmethod
    def from_root(
        cls,
        root: Path,
        *,
        host: str = "127.0.0.1",
        port: int = 8788,
        max_connections: int = 16,
    ) -> "Settings":
        if root.is_symlink():
            raise ConsoleServiceError("Console distribution root must not be a symlink")
        resolved = root.resolve(strict=True)
        repository = resolved.parents[1]
        settings = cls(
            root=resolved,
            version_file=repository / "VERSION",
            host=host,
            port=port,
            max_connections=max_connections,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        try:
            address = ipaddress.ip_address(self.host)
        except ValueError as error:
            raise ConsoleServiceError("Console host must be a loopback IP address") from error
        if not address.is_loopback:
            raise ConsoleServiceError("Console host must be loopback")
        if not 0 <= self.port <= 65_535:
            raise ConsoleServiceError("Console port is invalid")
        if not 1 <= self.max_connections <= 128:
            raise ConsoleServiceError("Console connection limit is invalid")
        if self.root.is_symlink() or not self.root.is_dir():
            raise ConsoleServiceError("Console distribution root is invalid")
        expected = {
            Path("index.html"),
            Path("asset-manifest.json"),
            Path("assets/app.js"),
            Path("assets/styles.css"),
        }
        actual: set[Path] = set()
        for path in self.root.rglob("*"):
            if path.is_symlink():
                raise ConsoleServiceError("Console distribution contains a symlink")
            if path.is_file():
                actual.add(path.relative_to(self.root))
        if actual != expected:
            raise ConsoleServiceError("Console distribution file set is invalid")
        file_bytes = {relative: read_safe_file(self.root / relative) for relative in expected}
        try:
            manifest = json.loads(file_bytes[Path("asset-manifest.json")])
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ConsoleServiceError("Console asset manifest is invalid") from error
        if set(manifest) != {"schema_version", "entrypoint", "files"} or manifest.get("schema_version") != 1 or manifest.get("entrypoint") != "index.html":
            raise ConsoleServiceError("Console asset manifest contract is invalid")
        entries = manifest.get("files")
        expected_entries = {"index.html", "assets/app.js", "assets/styles.css"}
        if not isinstance(entries, dict) or set(entries) != expected_entries:
            raise ConsoleServiceError("Console asset manifest file set is invalid")
        for name in sorted(expected_entries):
            metadata = entries[name]
            data = file_bytes[Path(name)]
            if not isinstance(metadata, dict) or set(metadata) != {"sha256", "size"}:
                raise ConsoleServiceError("Console asset manifest metadata is invalid")
            if metadata.get("size") != len(data) or metadata.get("sha256") != hashlib.sha256(data).hexdigest():
                raise ConsoleServiceError("Console asset digest mismatch")
        if self.version_file.is_symlink() or not self.version_file.is_file():
            raise ConsoleServiceError("HermesOps version file is invalid")


class BoundedHTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], handler, settings: Settings):
        self.settings = settings
        self._slots = threading.BoundedSemaphore(settings.max_connections)
        super().__init__(server_address, handler)

    def process_request(self, request, client_address) -> None:
        if not self._slots.acquire(blocking=False):
            request_id = "req_" + uuid.uuid4().hex
            body = b'{"status":503,"title":"Console capacity exhausted","type":"urn:hermesops:console:capacity_exhausted"}\n'
            headers = [
                "HTTP/1.1 503 Service Unavailable",
                "Content-Type: application/problem+json; charset=utf-8",
                f"Content-Length: {len(body)}",
                "Cache-Control: no-store",
                f"X-Request-ID: {request_id}",
                "Connection: close",
            ]
            headers.extend(f"{name}: {value}" for name, value in SECURITY_HEADERS.items())
            response = ("\r\n".join(headers) + "\r\n\r\n").encode("ascii") + body
            try:
                request.sendall(response)
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


class ConsoleHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "HermesOpsConsole"
    sys_version = ""

    @property
    def settings(self) -> Settings:
        return self.server.settings  # type: ignore[attr-defined]

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(10.0)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return

    def _request_id(self) -> str:
        return "req_" + uuid.uuid4().hex

    def _valid_host(self) -> bool:
        values = self.headers.get_all("Host", failobj=[])
        if len(values) != 1:
            return False
        supplied = values[0].strip().lower()
        expected = {
            f"{self.settings.host}:{self.server.server_port}",
            f"[{self.settings.host}]:{self.server.server_port}",
        }
        return supplied in expected

    def _headers(
        self,
        *,
        status: int,
        length: int,
        content_type: str,
        request_id: str,
        allow: str | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Request-ID", request_id)
        if allow is not None:
            self.send_header("Allow", allow)
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()

    def _send(
        self,
        *,
        status: int,
        body: bytes,
        content_type: str,
        request_id: str,
        head_only: bool = False,
        allow: str | None = None,
    ) -> None:
        self._headers(
            status=status,
            length=len(body),
            content_type=content_type,
            request_id=request_id,
            allow=allow,
        )
        if not head_only:
            self.wfile.write(body)

    def _problem(self, status: int, code: str, title: str, request_id: str, *, head_only: bool) -> None:
        body = (json.dumps(
            {
                "type": f"urn:hermesops:console:{code}",
                "title": title,
                "status": status,
                "request_id": request_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n").encode("utf-8")
        self._send(
            status=status,
            body=body,
            content_type="application/problem+json",
            request_id=request_id,
            head_only=head_only,
        )

    def _read_regular(self, relative: Path) -> bytes:
        return read_safe_file(self.settings.root / relative)

    def _serve(self, *, head_only: bool) -> None:
        request_id = self._request_id()
        if not self._valid_host():
            self._problem(400, "invalid_host", "Invalid Host header", request_id, head_only=head_only)
            return
        parsed = urlsplit(self.path)
        if parsed.query or parsed.fragment or "%" in parsed.path or "\\" in parsed.path:
            self._problem(400, "invalid_path", "Invalid request path", request_id, head_only=head_only)
            return
        path = parsed.path
        try:
            if path == "/health":
                body = b'{"service":"hermesops-console","status":"ok"}\n'
                self._send(status=200, body=body, content_type="application/json", request_id=request_id, head_only=head_only)
                return
            if path == "/version":
                version = read_safe_file(self.settings.version_file, 1024).decode("utf-8").strip()
                body = (json.dumps({"service": "hermesops-console", "version": version}, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
                self._send(status=200, body=body, content_type="application/json", request_id=request_id, head_only=head_only)
                return
            if path in ROUTES:
                body = self._read_regular(Path("index.html"))
                self._send(status=200, body=body, content_type="text/html", request_id=request_id, head_only=head_only)
                return
            asset = ASSETS.get(path)
            if asset is not None:
                relative, content_type = asset
                body = self._read_regular(relative)
                self._send(status=200, body=body, content_type=content_type, request_id=request_id, head_only=head_only)
                return
        except (OSError, ConsoleServiceError, UnicodeError):
            self._problem(503, "asset_unavailable", "Console asset unavailable", request_id, head_only=head_only)
            return
        self._problem(404, "route_not_found", "Route not found", request_id, head_only=head_only)

    def do_GET(self) -> None:
        self._serve(head_only=False)

    def do_HEAD(self) -> None:
        self._serve(head_only=True)

    def _method_not_allowed(self) -> None:
        request_id = self._request_id()
        body = b'{"status":405,"title":"Method not allowed","type":"urn:hermesops:console:method_not_allowed"}\n'
        self._send(
            status=405,
            body=body,
            content_type="application/problem+json",
            request_id=request_id,
            allow="GET, HEAD",
        )
        self.close_connection = True

    do_POST = _method_not_allowed
    do_PUT = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_DELETE = _method_not_allowed
    do_OPTIONS = _method_not_allowed
    do_TRACE = _method_not_allowed
    do_CONNECT = _method_not_allowed


def create_server(settings: Settings) -> BoundedHTTPServer:
    return BoundedHTTPServer((settings.host, settings.port), ConsoleHandler, settings)


def check_bind(settings: Settings) -> None:
    with socket.socket(socket.AF_INET6 if ":" in settings.host else socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind((settings.host, settings.port))


def settings_from_arguments(arguments: argparse.Namespace) -> Settings:
    return Settings.from_root(
        arguments.root,
        host=arguments.host,
        port=arguments.port,
        max_connections=arguments.max_connections,
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Serve the HermesOps Console foundation")
    subparsers = result.add_subparsers(dest="command", required=True)
    for name in ("check", "serve"):
        child = subparsers.add_parser(name)
        child.add_argument("--root", type=Path, required=True)
        child.add_argument("--host", default="127.0.0.1")
        child.add_argument("--port", type=int, default=8788)
        child.add_argument("--max-connections", type=int, default=16)
    return result


def main() -> int:
    arguments = parser().parse_args()
    try:
        settings = settings_from_arguments(arguments)
        if arguments.command == "check":
            check_bind(settings)
            print("HERMESOPS_CONSOLE_SERVICE_CHECK_PASS")
            return 0
        server = create_server(settings)
    except (ConsoleServiceError, OSError) as error:
        print(f"Console service failed: {error}", file=__import__("sys").stderr)
        return 1

    stop = threading.Event()

    def request_stop(signum, frame) -> None:
        del signum, frame
        if not stop.is_set():
            stop.set()
            threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("HermesOps Console listening on %s:%s", settings.host, server.server_port)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
