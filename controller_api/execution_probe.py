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
class ExecutionProbeResult:
    task_list_status: int | None
    task_status: int | None
    run_list_status: int | None
    run_status: int | None
    log_status: int | None
    task_count: int
    run_count: int


def _items(payload: dict[str, object], label: str) -> list[object]:
    items = payload.get("data")
    if not isinstance(items, list):
        raise ServiceSupportError(f"{label} did not return a list.")
    return items


def probe_execution_reads(
    base_url: str,
    session_file: Path,
    *,
    wait_seconds: float = 10,
) -> ExecutionProbeResult:
    host, port = _validated_base_url(base_url)
    token = read_session(session_file)
    objective_status, objective_payload = _request(
        host,
        port,
        "/api/v1/objectives?limit=50",
        token=token,
        timeout=wait_seconds,
    )
    if objective_status != 200:
        raise ServiceSupportError("Objective discovery did not return HTTP 200.")
    objectives = _items(objective_payload, "Objective discovery")

    task_list_status: int | None = None
    task: dict[str, object] | None = None
    for objective in objectives:
        if not isinstance(objective, dict) or not isinstance(objective.get("id"), str):
            raise ServiceSupportError("Objective discovery returned an invalid item.")
        candidate_status, candidate_payload = _request(
            host,
            port,
            f"/api/v1/objectives/{objective['id']}/tasks?limit=1",
            token=token,
            timeout=wait_seconds,
        )
        if candidate_status != 200:
            raise ServiceSupportError("Task list probe did not return HTTP 200.")
        task_list_status = candidate_status
        candidates = _items(candidate_payload, "Task list probe")
        if candidates:
            candidate = candidates[0]
            if not isinstance(candidate, dict) or not isinstance(candidate.get("id"), str):
                raise ServiceSupportError("Task list probe returned an invalid item.")
            task = candidate
            break

    if task is None:
        return ExecutionProbeResult(
            task_list_status=task_list_status,
            task_status=None,
            run_list_status=None,
            run_status=None,
            log_status=None,
            task_count=0,
            run_count=0,
        )

    task_id = str(task["id"])
    task_status, task_payload = _request(
        host,
        port,
        f"/api/v1/tasks/{task_id}",
        token=token,
        timeout=wait_seconds,
    )
    if task_status != 200 or not isinstance(task_payload.get("data"), dict):
        raise ServiceSupportError("Task detail probe did not return HTTP 200.")

    run_list_status, run_payload = _request(
        host,
        port,
        f"/api/v1/tasks/{task_id}/runs?limit=1",
        token=token,
        timeout=wait_seconds,
    )
    if run_list_status != 200:
        raise ServiceSupportError("Run list probe did not return HTTP 200.")
    runs = _items(run_payload, "Run list probe")
    if not runs:
        return ExecutionProbeResult(
            task_list_status=task_list_status,
            task_status=task_status,
            run_list_status=run_list_status,
            run_status=None,
            log_status=None,
            task_count=1,
            run_count=0,
        )

    run = runs[0]
    if not isinstance(run, dict) or not isinstance(run.get("id"), str):
        raise ServiceSupportError("Run list probe returned an invalid item.")
    run_id = str(run["id"])
    run_status, run_detail = _request(
        host,
        port,
        f"/api/v1/runs/{run_id}",
        token=token,
        timeout=wait_seconds,
    )
    if run_status != 200 or not isinstance(run_detail.get("data"), dict):
        raise ServiceSupportError("Run detail probe did not return HTTP 200.")

    log_status, logs = _request(
        host,
        port,
        f"/api/v1/runs/{run_id}/logs?limit=1",
        token=token,
        timeout=wait_seconds,
    )
    log_data = logs.get("data")
    if (
        log_status != 200
        or not isinstance(log_data, dict)
        or not isinstance(log_data.get("entries"), list)
    ):
        raise ServiceSupportError("Run log probe did not return HTTP 200.")

    return ExecutionProbeResult(
        task_list_status=task_list_status,
        task_status=task_status,
        run_list_status=run_list_status,
        run_status=run_status,
        log_status=log_status,
        task_count=1,
        run_count=1,
    )
