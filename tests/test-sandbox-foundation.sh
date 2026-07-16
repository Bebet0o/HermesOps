#!/usr/bin/env bash
set -Eeuo pipefail

AGENT="hermesops-agent"
ENGINE="hermesops-sandbox-engine"

[[ "$(
    docker inspect "$AGENT" \
        --format '{{.State.Health.Status}}'
)" == "healthy" ]]

[[ "$(
    docker inspect "$ENGINE" \
        --format '{{.State.Health.Status}}'
)" == "healthy" ]]

docker inspect "$AGENT" |
jq -e '
    .[0].Mounts |
    all(.Destination != "/var/run/docker.sock")
' >/dev/null

[[ -z "$(docker port "$ENGINE")" ]]

docker exec "$AGENT" sh -lc '
    test "$DOCKER_HOST" = "tcp://sandbox-engine:2375"
    docker info >/dev/null
'

docker exec -i --user hermes "$AGENT" python - <<'PY'
import os
from pathlib import Path

import yaml

path = Path(os.environ["HERMES_HOME"]) / "config.yaml"
config = yaml.safe_load(path.read_text()) or {}
terminal = config.get("terminal") or {}

assert terminal.get("backend") == "docker"
assert terminal.get("docker_mount_cwd_to_workspace") is False
assert terminal.get("docker_run_as_host_user") is False
assert "@sha256:" in terminal.get("docker_image", "")

print("Sandbox config: PASS")
PY

HOST_CHILDREN="$(
    docker ps -a \
        --filter 'label=hermes-agent=1' \
        --format '{{.Names}}'
)"

[[ -z "$HOST_CHILDREN" ]]

echo "Hermes sandbox foundation: PASS"
