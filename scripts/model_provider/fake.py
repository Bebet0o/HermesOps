"""Deterministic model provider used by unit and future runtime tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from .contract import (
    ModelProviderError,
    ModelProviderErrorKind,
    ModelRequest,
    ModelResult,
)


@dataclass(frozen=True)
class FakeModelProviderOutcome:
    result: ModelResult | None = field(default=None, repr=False)
    error: ModelProviderError | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if (self.result is None) == (self.error is None):
            raise ValueError("Fake model outcome requires exactly one result or error")
        if self.result is not None and type(self.result) is not ModelResult:
            raise TypeError("Fake model result must be a ModelResult")
        if self.error is not None and type(self.error) is not ModelProviderError:
            raise TypeError("Fake model error must be a ModelProviderError")

    @classmethod
    def success(cls, output_text: str) -> "FakeModelProviderOutcome":
        return cls(result=ModelResult(output_text))

    @classmethod
    def failure(cls, error: ModelProviderError) -> "FakeModelProviderOutcome":
        return cls(error=error)


class FakeModelProvider:
    def __init__(self, outcomes: list[FakeModelProviderOutcome]) -> None:
        if type(outcomes) is not list or any(
            type(outcome) is not FakeModelProviderOutcome for outcome in outcomes
        ):
            raise TypeError("Fake model outcomes must be a list of FakeModelProviderOutcome values")
        self._outcomes = list(outcomes)
        self.requests: list[ModelRequest] = []

    def generate(self, request: ModelRequest) -> ModelResult:
        if type(request) is not ModelRequest:
            raise TypeError("Fake model provider requires a ModelRequest")
        self.requests.append(request)
        if not self._outcomes:
            raise ModelProviderError(
                kind=ModelProviderErrorKind.UNAVAILABLE,
                message="Fake model provider has no configured outcome",
            )
        outcome = self._outcomes.pop(0)
        if outcome.error is not None:
            raise ModelProviderError(outcome.error.kind, str(outcome.error))
        if outcome.result is None:
            raise AssertionError("Validated fake model outcome has no result")
        return outcome.result
