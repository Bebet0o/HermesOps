"""Backend-neutral synchronous model generation contract."""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


_MAX_MODEL_ID_LENGTH = 256
_MAX_TIMEOUT_SECONDS = 600


def _contains_control(value: str) -> bool:
    return any(
        unicodedata.category(character).startswith("C")
        or unicodedata.category(character) in {"Zl", "Zp"}
        for character in value
    )


def _is_valid_unicode(value: str) -> bool:
    return not any(0xD800 <= ord(character) <= 0xDFFF for character in value)


class ModelMessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class ModelMessage:
    role: ModelMessageRole
    content: str = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.role) is not ModelMessageRole:
            raise TypeError("Model message role must be a ModelMessageRole")
        if type(self.content) is not str:
            raise TypeError("Model message content must be a string")
        if not _is_valid_unicode(self.content):
            raise ValueError("Model message content must be valid Unicode")


@dataclass(frozen=True)
class ModelRequest:
    model: str
    messages: tuple[ModelMessage, ...] = field(repr=False)
    timeout_seconds: int | float

    def __post_init__(self) -> None:
        if type(self.model) is not str:
            raise TypeError("Model identity must be a string")
        if (
            not self.model.strip()
            or len(self.model) > _MAX_MODEL_ID_LENGTH
            or _contains_control(self.model)
        ):
            raise ValueError("Model identity is invalid")
        if not _is_valid_unicode(self.model):
            raise ValueError("Model identity is invalid")
        if type(self.messages) is not tuple:
            raise TypeError("Model messages must be a non-empty tuple")
        if not self.messages:
            raise ValueError("Model messages must be non-empty")
        if any(type(message) is not ModelMessage for message in self.messages):
            raise TypeError("Model messages must contain only ModelMessage values")
        if type(self.timeout_seconds) not in {int, float}:
            raise TypeError("Model timeout must be an integer or float")
        if (
            not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
            or self.timeout_seconds > _MAX_TIMEOUT_SECONDS
        ):
            raise ValueError("Model timeout must be finite and between 0 and 600 seconds")


@dataclass(frozen=True)
class ModelResult:
    """Successful model output; an empty string remains a valid provider response."""

    output_text: str = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.output_text) is not str:
            raise TypeError("Model output must be a string")


class ModelProviderErrorKind(str, Enum):
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    REQUEST_REJECTED = "request_rejected"
    INVALID_RESPONSE = "invalid_response"
    PROVIDER_FAILED = "provider_failed"


class ModelProviderError(Exception):
    """Safe, backend-neutral model provider failure."""

    def __init__(self, kind: ModelProviderErrorKind, message: str) -> None:
        if type(kind) is not ModelProviderErrorKind:
            raise TypeError("Model provider error kind must be a ModelProviderErrorKind")
        if type(message) is not str:
            raise TypeError("Model provider error message must be a string")
        if not message:
            raise ValueError("Model provider error message must be non-empty")
        super().__init__(message)
        self.kind = kind

    def __repr__(self) -> str:
        return f"ModelProviderError(kind={self.kind.value!r})"


@runtime_checkable
class ModelProvider(Protocol):
    def generate(self, request: ModelRequest) -> ModelResult:
        """Generate one complete textual model response or raise a normalized error."""
