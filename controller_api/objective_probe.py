from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .service_support import (
    ServiceSupportError,
    _request,
    _validated_base_url,
    read_session,
)


@dataclass(frozen=True)
class ObjectiveProbeResult:
    list_status: int
    detail_status: int | None
    nested_status: int | None
    operation_status: int | None
    objective_count: int


def probe_objective_reads(
    base_url: str,
    session_file: Path,
    *,
    wait_seconds: float = 10,
) -> ObjectiveProbeResult:
    host, port = _validated_base_url(base_url)
    token = read_session(session_file)
    status, payload = _request(
        host, port, "/api/v1/objectives?limit=1", token=token, timeout=wait_seconds
    )
    if status != 200 or not isinstance(payload.get("data"), list):
        raise ServiceSupportError("Objective list probe did not return HTTP 200 with a list.")
    items = payload["data"]
    if not items:
        return ObjectiveProbeResult(status, None, None, None, 0)
    item = items[0]
    if not isinstance(item, dict) or not isinstance(item.get("id"), str):
        raise ServiceSupportError("Objective list returned an invalid item.")
    objective_id = item["id"]
    detail_status, detail = _request(
        host, port, f"/api/v1/objectives/{objective_id}",
        token=token, timeout=wait_seconds,
    )
    if detail_status != 200:
        raise ServiceSupportError("Objective detail probe did not return HTTP 200.")
    project_ids = detail.get("data", {}).get("project_ids", [])
    nested_status = None
    if isinstance(project_ids, list) and project_ids and isinstance(project_ids[0], str):
        nested_status, _ = _request(
            host, port, f"/api/v1/projects/{project_ids[0]}/objectives?limit=1",
            token=token, timeout=wait_seconds,
        )
        if nested_status != 200:
            raise ServiceSupportError("Project objective probe did not return HTTP 200.")
    operation_status = None
    operation_id = detail.get("data", {}).get("latest_operation_id")
    if isinstance(operation_id, str):
        operation_status, _ = _request(
            host, port, f"/api/v1/operations/{operation_id}",
            token=token, timeout=wait_seconds,
        )
        if operation_status != 200:
            raise ServiceSupportError("Operation detail probe did not return HTTP 200.")
    return ObjectiveProbeResult(
        list_status=status,
        detail_status=detail_status,
        nested_status=nested_status,
        operation_status=operation_status,
        objective_count=len(items),
    )
