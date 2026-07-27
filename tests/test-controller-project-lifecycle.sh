#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_controller_project_lifecycle
echo "HERMESOPS_CONTROLLER_PROJECT_LIFECYCLE_PASS"
