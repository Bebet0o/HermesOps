#!/usr/bin/env bash
    set -Eeuo pipefail
    export LC_ALL=C

    REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    UNIT_DIR="${REPO}/systemd/user"

    SUPERVISOR="${UNIT_DIR}/hermesops-supervisor.service"
    ORCHESTRATOR="${UNIT_DIR}/hermesops-orchestrator.service"
    NOTIFIER="${UNIT_DIR}/hermesops-notifier.service"
    CONTROLLER="${UNIT_DIR}/hermesops-controller-api.service"
    INSTALLER="${REPO}/install.sh"

    for unit in "$SUPERVISOR" "$ORCHESTRATOR" "$NOTIFIER" "$CONTROLLER"; do
        [[ -f "$unit" ]]

        grep -Fxq 'WantedBy=default.target' "$unit"

        if grep -Eq '^After=.*default\.target([[:space:]]|$)' "$unit"; then
            echo "Cycle potentiel avec default.target dans $unit" >&2
            exit 1
        fi
    done

    grep -Fxq 'After=hermesops-supervisor.service' "$ORCHESTRATOR"
    grep -Fxq 'Wants=hermesops-supervisor.service' "$ORCHESTRATOR"

    grep -Fq \
        'user_run systemctl --user restart hermesops-supervisor.service' \
        "$INSTALLER"

    grep -Fq \
        'user_run systemctl --user restart hermesops-orchestrator.service' \
        "$INSTALLER"

    grep -Fq \
        'user_run systemctl --user restart hermesops-notifier.service' \
        "$INSTALLER"

    grep -Fq \
        'user_run systemctl --user restart hermesops-controller-api.service' \
        "$INSTALLER"

    grep -Fq \
        'Service utilisateur inactif après installation' \
        "$INSTALLER"

    python3 - "$SUPERVISOR" "$ORCHESTRATOR" "$NOTIFIER" "$CONTROLLER" <<'PY'
from pathlib import Path
import re
import sys

units = [Path(value) for value in sys.argv[1:]]

# A WantedBy=default.target symlink causes default.target to want the service.
# Target units order themselves after wanted services by default, therefore an
# explicit service After=default.target creates the reverse edge and a cycle.
for unit in units:
    text = unit.read_text(encoding="utf-8")
    if "WantedBy=default.target" not in text:
        raise SystemExit(f"Missing default target install hook: {unit}")
    if re.search(r"^After=.*\bdefault\.target\b", text, re.MULTILINE):
        raise SystemExit(f"default.target ordering cycle: {unit}")

print("HermesOps systemd dependency graph: PASS")
PY

    echo "HermesOps user-service boot order: PASS"
