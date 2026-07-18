#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C
export PYTHONDONTWRITEBYTECODE=1

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

required=(
    docs/V020_BETA_ARCHITECTURE.md
    docs/milestones/2A_CONTROLLER_CONTRACTS.md
    docs/architecture/CONTROLLER_CONSOLE_BOUNDARY.md
    docs/architecture/CONTROLLER_COMPONENTS.md
    docs/api/CONTROLLER_API_V1.md
    docs/api/EVENTS_V1.md
    docs/hermesfile/SPECIFICATION_V0.md
    docs/console/INFORMATION_ARCHITECTURE.md
    docs/adr/0001-controller-owns-control-plane-writes.md
    docs/adr/0002-console-is-an-unprivileged-api-client.md
    docs/adr/0003-hermes-agent-is-behind-an-adapter.md
    docs/adr/0004-hermesfiles-compile-to-immutable-images.md
    docs/adr/0005-controller-events-are-replayable.md
    docs/adr/0006-dangerous-actions-require-confirmation.md
    specs/README.md
    specs/controller-api-v1.openapi.json
    specs/events-v1.schema.json
    specs/hermesfile-v0.schema.json
)

for relative in "${required[@]}"; do
    [[ -s "${REPO}/${relative}" ]] || {
        echo "Missing or empty contract file: ${relative}" >&2
        exit 1
    }
done

python3 - "$REPO" <<'PY'
from __future__ import annotations

from pathlib import Path
import json
import re
import sys

root = Path(sys.argv[1])

def load_json(relative: str):
    path = root / relative
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Invalid JSON {relative}: {exc}") from exc

def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)

def operation_parameters(operation: dict) -> list[dict]:
    return list(operation.get("parameters", []))

def parameter_name(parameter: dict) -> str | None:
    if "$ref" in parameter:
        return parameter["$ref"].rsplit("/", 1)[-1]
    return parameter.get("name")

openapi = load_json("specs/controller-api-v1.openapi.json")
events = load_json("specs/events-v1.schema.json")
hermesfile = load_json("specs/hermesfile-v0.schema.json")

require(openapi.get("openapi") == "3.1.0", "OpenAPI version must be 3.1.0")
require(
    openapi.get("servers") == [{"url": "/api/v1"}],
    "Controller API server base must be /api/v1",
)

security_schemes = openapi["components"]["securitySchemes"]
require("sessionCookie" in security_schemes, "sessionCookie security missing")
require("csrfHeader" in security_schemes, "csrfHeader security missing")
require(
    security_schemes["sessionCookie"].get("in") == "cookie",
    "Session authentication must use an HTTP cookie",
)
require(
    security_schemes["csrfHeader"].get("name") == "X-CSRF-Token",
    "CSRF header contract mismatch",
)

required_paths = {
    "/system/status",
    "/projects",
    "/projects/{project_id}",
    "/projects/{project_id}/objectives",
    "/objectives/{objective_id}",
    "/objectives/{objective_id}/commands/{command}",
    "/tasks/{task_id}",
    "/runs/{run_id}",
    "/runs/{run_id}/commands/{command}",
    "/reviews/{review_id}",
    "/recoveries/{recovery_id}",
    "/recoveries/{recovery_id}/decisions",
    "/sandboxes",
    "/sandboxes/{sandbox_id}",
    "/sandboxes/{sandbox_id}/builds",
    "/sandboxes/{sandbox_id}/commands/{command}",
    "/confirmations/{confirmation_id}",
}
require(
    required_paths.issubset(openapi["paths"]),
    f"OpenAPI paths missing: {sorted(required_paths - set(openapi['paths']))}",
)

operation_ids: set[str] = set()
mutating_methods = {"post", "put", "patch", "delete"}
for path, path_item in openapi["paths"].items():
    require(
        not any(forbidden in path for forbidden in ("/shell", "/docker", "/sqlite")),
        f"Forbidden primitive exposed by API path: {path}",
    )

    for method, operation in path_item.items():
        if method not in {"get", "post", "put", "patch", "delete"}:
            continue

        operation_id = operation.get("operationId")
        require(operation_id, f"operationId missing for {method.upper()} {path}")
        require(
            operation_id not in operation_ids,
            f"Duplicate operationId: {operation_id}",
        )
        operation_ids.add(operation_id)

        if method in mutating_methods:
            names = {
                parameter_name(parameter)
                for parameter in operation_parameters(operation)
            }
            require(
                "Idempotency-Key" in names,
                f"Idempotency-Key missing for {method.upper()} {path}",
            )
            param = next(
                parameter
                for parameter in operation_parameters(operation)
                if parameter_name(parameter) == "Idempotency-Key"
            )
            require(
                param.get("required") is True,
                f"Idempotency-Key must be required for {method.upper()} {path}",
            )
            security = operation.get("security", [])
            require(
                any(
                    "sessionCookie" in item and "csrfHeader" in item
                    for item in security
                ),
                f"Session + CSRF security missing for {method.upper()} {path}",
            )
            require(
                "409" in operation.get("responses", {}),
                f"409 confirmation/conflict response missing for {method.upper()} {path}",
            )

problem = openapi["components"]["schemas"]["Problem"]
for field in ("type", "title", "status", "code", "request_id"):
    require(field in problem["required"], f"Problem required field missing: {field}")

confirmation = openapi["components"]["schemas"]["ConfirmationRequirement"]
for field in ("id", "risk", "expires_at", "consequences"):
    require(
        field in confirmation["required"],
        f"Confirmation required field missing: {field}",
    )

require(events.get("$schema", "").endswith("2020-12/schema"), "Event schema draft mismatch")
for field in (
    "schema_version",
    "sequence",
    "event_id",
    "type",
    "occurred_at",
    "actor",
    "aggregate",
    "correlation_id",
    "data",
):
    require(field in events["required"], f"Event envelope field missing: {field}")

require(
    events["properties"]["schema_version"].get("const") == 1,
    "Event schema version must be 1",
)
require(
    events["properties"]["sequence"].get("minimum") == 1,
    "Event sequence must begin at 1",
)
event_types = set(events["properties"]["type"]["enum"])
for event_type in (
    "run.state_changed",
    "review.verdict_recorded",
    "recovery.decision_applied",
    "sandbox.activated",
    "confirmation.created",
):
    require(event_type in event_types, f"Required event type missing: {event_type}")

require(
    hermesfile["properties"]["apiVersion"].get("const")
    == "hermesops.dev/v0alpha1",
    "Hermesfile apiVersion mismatch",
)
require(
    hermesfile["properties"]["kind"].get("const") == "SandboxProfile",
    "Hermesfile kind mismatch",
)

spec = hermesfile["properties"]["spec"]
for field in ("base", "workspace", "runtime", "network", "security", "validation"):
    require(field in spec["required"], f"Hermesfile required section missing: {field}")

base = spec["properties"]["base"]
require("digest" in base["required"], "Base image digest must be required")
require(
    base["properties"]["digest"].get("pattern")
    == r"^sha256:[a-f0-9]{64}$",
    "Base digest pattern mismatch",
)

security = spec["properties"]["security"]["properties"]
require(security["privileged"].get("const") is False, "Privileged must be false")
require(
    security["noNewPrivileges"].get("const") is True,
    "noNewPrivileges must be true",
)
require(
    security["allowDockerSocket"].get("const") is False,
    "Docker socket must be forbidden",
)
require(
    security["allowDeviceAccess"].get("const") is False,
    "Device access must be forbidden",
)
require(
    security["capabilities"]["properties"]["add"].get("maxItems") == 0,
    "Added Linux capabilities must be forbidden in v0",
)

mount_props = spec["properties"]["mounts"]["items"]["properties"]
require("source" not in mount_props, "Hermesfile must not expose host mount source")
require(
    set(mount_props["type"]["enum"])
    == {"workspace", "cache", "tmpfs", "artifact"},
    "Hermesfile mount types mismatch",
)

# Verify local links in new Markdown documents.
new_docs = [
    root / "docs/V020_BETA_ARCHITECTURE.md",
    *sorted((root / "docs/milestones").glob("*.md")),
    *sorted((root / "docs/architecture").glob("CONTROLLER*.md")),
    *sorted((root / "docs/api").glob("*.md")),
    *sorted((root / "docs/hermesfile").glob("*.md")),
    *sorted((root / "docs/console").glob("*.md")),
    *sorted((root / "docs/adr").glob("000*.md")),
]
link_re = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
for path in new_docs:
    text = path.read_text(encoding="utf-8")
    require(len(text.splitlines()) >= 20, f"Contract document too short: {path}")
    for target in link_re.findall(text):
        if target.startswith(("http://", "https://", "#")):
            continue
        file_part = target.split("#", 1)[0]
        if not file_part:
            continue
        resolved = (path.parent / file_part).resolve()
        require(
            resolved.is_file(),
            f"Broken local link in {path.relative_to(root)}: {target}",
        )

adrs = sorted((root / "docs/adr").glob("000*.md"))
require(len(adrs) >= 6, "At least six architecture decisions are required")
numbers = [int(path.name.split("-", 1)[0]) for path in adrs]
require(numbers[:6] == list(range(1, 7)), f"ADR sequence invalid: {numbers}")
for path in adrs[:6]:
    text = path.read_text(encoding="utf-8")
    require("Status: **Accepted**" in text, f"ADR not accepted: {path.name}")

readme = (root / "README.md").read_text(encoding="utf-8")
readme_words = " ".join(readme.split())
require(
    "docs/V020_BETA_ARCHITECTURE.md" in readme,
    "README must link to v0.2.0-beta architecture contracts",
)
require(
    "do not mean those runtime features are already implemented"
    in readme_words,
    "README must distinguish design contracts from implementation",
)

print("Controller OpenAPI contract: PASS")
print("Controller mutation idempotency and CSRF contract: PASS")
print("Replayable event schema: PASS")
print("Hermesfile v0 security schema: PASS")
print("Milestone 2A documentation links: PASS")
print("Architecture decision sequence: PASS")
PY

echo "HERMESOPS_CONTROLLER_CONTRACTS_PASS"
