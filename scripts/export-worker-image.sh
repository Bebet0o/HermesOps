#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C

ROOT="${HERMESOPS_ROOT:-/opt/docker/hermesops}"
REPO="${ROOT}/repo"
ENGINE="${HERMESOPS_SANDBOX_ENGINE:-hermesops-sandbox-engine}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${HERMESOPS_EXPORT_DIR:-${HOME}}"
REPORT="${OUT_DIR}/hermesops-worker-image-export-${STAMP}.log"

exec > >(tee "$REPORT") 2>&1

readarray -t LOCK_VALUES < <(
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

TAG="${LOCK_VALUES[0]}"
EXPECTED_ID="${LOCK_VALUES[1]}"
SAFE_TAG="${TAG//[:\/]/-}"
ARCHIVE="${OUT_DIR}/${SAFE_TAG}.tar.gz"
CHECKSUM="${ARCHIVE}.sha256"

docker inspect "$ENGINE" >/dev/null
ACTUAL_ID="$(docker exec "$ENGINE" docker image inspect --format '{{.Id}}' "$TAG")"
[[ "$ACTUAL_ID" == "$EXPECTED_ID" ]] || {
    echo "ID worker inattendu." >&2
    echo "Attendu : $EXPECTED_ID" >&2
    echo "Observé : $ACTUAL_ID" >&2
    exit 1
}

umask 077
docker exec "$ENGINE" docker image save "$TAG" | gzip -9 >"$ARCHIVE"
(cd "$OUT_DIR" && sha256sum "$(basename "$ARCHIVE")" >"$(basename "$CHECKSUM")")
gzip -t "$ARCHIVE"
chmod 0600 "$ARCHIVE" "$CHECKSUM" "$REPORT"

echo "WORKER_IMAGE_EXPORT_PASS"
echo "Archive  : $ARCHIVE"
echo "Checksum : $CHECKSUM"
echo "Rapport  : $REPORT"
