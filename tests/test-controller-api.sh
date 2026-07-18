#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C
export PYTHONDONTWRITEBYTECODE=1
export PYTHONWARNINGS="error::ResourceWarning"

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
export PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}"

python3 -m compileall -q \
    controller_api \
    scripts/hermesops-controller-api.py \
    tests/test_controller_api.py

python3 tests/test_controller_api.py

python3 scripts/hermesops-controller-api.py --help >/dev/null
python3 scripts/hermesops-controller-api.py serve --help >/dev/null
python3 scripts/hermesops-controller-api.py check --help >/dev/null

python3 - "$REPO/specs/controller-api-v1.openapi.json" <<'PY'
import json
import sys
from pathlib import Path

contract = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
implemented = {
    "/system/health": "get",
    "/system/status": "get",
    "/system/capabilities": "get",
    "/projects": "get",
    "/projects/{project_id}": "get",
}
for path, method in implemented.items():
    if path not in contract["paths"]:
        raise SystemExit(f"Missing OpenAPI path: {path}")
    if method not in contract["paths"][path]:
        raise SystemExit(f"Missing OpenAPI method: {method.upper()} {path}")

print("Controller API implemented OpenAPI subset: PASS")
PY

if grep -R -n -E \
    '(^|[^A-Za-z])(Flask|FastAPI|Django|aiohttp|uvicorn)([^A-Za-z]|$)' \
    controller_api scripts/hermesops-controller-api.py
then
    echo "Unexpected third-party web framework dependency." >&2
    exit 1
fi

echo "Controller API stdlib dependency contract: PASS"
echo "Controller API read-only skeleton: PASS"
echo "HERMESOPS_CONTROLLER_API_SKELETON_PASS"
