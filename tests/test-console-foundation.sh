#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C
export PYTHONDONTWRITEBYTECODE=1

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 "${REPO}/scripts/hermesops-console-build.py" check \
    --source "${REPO}/console/src" \
    --expected "${REPO}/console/dist"

python3 -m unittest -v tests.test_console_service

grep -Fq "HermesOps Console" "${REPO}/console/dist/index.html"
grep -Fq "connect-src 'none'" "${REPO}/scripts/hermesops-console.py"
! grep -RInE '(fetch\(|WebSocket\(|localStorage|sessionStorage)' \
    "${REPO}/console/src" "${REPO}/console/dist/assets"

systemd-analyze verify \
    "${REPO}/systemd/user/hermesops-console.service" >/dev/null

echo "HERMESOPS_CONSOLE_WEB_FOUNDATION_PASS"
