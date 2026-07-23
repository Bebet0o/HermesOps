#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.client
import json
import time
from urllib.parse import urlsplit

ROUTES = (
    "/",
    "/dashboard",
    "/projects",
    "/objectives",
    "/executions",
    "/reviews",
    "/events",
    "/administration",
)
REQUIRED_HEADERS = {
    "content-security-policy": "default-src 'none'",
    "cross-origin-resource-policy": "same-origin",
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
}


class ProbeError(RuntimeError):
    pass


def request(host: str, port: int, path: str, *, method: str = "GET", timeout: float = 3.0):
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request(method, path, headers={"Host": f"{host}:{port}"})
        response = connection.getresponse()
        body = response.read(600_000)
        return response.status, {name.lower(): value for name, value in response.getheaders()}, body
    finally:
        connection.close()


def validate(base_url: str, wait_seconds: float) -> None:
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1"} or parsed.path or parsed.query or parsed.fragment:
        raise ProbeError("Console probe requires one canonical loopback HTTP origin")
    port = parsed.port or 80
    deadline = time.monotonic() + wait_seconds
    last_error: BaseException | None = None
    while True:
        try:
            status, headers, body = request(parsed.hostname, port, "/health")
            if status != 200:
                raise ProbeError(f"Console health returned HTTP {status}")
            payload = json.loads(body)
            if payload != {"service": "hermesops-console", "status": "ok"}:
                raise ProbeError("Console health payload is invalid")
            break
        except (OSError, ValueError, ProbeError) as error:
            last_error = error
            if time.monotonic() >= deadline:
                raise ProbeError(f"Console did not become ready: {last_error}") from error
            time.sleep(0.25)

    for route in ROUTES:
        status, headers, body = request(parsed.hostname, port, route)
        if status != 200 or b"HermesOps Console" not in body:
            raise ProbeError(f"Console route failed: {route}")
        for name, fragment in REQUIRED_HEADERS.items():
            if fragment not in headers.get(name, ""):
                raise ProbeError(f"Console security header missing on {route}: {name}")
        if headers.get("cache-control") != "no-store":
            raise ProbeError(f"Console cache policy is invalid on {route}")
        if not headers.get("x-request-id", "").startswith("req_"):
            raise ProbeError(f"Console request ID is invalid on {route}")

    status, _, body = request(parsed.hostname, port, "/assets/app.js")
    if status != 200 or b"fetch(" in body or b"WebSocket(" in body or b"localStorage" in body:
        raise ProbeError("Console foundation script violates the 2P network/storage boundary")

    status, headers, body = request(parsed.hostname, port, "/", method="HEAD")
    if status != 200 or body or int(headers.get("content-length", "0")) <= 0:
        raise ProbeError("Console HEAD contract failed")

    status, _, _ = request(parsed.hostname, port, "/api/v1/system/health")
    if status != 404:
        raise ProbeError("Console foundation unexpectedly exposes an API proxy")

    print(f"HermesOps Console probe: PASS routes={len(ROUTES)} port={port}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the HermesOps Console foundation")
    parser.add_argument("--base-url", default="http://127.0.0.1:8788")
    parser.add_argument("--wait-seconds", type=float, default=10.0)
    arguments = parser.parse_args()
    if not 0 <= arguments.wait_seconds <= 60:
        parser.error("--wait-seconds must be between 0 and 60")
    try:
        validate(arguments.base_url, arguments.wait_seconds)
    except ProbeError as error:
        print(f"Console probe failed: {error}", file=__import__("sys").stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
