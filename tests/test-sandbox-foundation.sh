#!/usr/bin/env bash
set -Eeuo pipefail

AGENT="hermesops-agent"
ENGINE="hermesops-sandbox-engine"
SOCKET="/run/hermes-docker/docker.sock"

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

docker exec "$AGENT" test -S "$SOCKET"

docker exec --user hermes "$AGENT" sh -lc '
    test "$DOCKER_HOST" = "unix:///run/hermes-docker/docker.sock"
    docker info >/dev/null
'

ENGINE_COMMAND="$(
    docker inspect "$ENGINE" \
        --format '{{json .Config.Cmd}}'
)"

! grep -Eq 'tcp://|2375|2376' <<<"$ENGINE_COMMAND"

docker exec "$ENGINE" sh -lc '
    ! grep -qiE ":(0947|0948) " /proc/net/tcp /proc/net/tcp6
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
