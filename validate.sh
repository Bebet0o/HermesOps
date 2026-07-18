#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C
export PYTHONDONTWRITEBYTECODE=1

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${HERMESOPS_ROOT:-/opt/docker/hermesops}"
MODE="all"
QUIET=0

while (($#)); do
    case "$1" in
        --static) MODE="static"; shift ;;
        --runtime) MODE="runtime"; shift ;;
        --quiet) QUIET=1; shift ;;
        --help|-h)
            cat <<'HELP'
Usage: ./validate.sh [--static|--runtime] [--quiet]
HELP
            exit 0
            ;;
        *) echo "Option inconnue: $1" >&2; exit 2 ;;
    esac
done

log() { [[ "$QUIET" == 1 ]] || printf '%s\n' "$*"; }

static_validation() {
    log "== Validation statique =="
    [[ "$(cat "${REPO}/VERSION")" == "0.1.0-alpha" ]]

    for file in \
        install.sh uninstall.sh preflight.sh validate.sh \
        scripts/check-secrets.sh scripts/check-secrets.py \
        scripts/export-worker-image.sh scripts/init-test-fixtures.sh \
        tests/test-public-empty-registry.sh \
        tests/test-preflight-minimal-host.sh \
        tests/test-install-no-auth-contract.sh \
        tests/test-systemd-user-boot-order.sh \
        tests/test-release-documentation.sh \
        compose/agent.yaml compose/images.lock.env \
        compose/agent.env.example compose/webui.env.example \
        compose/notifications.env.example config/host-packages.lock.toml
    do
        [[ -f "${REPO}/${file}" ]]
    done

    while IFS= read -r -d '' script; do
        bash -n "$script"
    done < <(
        find "$REPO" -path "$REPO/.git" -prune -o \
            -type f -name '*.sh' -print0
    )

    python3 - "$REPO" <<'PY'
from pathlib import Path
import ast
import sys
root = Path(sys.argv[1])
for path in sorted(root.rglob("*.py")):
    if ".git" in path.parts:
        continue
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
print("Python AST: PASS")
PY

    "${REPO}/scripts/check-secrets.sh" --root "$REPO"

    if git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        python3 - "$REPO" <<'PY'
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1])
result = subprocess.run(
    ["git", "-C", str(root), "ls-files", "config/projects.d/*.toml"],
    check=True,
    text=True,
    stdout=subprocess.PIPE,
)
tracked = sorted(
    line for line in result.stdout.splitlines() if line
)
if tracked:
    raise SystemExit(
        f"Active project configuration tracked: {tracked}"
    )

required = (
    root / "tests/fixtures/projects/transaction-fixture.toml",
    root / "tests/fixtures/projects/transaction-fixture-b.toml",
)
missing = [
    path.relative_to(root).as_posix()
    for path in required
    if not path.is_file()
]
if missing:
    raise SystemExit(f"Test fixture templates missing: {missing}")

print("Tracked active project configurations: NONE")
print("Test fixture templates: PASS")
PY
    fi

    python3 - "$REPO/migrations" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
versions = [
    int(path.name.split("_", 1)[0])
    for path in sorted(root.glob("[0-9][0-9][0-9]_*.sql"))
]
if versions != list(range(1, len(versions) + 1)):
    raise SystemExit(f"Migration sequence invalid: {versions}")
print(f"Migration sequence: PASS ({len(versions)})")
PY

    "${REPO}/tests/test-public-empty-registry.sh"
    "${REPO}/tests/test-preflight-minimal-host.sh"
    "${REPO}/tests/test-install-no-auth-contract.sh"
    "${REPO}/tests/test-systemd-user-boot-order.sh"
    "${REPO}/tests/test-release-documentation.sh"

    TMP="$(mktemp -d)"
    mkdir -p \
        "$TMP/root/repo/compose" \
        "$TMP/root/secrets" \
        "$TMP/root/state" \
        "$TMP/root/runtime" \
        "$TMP/root/workspaces" \
        "$TMP/root/project-data"
    cp "${REPO}/compose/agent.yaml" "$TMP/root/repo/compose/"
    cp "${REPO}/compose/images.lock.env" "$TMP/root/repo/compose/"
    cp "${REPO}/compose/agent.env.example" "$TMP/root/secrets/agent.env"
    cp "${REPO}/compose/webui.env.example" "$TMP/root/secrets/webui.env"

    HERMES_UID="$(id -u)" HERMES_GID="$(id -g)" \
    docker compose \
        --project-directory "$TMP/root/repo/compose" \
        --env-file "$TMP/root/repo/compose/images.lock.env" \
        -f "$TMP/root/repo/compose/agent.yaml" \
        config --quiet
    rm -rf "$TMP"
    log "HERMESOPS_STATIC_VALIDATION_PASS"
}

runtime_validation() {
    log "== Validation runtime =="
    [[ "$REPO" == "${ROOT}/repo" ]] || {
        echo "Lancer depuis ${ROOT}/repo." >&2
        exit 1
    }

    "${REPO}/scripts/verify-layout.sh"
    "${REPO}/scripts/hermesops-db.py" integrity
    "${REPO}/scripts/hermesops-registry.py" validate
    "${REPO}/scripts/hermesops-roles.py" validate
    "${REPO}/scripts/hermesops-roles.py" verify-profiles

    COMPOSE=(
        docker compose
        --project-directory "${REPO}/compose"
        --env-file "${REPO}/compose/images.lock.env"
        -f "${REPO}/compose/agent.yaml"
    )
    "${COMPOSE[@]}" config --quiet

    for container in hermesops-sandbox-engine hermesops-agent hermesops-webui; do
        health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container")"
        [[ "$health" == "healthy" || "$health" == "running" ]] || {
            echo "$container non sain: $health" >&2
            exit 1
        }
    done

    curl --silent --show-error --fail --max-time 5 \
        http://127.0.0.1:8642/health >/dev/null
    curl --silent --show-error --fail --max-time 5 \
        http://127.0.0.1:8787/health >/dev/null

    readarray -t WORKER_LOCK < <(
        python3 - "${REPO}/config/worker-sandbox.lock.toml" <<'PY'
import sys
import tomllib
from pathlib import Path
with Path(sys.argv[1]).open("rb") as stream:
    data = tomllib.load(stream)
print(data["tag"])
print(data["image_id"])
PY
    )
    worker_actual="$(docker exec hermesops-sandbox-engine docker image inspect --format '{{.Id}}' "${WORKER_LOCK[0]}")"
    [[ "$worker_actual" == "${WORKER_LOCK[1]}" ]]

    for unit in hermesops-supervisor.service hermesops-orchestrator.service hermesops-notifier.service; do
        systemctl --user is-enabled "$unit" >/dev/null
        systemctl --user is-active "$unit" >/dev/null
    done

    [[ -f "${ROOT}/state/hermes-home/auth.json" ]]
    [[ "$(stat -c '%a' "${ROOT}/state/hermes-home/auth.json")" == "600" ]]
    [[ "$(stat -c '%a' "${ROOT}/secrets")" == "700" ]]
    log "HERMESOPS_RUNTIME_VALIDATION_PASS"
}

case "$MODE" in
    static) static_validation ;;
    runtime) runtime_validation ;;
    all) static_validation; runtime_validation ;;
esac
log "HERMESOPS_VALIDATION_PASS"
