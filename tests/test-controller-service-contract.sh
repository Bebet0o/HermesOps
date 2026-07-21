#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C
export PYTHONDONTWRITEBYTECODE=1

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${REPO}${PYTHONPATH:+:${PYTHONPATH}}"
cd "$REPO"

UNIT="systemd/user/hermesops-controller-api.service"
INSTALLER="install.sh"
UNINSTALLER="uninstall.sh"
VALIDATE="validate.sh"

for file in \
    controller_api/service_support.py \
    scripts/hermesops-controller-session.py \
    scripts/hermesops-controller-probe.py \
    tests/test_controller_service.py \
    tests/test-controller-service-lifecycle.sh \
    tests/test-controller-service-persistence.sh \
    "$UNIT"
do
    [[ -f "$file" ]]
done

python3 -m compileall -q \
    controller_api/service_support.py \
    scripts/hermesops-controller-session.py \
    scripts/hermesops-controller-probe.py \
    tests/test_controller_service.py

python3 tests/test_controller_service.py

bash -n \
    tests/test-controller-service-lifecycle.sh \
    tests/test-controller-service-persistence.sh \
    install.sh uninstall.sh validate.sh

for marker in \
    'ExecStartPre=/usr/bin/python3 /opt/docker/hermesops/repo/scripts/hermesops-controller-session.py check' \
    'ExecStartPre=/usr/bin/python3 /opt/docker/hermesops/repo/scripts/hermesops-controller-operator.py ensure' \
    'ExecStart=/usr/bin/python3 /opt/docker/hermesops/repo/scripts/hermesops-controller-api.py serve --host 127.0.0.1 --port 8765 --log-level INFO' \
    'ExecStartPost=/usr/bin/python3 /opt/docker/hermesops/repo/scripts/hermesops-controller-probe.py --base-url http://127.0.0.1:8765 --wait-seconds 20' \
    'Restart=on-failure' \
    'NoNewPrivileges=true' \
    'RestrictSUIDSGID=true' \
    'RestrictRealtime=true' \
    'RestrictNamespaces=true' \
    'LockPersonality=true' \
    'MemoryDenyWriteExecute=true' \
    'RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6' \
    'WantedBy=default.target'
do
    grep -Fxq "$marker" "$UNIT"
done

if grep -Eq '^After=.*default\.target([[:space:]]|$)' "$UNIT"; then
    echo "default.target ordering cycle in Controller unit" >&2
    exit 1
fi


for forbidden in \
    'CapabilityBoundingSet=' \
    'AmbientCapabilities=' \
    'PrivateDevices=' \
    'ProtectKernelTunables=' \
    'ProtectKernelModules=' \
    'ProtectKernelLogs=' \
    'ProtectControlGroups=' \
    'ProtectSystem=' \
    'ProtectHome=' \
    'PrivateTmp=' \
    'PrivateUsers='
do
    if grep -Eq "^[[:space:]]*${forbidden}" "$UNIT"; then
        echo "Non-portable user-service hardening remains: ${forbidden}" >&2
        exit 1
    fi
done

if command -v systemd-analyze >/dev/null 2>&1; then
    systemd-analyze --user verify "$UNIT"
fi

for marker in \
    '"${REPO}/scripts/hermesops-controller-session.py" ensure' \
    '"${REPO}/scripts/hermesops-controller-operator.py" ensure' \
    'hermesops-controller-api.service' \
    'user_run systemctl --user restart hermesops-controller-api.service' \
    '"${REPO}/scripts/hermesops-controller-probe.py"'
do
    grep -Fq "$marker" "$INSTALLER"
done

grep -Fq \
    'for unit in hermesops-controller-api.service hermesops-notifier.service' \
    "$UNINSTALLER"

if grep -Fq 'rm -f "${ROOT}/secrets/controller-session"' "$UNINSTALLER"; then
    echo "Conservative uninstall must preserve Controller session." >&2
    exit 1
fi

grep -Fq     '"${TARGET_HOME}/.config/systemd/user/default.target.wants/${unit}"'     "$UNINSTALLER"

for marker in \
    'tests/test-controller-service-contract.sh' \
    'tests/test-controller-service-persistence.sh' \
    'hermesops-controller-api.service' \
    'scripts/hermesops-controller-probe.py'
do
    grep -Fq "$marker" "$VALIDATE"
done

python3 - "$UNIT" "$INSTALLER" "$UNINSTALLER" <<'PY'
from pathlib import Path
import sys

unit = Path(sys.argv[1]).read_text(encoding="utf-8")
installer = Path(sys.argv[2]).read_text(encoding="utf-8")
uninstaller = Path(sys.argv[3]).read_text(encoding="utf-8")

if "--host 0.0.0.0" in unit or "--host ::" in unit:
    raise SystemExit("Controller service is not loopback-only")

session = installer.index("hermesops-controller-session.py\" ensure")
unit_copy = installer.index('for unit in "${REPO}"/systemd/user/*.service')
restart = installer.index(
    "systemctl --user restart hermesops-controller-api.service"
)
probe = installer.index("hermesops-controller-probe.py", restart)
if not session < unit_copy < restart < probe:
    raise SystemExit("Invalid Controller install lifecycle order")

stop = uninstaller.index("hermesops-controller-api.service")
compose = uninstaller.index("hermes-agent-compose.sh")
if not stop < compose:
    raise SystemExit("Controller must stop before containers are removed")

for required in (
    "CONTROLLER_UNIT_TOUCHED=1",
    "restore_controller_unit",
    "CONTROLLER_UNIT_WAS_ENABLED",
    "CONTROLLER_UNIT_WAS_ACTIVE",
):
    if required not in installer:
        raise SystemExit(
            f"Controller installer rollback marker missing: {required}"
        )

if "default.target.wants/${unit}" not in uninstaller:
    raise SystemExit("Uninstaller does not remove stale activation links")

print("HermesOps Controller service installation contract: PASS")
PY

echo "HERMESOPS_CONTROLLER_SERVICE_CONTRACT_PASS"
