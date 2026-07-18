#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFLIGHT="${REPO}/preflight.sh"
INSTALLER="${REPO}/install.sh"

grep -Fq \
    'export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' \
    "$PREFLIGHT"

grep -Fq 'STATIC_VALIDATION_READY=0' "$PREFLIGHT"

grep -Fq \
    'Validation statique complète reportée après installation des dépendances' \
    "$PREFLIGHT"

if grep -A3 'getent' "$PREFLIGHT" |
   grep -Eq 'getent[[:space:]]+runuser'
then
    echo "runuser reste un prérequis système dur." >&2
    exit 1
fi

grep -Fq 'sqlite3 util-linux)' "$INSTALLER"

grep -Fq \
    'runuser reste absent après installation de util-linux' \
    "$INSTALLER"

grep -Fxq 'config/projects.d/*.toml' "${REPO}/.gitignore"

if grep -Fxq     '!config/projects.d/transaction-fixture.toml'     "${REPO}/.gitignore"
then
    echo "Exception fixture interdite dans .gitignore." >&2
    exit 1
fi

if grep -Fxq     '!config/projects.d/transaction-fixture-b.toml'     "${REPO}/.gitignore"
then
    echo "Exception fixture B interdite dans .gitignore." >&2
    exit 1
fi

git -C "$REPO" check-ignore -q --no-index     config/projects.d/example-local.toml

git -C "$REPO" check-ignore -q --no-index     config/projects.d/transaction-fixture.toml

git -C "$REPO" check-ignore -q --no-index     config/projects.d/transaction-fixture-b.toml

bash -n "$PREFLIGHT"
bash -n "$INSTALLER"

echo "HermesOps minimal-host preflight contract: PASS"
