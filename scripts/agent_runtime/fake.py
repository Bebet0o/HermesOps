"""Deterministic AgentRuntime test double."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .contract import (
    RuntimeError,
    RuntimeErrorKind,
    RuntimeRequest,
    RuntimeResult,
)


@dataclass(frozen=True)
class FakeRuntimeOutcome:
    output: str = ""
    exit_status: int = 0
    error_kind: RuntimeErrorKind | None = None
    message: str = ""
    effect: Callable[[RuntimeRequest], None] | None = field(
        default=None,
        compare=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.output, str):
            raise TypeError("Fake runtime output must be a string")
        if not isinstance(self.exit_status, int) or isinstance(
            self.exit_status,
            bool,
        ):
            raise TypeError("Fake runtime exit status must be an integer")
        if self.error_kind is not None and not isinstance(
            self.error_kind,
            RuntimeErrorKind,
        ):
            raise TypeError("Fake runtime error kind must be a RuntimeErrorKind")
        if not isinstance(self.message, str):
            raise TypeError("Fake runtime message must be a string")
        if self.effect is not None and not callable(self.effect):
            raise TypeError("Fake runtime effect must be callable")
        if self.error_kind is not None and not self.message:
            raise ValueError("Fake runtime failures require a message")
        if (
            self.error_kind not in {None, RuntimeErrorKind.EXECUTION_FAILED}
            and self.exit_status != 0
        ):
            raise ValueError(
                "Only execution failures may carry a nonzero exit status"
            )
        if self.error_kind is None and self.message:
            raise ValueError("Successful fake runtime outcomes cannot carry a message")

    @classmethod
    def success(
        cls,
        *,
        output: str,
        effect: Callable[[RuntimeRequest], None] | None = None,
    ) -> "FakeRuntimeOutcome":
        return cls(output=output, effect=effect)

    @classmethod
    def failure(cls, message: str) -> "FakeRuntimeOutcome":
        return cls(
            exit_status=1,
            error_kind=RuntimeErrorKind.EXECUTION_FAILED,
            message=message,
        )

    @classmethod
    def timeout(cls) -> "FakeRuntimeOutcome":
        return cls(
            error_kind=RuntimeErrorKind.TIMEOUT,
            message="Runtime execution timed out",
        )

    @classmethod
    def invalid_result(cls) -> "FakeRuntimeOutcome":
        return cls(
            error_kind=RuntimeErrorKind.INVALID_RESULT,
            message="Runtime result is invalid",
        )

    @classmethod
    def cancelled(cls) -> "FakeRuntimeOutcome":
        return cls(
            error_kind=RuntimeErrorKind.CANCELLED,
            message="Runtime execution was cancelled",
        )


class FakeRuntime:
    def __init__(self, outcomes: list[FakeRuntimeOutcome]) -> None:
        if not isinstance(outcomes, list):
            raise TypeError("Fake runtime outcomes must be a list")
        if any(not isinstance(outcome, FakeRuntimeOutcome) for outcome in outcomes):
            raise TypeError("Fake runtime outcomes must be FakeRuntimeOutcome values")
        self._outcomes = list(outcomes)
        self.requests: list[RuntimeRequest] = []

    def execute(self, request: RuntimeRequest) -> RuntimeResult:
        if not isinstance(request, RuntimeRequest):
            raise RuntimeError(
                RuntimeErrorKind.INVALID_RESULT,
                "Fake runtime request does not satisfy the runtime contract",
            )
        self.requests.append(request)
        if not self._outcomes:
            raise RuntimeError(
                RuntimeErrorKind.RUNTIME_UNAVAILABLE,
                "Fake runtime has no configured outcome",
            )

        outcome = self._outcomes.pop(0)
        if outcome.error_kind is None and outcome.exit_status != 0:
            raise RuntimeError(
                RuntimeErrorKind.EXECUTION_FAILED,
                f"Runtime execution failed with code {outcome.exit_status}",
                exit_status=outcome.exit_status,
                output=outcome.output,
            )
        if outcome.error_kind is not None:
            raise RuntimeError(
                outcome.error_kind,
                outcome.message,
                exit_status=(
                    outcome.exit_status
                    if outcome.error_kind is RuntimeErrorKind.EXECUTION_FAILED
                    else None
                ),
                output=outcome.output,
            )

        if outcome.effect is not None:
            try:
                outcome.effect(request)
            except Exception as error:
                raise RuntimeError(
                    RuntimeErrorKind.EXECUTION_FAILED,
                    f"Fake runtime effect failed: {type(error).__name__}",
                    output=outcome.output,
                ) from error

        marker_found = any(
            line.strip() == request.completion_marker
            for line in outcome.output.splitlines()
        )
        if not marker_found:
            raise RuntimeError(
                RuntimeErrorKind.INVALID_RESULT,
                "Runtime completion marker is absent",
                exit_status=outcome.exit_status,
                output=outcome.output,
            )

        return RuntimeResult(output=outcome.output)
