"""Public model generation provider boundary."""

from .contract import (
    ModelMessage,
    ModelMessageRole,
    ModelProvider,
    ModelProviderError,
    ModelProviderErrorKind,
    ModelRequest,
    ModelResult,
)
from .fake import FakeModelProvider, FakeModelProviderOutcome
from .openai_compatible import OpenAICompatibleConfig, OpenAICompatibleProvider


__all__ = [
    "FakeModelProvider",
    "FakeModelProviderOutcome",
    "ModelMessage",
    "ModelMessageRole",
    "ModelProvider",
    "ModelProviderError",
    "ModelProviderErrorKind",
    "ModelRequest",
    "ModelResult",
    "OpenAICompatibleConfig",
    "OpenAICompatibleProvider",
]
