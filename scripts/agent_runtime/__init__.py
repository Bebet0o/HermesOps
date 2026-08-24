"""Runtime-neutral agent execution boundary for HermesOps."""

from pathlib import Path

from .contract import (
    AgentRuntime,
    RuntimeError,
    RuntimeErrorKind,
    RuntimeRequest,
    RuntimeResult,
    RuntimeRole,
    RuntimeSandboxContext,
)
from .fake import FakeRuntime, FakeRuntimeOutcome
from .hermes import HermesRuntime


def create_runtime(
    root: Path,
    *,
    required_role: RuntimeRole,
) -> AgentRuntime:
    """Construct the configured runtime implementation for one role."""
    return HermesRuntime(root, required_role=required_role)

__all__ = [
    "AgentRuntime",
    "FakeRuntime",
    "FakeRuntimeOutcome",
    "HermesRuntime",
    "RuntimeError",
    "RuntimeErrorKind",
    "RuntimeRequest",
    "RuntimeResult",
    "RuntimeRole",
    "RuntimeSandboxContext",
    "create_runtime",
]
