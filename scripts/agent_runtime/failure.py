"""Shared runtime failure projection for control-plane execution journals."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .contract import RuntimeError


_PERSISTENCE_FAILURE_SUFFIX = "; transcript_persistence_failed"


@dataclass(frozen=True)
class RuntimeFailureRecord:
    """Stable runtime failure fields consumed by existing execution journals."""

    exit_code: int | None
    failure_reason: str
    output: str = field(repr=False)

    def __post_init__(self) -> None:
        if self.exit_code is not None and (
            not isinstance(self.exit_code, int)
            or isinstance(self.exit_code, bool)
        ):
            raise TypeError("Runtime failure exit code must be an integer or None")
        if not isinstance(self.failure_reason, str) or not self.failure_reason:
            raise ValueError("Runtime failure reason must be non-empty")
        if not isinstance(self.output, str):
            raise TypeError("Runtime failure output must be a string")


def record_runtime_failure(
    error: RuntimeError,
    persist_output: Callable[[str], None],
) -> RuntimeFailureRecord:
    """Persist partial output and project a runtime error without domain policy."""
    if not isinstance(error, RuntimeError):
        raise TypeError("Runtime failure projection requires a RuntimeError")
    if not callable(persist_output):
        raise TypeError("Runtime failure output sink must be callable")

    record = RuntimeFailureRecord(
        exit_code=error.exit_status,
        failure_reason=(
            f"runtime_error[{error.kind.value}]: {str(error)[:4096]}"
        ),
        output=error.output,
    )
    try:
        persist_output(record.output)
    except Exception:
        record = RuntimeFailureRecord(
            exit_code=record.exit_code,
            failure_reason=record.failure_reason + _PERSISTENCE_FAILURE_SUFFIX,
            output=record.output,
        )
    return record
